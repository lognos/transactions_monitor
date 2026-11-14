from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from typing_extensions import TypedDict

from ..models import LearnOutput, WorkflowError, Write, new_id, utc_now


class ReviewInput(TypedDict):
    eval_id: str
    principal_id: str
    input: dict


class ReviewState(ReviewInput, total=False):
    evaluation: dict
    txn: dict
    principal: dict
    gate: dict
    decision: dict
    transaction_status: str
    memory_created: list[dict]


def build_review_graph(*, store, check_gate, write_with_audit, learn):
    async def load_review(state: ReviewState) -> dict:
        evaluation = await store.get('evaluations', state['eval_id'])
        if evaluation is None:
            raise WorkflowError(404, 'not_found', 'Unknown evaluation.')
        if evaluation['status'] == 'decided':
            raise WorkflowError(409, 'already_decided', 'This evaluation already has a decision.')
        return {
            'evaluation': evaluation, 'txn': await store.get('transactions', evaluation['txn_id']),
            'principal': await store.get('principals', state['principal_id']), 'memory_created': [],
        }

    async def policy_gate(state: ReviewState) -> Command[Literal['record_denied', 'record_decision']]:
        gate = await check_gate(
            principal=state['principal'], txn=state['txn'], evaluation=state['evaluation'],
            verdict=state['input']['verdict'],
        )
        destination = 'record_denied' if gate['result'] == 'deny' else 'record_decision'
        return Command(goto=destination, update={'gate': gate})

    def reviewer_actor(state: ReviewState) -> dict:
        principal = state['principal']
        return {'id': principal['_id'], 'type': principal['type'], 'role': principal['role'], 'on_behalf_of': None}

    async def record_denied(state: ReviewState) -> dict:
        await write_with_audit(
            actor=reviewer_actor(state), event='decision.denied', txn_id=state['txn']['txn_id'],
            ref={'collection': 'evaluations', 'id': state['eval_id']},
            detail={'verdict': state['input']['verdict'], 'amount': state['txn']['amount'], 'gate': state['gate']},
            writes=[],
        )
        return {}

    async def record_decision(state: ReviewState) -> dict:
        verdict = state['input']['verdict']
        transaction_status = 'rejected' if verdict == 'rejected' else 'passed'
        decision_id = new_id('DEC')
        txn_id = state['txn']['txn_id']
        decision = {
            'decision_id': decision_id, 'eval_id': state['eval_id'], 'txn_id': txn_id,
            'reviewer_id': state['principal_id'], 'verdict': verdict, 'comments': state['input']['comments'],
            'agreed_with_agent': (verdict != 'rejected') == (state['evaluation']['recommendation'] == 'pass'),
            'gate': state['gate'], 'ts': utc_now(),
        }
        await write_with_audit(
            actor=reviewer_actor(state), event='decision.recorded', txn_id=txn_id,
            ref={'collection': 'decisions', 'id': decision_id},
            detail={key: decision[key] for key in ('verdict', 'agreed_with_agent', 'gate')},
            writes=[Write('decisions', decision_id, decision),
                    Write('evaluations', state['eval_id'], {'status': 'decided'}, 'update'),
                    Write('transactions', txn_id, {'status': transaction_status}, 'update')],
        )
        return {'decision': decision, 'transaction_status': transaction_status}

    async def store_memory(state: ReviewState, *, kind: str, text: str, scope: dict | None) -> dict:
        txn = state['txn']
        memory_id = new_id('MEM')
        decision_id = state['decision']['decision_id']
        author_id = state['principal_id']
        memory = {
            'memory_id': memory_id, 'kind': kind, 'txn_type': txn['type'], 'text': text, 'scope': scope,
            'source_decision_id': decision_id, 'source_txn_id': txn['txn_id'], 'author_id': author_id,
            'active': True, 'created_at': utc_now(),
        }
        await write_with_audit(
            actor={'id': 'agent-01', 'type': 'agent', 'role': 'agent', 'on_behalf_of': author_id},
            event='memory.created', txn_id=txn['txn_id'], ref={'collection': 'memory', 'id': memory_id},
            detail={'kind': kind, 'criterion_id': scope['criterion_id'] if scope else None,
                    'source_decision_id': decision_id, 'author_id': author_id},
            writes=[Write('memory', memory_id, memory)],
        )
        return {'memory_id': memory_id, 'kind': kind, 'text': text}

    async def learn_from_feedback(state: ReviewState) -> dict:
        policy = await store.get('policies', state['txn']['type'])
        output = LearnOutput.model_validate(await learn(
            decision=state['decision'], evaluation=state['evaluation'], policy=policy,
        ))
        judgment_ids = {c['id'] for c in policy['criteria'] if c['kind'] == 'judgment'}
        if not (output.should_create and output.criterion_id in judgment_ids
                and output.condition.strip() and output.text.strip()):
            return {}
        memory = await store_memory(state, kind='adjustment', text=output.text,
                                    scope={'criterion_id': output.criterion_id, 'condition': output.condition})
        return {'memory_created': [*state['memory_created'], memory]}

    async def store_precedent(state: ReviewState) -> dict:
        txn = state['txn']
        decision = state['decision']
        text = (f"{txn['type'].capitalize()}, {txn['currency']} {txn['amount']:,}, "
                f"{decision['verdict'].replace('_', ' ')} by {decision['reviewer_id']}.")
        memory = await store_memory(state, kind='precedent', text=text, scope=None)
        return {'memory_created': [*state['memory_created'], memory]}

    graph = StateGraph(ReviewState, input_schema=ReviewInput)
    for node in (load_review, policy_gate, record_denied, record_decision, learn_from_feedback, store_precedent):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, 'load_review')
    graph.add_edge('load_review', 'policy_gate')
    graph.add_edge('record_denied', END)
    graph.add_conditional_edges('record_decision', lambda state: 'learn_from_feedback' if state['input']['comments']
                                else 'store_precedent', ['learn_from_feedback', 'store_precedent'])
    graph.add_edge('learn_from_feedback', 'store_precedent')
    graph.add_edge('store_precedent', END)
    return graph.compile()
