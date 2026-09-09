"""Validate private numeric contracts before entering the immutable V2 runtime.

No values, holding identities or policy field paths are printed. No thresholds change.
"""
import math
import runpy
import sys
from portfolio_risk import load_risk_policy, load_portfolio_state
from portfolio_risk_v2 import validate_risk_inputs_v2

NUMERIC = {'market_value_twd','financing_debt_twd','cash_twd','gross_exposure_pct',
           'weight_pct','max_single_position_pct','max_theme_exposure_pct',
           'max_gross_exposure_pct','max_new_position_pct','min_avg_turnover_twd',
           'max_position_loss_pct','cost_basis','current_price'}


def check_numbers(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if key in NUMERIC:
                if type(item) not in (int,float) or not math.isfinite(item) or item<0:
                    raise ValueError('PRIVATE_NUMERIC_CONTRACT_INVALID')
            check_numbers(item)
    elif isinstance(value,list):
        for item in value:check_numbers(item)


def validate():
    try:
        policy,portfolio=load_risk_policy(),load_portfolio_state()
        check_numbers(policy);check_numbers(portfolio)
        valid,_,normalized=validate_risk_inputs_v2(policy,portfolio)
        if not valid:raise ValueError('invalid')
        for pos in normalized["positions"]:
            weight=pos.get("weight_pct")
            if (not isinstance(pos.get("ticker"),str) or not pos["ticker"].strip()
                    or type(weight) not in (int,float) or not math.isfinite(weight) or weight<0):
                raise ValueError("position exposure unavailable")
    except Exception:
        raise ValueError('PRIVATE_RISK_INPUTS_NOT_READY') from None


def main():
    allowed={'decision_run_v2','decision_run_with_maintenance_v2','position_alias_output_v2',
             'position_cio_advisory','entry_plan_run_v2'}
    if len(sys.argv)!=2 or sys.argv[1] not in allowed:
        raise SystemExit('UNSUPPORTED_RUNTIME_ENTRYPOINT')
    validate()
    if sys.argv[1]=='entry_plan_run_v2':
        from canonical_price_inputs import load
        import entry_structure_v2
        frames=load()
        previous=entry_structure_v2._download_histories
        entry_structure_v2._download_histories=lambda tickers: {t:frames[t] for t in tickers if t in frames}
        try:
            runpy.run_module(sys.argv[1],run_name='__main__')
        finally:
            entry_structure_v2._download_histories=previous
    else:
        runpy.run_module(sys.argv[1],run_name='__main__')

if __name__=='__main__':main()
