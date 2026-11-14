from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import llm
from .graphs.evaluate import build_evaluate_graph
from .graphs.review import build_review_graph
from .local_demo import LocalDemo
from .models import DecideRequest, WorkflowError


def create_app() -> FastAPI:
    app = FastAPI(title='Transaction validation agent')
    store = LocalDemo()
    app.state.store = store
    evaluate_graph = build_evaluate_graph(store=store, write_with_audit=store.write_with_audit, recommend=llm.recommend)
    review_graph = build_review_graph(
        store=store, check_gate=store.check_gate, write_with_audit=store.write_with_audit, learn=llm.learn,
    )

    @app.exception_handler(WorkflowError)
    async def workflow_error(request: Request, error: WorkflowError) -> JSONResponse:
        return JSONResponse(status_code=error.status, content=error.body)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={
            'error': {'code': 'invalid_request', 'message': error.errors()[0]['msg']},
        })

    async def current_principal(x_principal_id: Annotated[str | None, Header()] = None) -> dict:
        principal = await store.get('principals', x_principal_id) if x_principal_id else None
        if principal is None:
            raise WorkflowError(401, 'unknown_principal', 'Missing or unknown X-Principal-Id.')
        return principal

    @app.get('/principals')
    async def principals(principal: dict = Depends(current_principal)) -> dict:
        return {'principals': await store.list_documents('principals')}

    @app.get('/transactions')
    async def transactions(
        status: Literal['pending', 'awaiting_review', 'passed', 'rejected'] | None = None,
        principal: dict = Depends(current_principal),
    ) -> dict:
        rows = []
        for txn in await store.list_transactions():
            if status and txn['status'] != status:
                continue
            customer = await store.get('customers', txn['customer_id'])
            evaluation = await store.latest_evaluation(txn['txn_id'])
            rows.append({
                **{key: txn[key] for key in ('txn_id', 'type', 'amount', 'currency', 'memo', 'status', 'created_at')},
                'customer_name': customer['name'], 'counterparty_name': txn['counterparty']['name'],
                'eval_id': evaluation['eval_id'] if evaluation else None,
            })
        return {'transactions': rows}

    def evaluation_response(evaluation: dict, txn: dict, customer: dict) -> dict:
        return {**evaluation, 'transaction': txn, 'customer': {
            key: customer[key] for key in ('customer_id', 'name', 'segment', 'typical_amount')
        }}

    @app.post('/transactions/{txn_id}/evaluate')
    async def evaluate(txn_id: str, principal: dict = Depends(current_principal)) -> dict:
        async with store.lock:
            state = await evaluate_graph.ainvoke({'txn_id': txn_id, 'principal_id': principal['_id']})
            return evaluation_response(state['evaluation'], state['txn'], state['customer'])

    @app.get('/evaluations/{eval_id}')
    async def evaluation(eval_id: str, principal: dict = Depends(current_principal)) -> dict:
        async with store.lock:
            record = await store.get('evaluations', eval_id)
            if record is None:
                raise WorkflowError(404, 'not_found', 'Unknown evaluation.')
            txn = await store.get('transactions', record['txn_id'])
            customer = await store.get('customers', txn['customer_id'])
            return {**evaluation_response(record, txn, customer), 'decision': await store.decision_for(eval_id)}

    @app.post('/evaluations/{eval_id}/decide')
    async def decide(eval_id: str, body: DecideRequest, principal: dict = Depends(current_principal)) -> dict:
        async with store.transaction():
            state = await review_graph.ainvoke({
                'eval_id': eval_id, 'principal_id': principal['_id'],
                'input': {'kind': 'decision', **body.model_dump()},
            })
        if state['gate']['result'] == 'deny':
            raise WorkflowError(403, 'gate_denied', state['gate']['reason'], gate=state['gate'])
        return {key: state[key] for key in ('decision', 'transaction_status', 'memory_created')}

    return app


app = create_app()
