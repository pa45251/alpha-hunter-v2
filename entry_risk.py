"""Canonical long-entry price risk. Stops are inputs, never moved to pass policy."""
import math

MAX_ENTRY_RISK = 0.08
MIN_REWARD_RISK = 2.0
RISK_CONTRACT = 'LONG_ENTRY_UPPER_TO_INVALIDATION_V1'


def entry_risk(entry_low, entry_high, stop, reference):
    """Worst downside and worst reference R/R over the entire executable zone.

    Fractions, not percent points. Excludes fees, slippage and gap-through risk.
    A technical reference is a scenario, not a forecast or promised exit target.
    """
    out = dict(risk_contract=RISK_CONTRACT, risk_basis='ENTRY_UPPER_TO_STOP',
               risk_limit_pct=MAX_ENTRY_RISK, minimum_reward_risk=MIN_REWARD_RISK,
               risk_amount=None, risk_pct=None, reward_amount=None, reward_risk=None,
               risk_gate=False, reward_risk_gate=False, entry_risk_eligible=False,
               risk_summary='Unavailable: require 0 < stop < entry_low <= entry_high',
               reference_is_target=False)
    try:
        low, high, invalidation = map(float, (entry_low, entry_high, stop))
    except (ValueError, TypeError):
        return out
    if not all(math.isfinite(v) for v in (low, high, invalidation)) or not 0 < invalidation < low <= high:
        return out
    downside = high - invalidation
    pct = downside / high
    risk_ok = pct <= MAX_ENTRY_RISK
    try:
        ref = float(reference)
        reward = ref - high if math.isfinite(ref) and ref > high else None
    except (ValueError, TypeError):
        reward = None
    rr = reward / downside if reward is not None else None
    rr_ok = rr is not None and rr >= MIN_REWARD_RISK
    out.update(risk_amount=downside, risk_pct=pct, reward_amount=reward,
               reward_risk=rr, risk_gate=risk_ok, reward_risk_gate=rr_ok,
               entry_risk_eligible=risk_ok and rr_ok,
               risk_summary=f'Worst-zone downside ({high:g} - {invalidation:g}) / {high:g} = {pct:.2%}; '
                            f'{"within" if risk_ok else "exceeds"} {MAX_ENTRY_RISK:.0%} policy limit')
    return out


def risk_narrative(metrics, reference_basis):
    rr = metrics['reward_risk']
    reference = (f'{reference_basis}: {rr:.2f}R before costs'
                 if rr is not None else 'No upside reference above entry; R/R unavailable')
    result = metrics['risk_summary'] + '; ' + reference + ' (technical reference, not a price target).'
    if not metrics['entry_risk_eligible']:
        result += ' WAIT_FOR_ENTRY: require a new valid setup; retain the technical invalidation.'
    return result


def validate_plan(plan):
    """Fail closed before publication if any risk number or permission drifted."""
    metrics = entry_risk(plan.get('entry_low'), plan.get('entry_high'), plan.get('stop'), plan.get('reference_target'))
    for key in ['risk_amount', 'risk_pct', 'reward_amount', 'reward_risk']:
        actual, expected = plan.get(key), metrics[key]
        if expected is None:
            if actual is not None:
                raise ValueError('ENTRY_RISK_INCONSISTENT:' + key)
        elif actual is None or not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-10):
            raise ValueError('ENTRY_RISK_INCONSISTENT:' + key)
    for key in ['risk_gate', 'reward_risk_gate', 'entry_risk_eligible']:
        if plan.get(key) != metrics[key]:
            raise ValueError('ENTRY_RISK_INCONSISTENT:' + key)
    if (plan.get('price_ok') or plan.get('action') in {'BUY', 'EARLY BUY'}) and not metrics['entry_risk_eligible']:
        raise ValueError('ENTRY_RISK_PERMISSION_INCONSISTENT')
    if plan.get('risk_summary') != metrics['risk_summary']:
        raise ValueError('ENTRY_RISK_NARRATIVE_INCONSISTENT')
    if metrics['risk_pct'] is not None:
        if (plan.get('entry') != f"{plan['entry_low']:g}–{plan['entry_high']:g}"
                or plan.get('invalidation') != f"Exit on loss of {plan['stop']:g}; thesis failure also invalidates"
                or not plan.get('price_reason', '').startswith(risk_narrative(metrics, plan.get('target_basis')))):
            raise ValueError('ENTRY_RISK_DISPLAY_INCONSISTENT')
