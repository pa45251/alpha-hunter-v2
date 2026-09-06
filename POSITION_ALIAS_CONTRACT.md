# Alpha Hunter Position Alias Contract

## Purpose

Existing-position decisions must be identifiable to the user without publishing the real instrument identity or portfolio balances in this public repository.

## Private mapping

The ticker-to-alias mapping is private configuration. Preferred source:

`ALPHA_HUNTER_POSITION_ALIAS_JSON`

Accepted schema:

```json
{
  "aliases": {
    "SYNTHETIC_TICKER_1": "CORE_A",
    "SYNTHETIC_TICKER_2": "SATELLITE_B"
  }
}
```

An `alias` field embedded inside each position in the private `ALPHA_HUNTER_PORTFOLIO_JSON` is also accepted as a fallback.

Do not commit the real mapping to the repository, tests, documentation, issues, pull requests, logs, or Action artifacts.

## Public output

`output/position_alias_actions.json` may contain only:

- run id / generation metadata
- user-defined alias
- action
- reason
- thesis mapping / thesis strength
- user-thesis disagreement boolean

It must not contain:

- ticker / security code
- company or ETF name
- market value
- weight
- cost basis
- realized or unrealized P/L
- cash
- financing / debt
- the ticker-to-alias mapping

## Fail-closed rules

- Missing mapping: do not guess; mark alias output `NOT_CONFIGURED`.
- Incomplete mapping: do not publish a partial alias file.
- Duplicate aliases: reject.
- Invalid aliases: reject.
- Alias action counts must exactly equal the aggregate existing-position action counts from the same decision packet.
- A stale alias file must be deleted if the current run cannot produce a valid alias output.

## Separation from execution

Alias publication changes observability only. It does not alter the frozen decision, risk, launch, sizing, shadow-validation, or brokerage-execution rules.
