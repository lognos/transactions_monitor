"""Deterministic model stand-in for the local payroll workflow."""

from calendar import monthrange
from datetime import date

from .models import JudgmentCheck, LearnOutput, RecommendOutput

PAYROLL_COMMENT = "Payroll customers spike at month-end, that's normal."
PAYROLL_CONDITION = 'customer segment is payroll and date is within 3 days of month-end'


async def recommend(
    *, txn: dict, customer: dict, policy: dict, checks: list[dict],
    precedents: list[dict], adjustments: list[dict],
) -> RecommendOutput:
    criterion = next(item for item in policy['criteria'] if item['id'] == 'C-04')
    typical = customer['typical_amount']
    ratio = txn['amount'] / typical if typical else None
    adjustment = next((item for item in adjustments if item['scope'] == {
        'criterion_id': 'C-04', 'condition': PAYROLL_CONDITION,
    }), None)
    valid_date = any(check['criterion_id'] == 'Q-01' and check['result'] == 'pass' for check in checks)
    if adjustment and valid_date and customer['segment'] == 'payroll':
        cheque_date = date.fromisoformat(txn['type_specific']['cheque_date'])
        days_to_month_end = monthrange(cheque_date.year, cheque_date.month)[1] - cheque_date.day
        if days_to_month_end > 3:
            adjustment = None
    else:
        adjustment = None

    if adjustment:
        evidence = f"Month-end payroll spike covered by guidance from {adjustment['author_id']}."
        judgment = JudgmentCheck(
            criterion_id='C-04', result='pass', evidence=evidence,
            adjustments_used=[adjustment['memory_id']],
        )
    elif ratio is None:
        evidence = 'No posted payment history is available to establish a typical amount.'
        judgment = JudgmentCheck(criterion_id='C-04', evidence=evidence, result='no_pass')
    else:
        evidence = f'Cheque amount is {ratio:.1f} times the typical amount.'
        judgment = JudgmentCheck(
            criterion_id='C-04', evidence=evidence,
            result='no_pass' if ratio > criterion['params']['ratio_hint'] else 'pass',
        )
    return RecommendOutput(judgment_checks=[judgment], rationale=evidence)


async def learn(*, decision: dict, evaluation: dict, policy: dict) -> LearnOutput:
    if decision['verdict'] == 'rejected' or decision['comments'] != PAYROLL_COMMENT:
        return LearnOutput(should_create=False)
    return LearnOutput(
        should_create=True,
        criterion_id='C-04',
        condition=PAYROLL_CONDITION,
        text='Higher cheque amounts are expected for payroll customers near month-end.',
    )
