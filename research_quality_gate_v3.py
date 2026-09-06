from __future__ import annotations

import json
from pathlib import Path


RESULT = Path("output/research_result_v3.json")


def evaluate(path: Path = RESULT) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results") or []
    total_sources = 0
    sourced_drivers = 0
    active_or_inactive = 0
    for row in results:
        try:
            source_count = int(row.get("source_count", 0) or 0)
        except Exception:
            source_count = 0
        total_sources += max(source_count, 0)
        if source_count > 0:
            sourced_drivers += 1
        if str(row.get("state", "UNKNOWN")).upper() in {"ACTIVE", "INACTIVE"}:
            active_or_inactive += 1

    status = str(data.get("status", ""))
    quality_pass = (
        status == "PASS"
        and len(results) > 0
        and total_sources > 0
        and sourced_drivers > 0
    )
    return {
        "status": status,
        "target_count": len(results),
        "total_sources": total_sources,
        "sourced_drivers": sourced_drivers,
        "active_or_inactive": active_or_inactive,
        "quality_pass": quality_pass,
    }


def main() -> None:
    q = evaluate()
    print(
        "research quality: "
        f"status={q['status']} targets={q['target_count']} total_sources={q['total_sources']} "
        f"sourced_drivers={q['sourced_drivers']} resolved={q['active_or_inactive']}"
    )
    if not q["quality_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
