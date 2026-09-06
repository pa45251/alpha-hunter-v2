from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


OUT = Path("output")
MANIFEST = OUT / "manifest.json"
QUEUE = OUT / "causal_research_queue.csv"
RESEARCH = OUT / "research_result_v3.json"
ACTIVATION_OUT = OUT / "driver_activation_v3.csv"


def _claims(items: list[dict] | None) -> str:
    if not items:
        return ""
    vals = []
    for item in items:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim", "")).strip()
        title = str(item.get("source_title", "")).strip()
        url = str(item.get("source_url", "")).strip()
        bit = claim
        if title:
            bit += f" [{title}]"
        if url:
            bit += f" {url}"
        if bit.strip():
            vals.append(bit.strip())
    return " | ".join(vals)


def main() -> None:
    required = [MANIFEST, QUEUE, RESEARCH]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(f"V3 activation bridge missing canonical inputs: {missing}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    queue = pd.read_csv(QUEUE)

    run_id = str(manifest.get("run_id", ""))
    if not run_id:
        raise RuntimeError("V3 activation bridge missing manifest run_id")
    if research.get("contract") != "ALPHA_HUNTER_V3_VALIDATED_RESEARCH":
        raise RuntimeError("V3 activation bridge research contract mismatch")
    if research.get("status") != "PASS":
        raise RuntimeError(f"V3 activation bridge research status is not PASS: {research.get('status')}")
    if str(research.get("research_run_id", "")) != run_id:
        raise RuntimeError("V3 activation bridge MIXED_SNAPSHOT_DATA: research/manifest run_id mismatch")
    if "run_id" not in queue.columns or queue.empty or not queue["run_id"].astype(str).eq(run_id).all():
        raise RuntimeError("V3 activation bridge MIXED_SNAPSHOT_DATA: queue/manifest run_id mismatch")

    queue_ids = set(queue["driver_id"].astype(str))
    results = research.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("V3 activation bridge research results missing")

    rows = []
    seen: set[str] = set()
    validated_at = str(research.get("validated_at_utc", ""))
    for result in results:
        if not isinstance(result, dict):
            raise RuntimeError("V3 activation bridge encountered non-object research result")
        driver_id = str(result.get("driver_id", ""))
        if not driver_id or driver_id in seen:
            raise RuntimeError(f"V3 activation bridge duplicate/missing driver_id: {driver_id}")
        if driver_id not in queue_ids:
            raise RuntimeError(f"V3 activation bridge unnominated driver: {driver_id}")
        if str(result.get("research_run_id", "")) != run_id:
            raise RuntimeError(f"V3 activation bridge per-driver run_id mismatch: {driver_id}")
        seen.add(driver_id)

        state = str(result.get("state", "UNKNOWN")).upper()
        if state not in {"ACTIVE", "INACTIVE", "UNKNOWN"}:
            raise RuntimeError(f"V3 activation bridge invalid state for {driver_id}: {state}")
        confidence = float(result.get("confidence", 0.0))
        if confidence < 0 or confidence > 1:
            raise RuntimeError(f"V3 activation bridge invalid confidence for {driver_id}: {confidence}")
        source_count = int(result.get("source_count", 0))
        if source_count < 0:
            raise RuntimeError(f"V3 activation bridge invalid source_count for {driver_id}")

        supporting = result.get("supporting_evidence") or []
        counter = result.get("counter_evidence") or []
        rows.append({
            "driver_id": driver_id,
            "activation_state": state,
            "activation_confidence": confidence,
            "as_of_utc": str(result.get("researched_at_utc") or validated_at),
            "source_count": source_count,
            "primary_cause": str(result.get("primary_cause", "")),
            "counter_evidence": _claims(counter),
            "source_summary": _claims(supporting),
            "industry_scope": str(result.get("industry_scope", "UNKNOWN")),
            "research_run_id": run_id,
            "activation_source": "V3_AUTONOMOUS_RESEARCH",
        })

    df = pd.DataFrame(rows)
    df.to_csv(ACTIVATION_OUT, index=False)
    active = int(df["activation_state"].eq("ACTIVE").sum())
    inactive = int(df["activation_state"].eq("INACTIVE").sum())
    unknown = int(df["activation_state"].eq("UNKNOWN").sum())
    print(f"V3 activation bridge PASS: rows={len(df)} ACTIVE={active} INACTIVE={inactive} UNKNOWN={unknown} run_id={run_id}")


if __name__ == "__main__":
    main()
