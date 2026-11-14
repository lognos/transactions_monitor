"""Model adapter for recommendations and local feedback-learning stand-in."""

from .models import LearnOutput, RecommendOutput, WorkflowError
from .recommendation import build_recommend_messages

PAYROLL_COMMENT = "Payroll customers spike at month-end, that's normal."
PAYROLL_CONDITION = 'customer segment is payroll and date is within 3 days of month-end'


async def probe_model() -> None:
    from .config import settings

    try:
        from .agent.llm import get_llm

        await get_llm().ainvoke('Reply with OK. This is a connectivity test.')
    except Exception as exc:
        raise WorkflowError(
            502, 'llm_call_failed',
            f'Could not call {settings.llm_model} ({type(exc).__name__}). '
            'Check the model dependencies, credentials and provider connection.',
        ) from exc


async def recommend(
    *, txn: dict, customer: dict, policy: dict, checks: list[dict],
    related_policies: list[dict], precedents: list[dict], adjustments: list[dict],
) -> RecommendOutput:
    from .agent.llm import get_llm

    messages = build_recommend_messages(
        txn=txn, customer=customer, policy=policy, checks=checks,
        related_policies=related_policies, precedents=precedents, adjustments=adjustments,
    )
    try:
        output = await get_llm().with_structured_output(RecommendOutput).ainvoke(messages)
        return RecommendOutput.model_validate(output)
    except Exception as exc:
        raise WorkflowError(
            502, 'llm_call_failed', f'Recommendation model call failed ({type(exc).__name__}).',
        ) from exc


async def learn(*, decision: dict, evaluation: dict, policy: dict) -> LearnOutput:
    if decision['verdict'] == 'rejected' or decision['comments'] != PAYROLL_COMMENT:
        return LearnOutput(should_create=False)
    return LearnOutput(
        should_create=True,
        criterion_id='C-04',
        condition=PAYROLL_CONDITION,
        text='Higher cheque amounts are expected for payroll customers near month-end.',
    )
