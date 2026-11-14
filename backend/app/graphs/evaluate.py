from typing import Literal

from langgraph.types import Command
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from ..checks import CHECKS
from ..models import RecommendOutput, WorkflowError, Write, new_id, utc_now


class EvalInput(TypedDict):
    txn_id: str
    principal_id: str


class EvalState(EvalInput, total=False):
    txn: dict
    customer: dict
    policy: dict
    checks: list[dict]
    precedents: list[dict]
    adjustments: list[dict]
    llm_output: dict
    evaluation: dict


def build_evaluate_graph(*, store, write_with_audit, recommend):
    async def load(state: EvalState) -> Command[Literal['run_checks', '__end__']]:
        txn = await store.get('transactions', state['txn_id'])
        if txn is None:
            raise WorkflowError(404, 'not_found', 'Unknown transaction.')
        customer = await store.get('customers', txn['customer_id'])
        if txn['status'] != 'pending':
            return Command(goto=END, update={
                'txn': txn, 'customer': customer,
                'evaluation': await store.latest_evaluation(txn['txn_id']),
            })
        policy = await store.get('policies', txn['type'])
        if not policy or not policy['active']:
            raise WorkflowError(422, 'unsupported_transaction_type', 'No active policy for this payment method.')
        return Command(goto='run_checks', update={'txn': txn, 'customer': customer, 'policy': policy})

    async def run_checks(state: EvalState) -> dict:
        checks = []
        for criterion in state['policy']['criteria']:
            if criterion['kind'] != 'hard':
                continue
            outcome = await CHECKS[criterion['check']](state['txn'], state['customer'], criterion['params'], store)
            checks.append({
                'criterion_id': criterion['id'], 'description': criterion['description'],
                'kind': 'hard', 'source': 'rule', 'regulation_ref': criterion['regulation_ref'],
                'precedents_used': [], 'adjustments_used': [], **outcome,
            })
        return {'checks': checks}

    async def retrieve_context(state: EvalState) -> dict:
        return {'precedents': [], 'adjustments': await store.active_adjustments(txn_type=state['txn']['type'])}

    async def recommend_node(state: EvalState) -> dict:
        output = await recommend(
            txn=state['txn'], customer=state['customer'], policy=state['policy'], checks=state['checks'],
            precedents=state['precedents'], adjustments=state['adjustments'],
        )
        return {'llm_output': RecommendOutput.model_validate(output).model_dump()}

    async def save_evaluation(state: EvalState) -> dict:
        criteria = {c['id']: c for c in state['policy']['criteria'] if c['kind'] == 'judgment'}
        output = RecommendOutput.model_validate(state['llm_output'])
        returned_ids = [check.criterion_id for check in output.judgment_checks]
        if sorted(returned_ids) != sorted(criteria):
            raise WorkflowError(502, 'invalid_model_output', 'Expected one result per judgment criterion.')
        precedent_ids = {item['memory_id'] for item in state['precedents']}
        checks = list(state['checks'])
        for check in output.judgment_checks:
            criterion = criteria[check.criterion_id]
            allowed_adjustments = {item['memory_id'] for item in state['adjustments']
                                   if item['scope']['criterion_id'] == check.criterion_id}
            checks.append({
                'criterion_id': check.criterion_id, 'description': criterion['description'],
                'kind': 'judgment', 'source': 'llm', 'regulation_ref': criterion['regulation_ref'],
                'result': check.result, 'evidence': check.evidence,
                'precedents_used': sorted(precedent_ids.intersection(check.precedents_used)),
                'adjustments_used': sorted(allowed_adjustments.intersection(check.adjustments_used)),
            })
        failed = [item['criterion_id'] for item in checks if item['result'] == 'no_pass']
        actor = {'id': 'agent-01', 'type': 'agent', 'role': 'agent', 'on_behalf_of': state['principal_id']}
        eval_id = new_id('EVAL')
        txn_id = state['txn_id']
        evaluation = {
            'eval_id': eval_id, 'txn_id': txn_id, 'actor': actor, 'policy_version': state['policy']['version'],
            'checks': checks, 'recommendation': 'no_pass' if failed else 'pass', 'rationale': output.rationale,
            'precedents_used': sorted({ref for check in checks for ref in check['precedents_used']}),
            'adjustments_used': sorted({ref for check in checks for ref in check['adjustments_used']}),
            'thread': [], 'status': 'awaiting_review', 'created_at': utc_now(),
        }
        detail = {key: evaluation[key] for key in ('recommendation', 'policy_version', 'precedents_used', 'adjustments_used')}
        await write_with_audit(
            actor=actor, event='evaluation.created', txn_id=txn_id,
            ref={'collection': 'evaluations', 'id': eval_id}, detail={**detail, 'failed': failed},
            writes=[Write('evaluations', eval_id, evaluation),
                    Write('transactions', txn_id, {'status': 'awaiting_review'}, 'update')],
        )
        return {'evaluation': evaluation, 'txn': {**state['txn'], 'status': 'awaiting_review'}}

    graph = StateGraph(EvalState, input_schema=EvalInput)
    for node in (load, run_checks, retrieve_context, save_evaluation):
        graph.add_node(node.__name__, node)
    graph.add_node('recommend', recommend_node)
    graph.add_edge(START, 'load')
    graph.add_edge('run_checks', 'retrieve_context')
    graph.add_edge('retrieve_context', 'recommend')
    graph.add_edge('recommend', 'save_evaluation')
    graph.add_edge('save_evaluation', END)
    return graph.compile()
