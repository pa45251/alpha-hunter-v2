from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
DEFAULT_MANIFEST = Path("output/manifest.json")


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def canonical_snapshot_is_fresh_for_today(manifest: dict, now: datetime | None = None) -> tuple[bool, str]:
    now = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    if manifest.get("status") != "PASS":
        return False, "MANIFEST_NOT_PASS"

    generated = manifest.get("generated_at_taipei") or manifest.get("generated_at_utc")
    if not generated:
        return False, "MANIFEST_TIMESTAMP_MISSING"

    try:
        generated_dt = _parse_iso(str(generated)).astimezone(TAIPEI)
    except ValueError:
        return False, "MANIFEST_TIMESTAMP_INVALID"

    if generated_dt.date() != now.date():
        return False, "MANIFEST_NOT_TODAY_TAIPEI"

    age_seconds = (now - generated_dt).total_seconds()
    if age_seconds < -300:
        return False, "MANIFEST_FROM_FUTURE"
    if age_seconds > 12 * 3600:
        return False, "MANIFEST_TOO_OLD"

    checks = manifest.get("pipeline_checks") or {}
    if checks and not all(bool(v) for v in checks.values()):
        return False, "PIPELINE_CHECKS_NOT_ALL_TRUE"

    return True, "FRESH_TODAY"


def triggering_run_produced_snapshot(
    manifest: dict,
    trigger_started_at_utc: str,
    tolerance_seconds: int = 120,
) -> tuple[bool, str]:
    if manifest.get("status") != "PASS":
        return False, "MANIFEST_NOT_PASS"

    generated = manifest.get("generated_at_utc")
    if not generated:
        return False, "MANIFEST_UTC_TIMESTAMP_MISSING"

    try:
        generated_dt = _parse_iso(str(generated)).astimezone(timezone.utc)
        trigger_dt = _parse_iso(trigger_started_at_utc).astimezone(timezone.utc)
    except ValueError:
        return False, "TRIGGER_TIMESTAMP_INVALID"

    if generated_dt.timestamp() + tolerance_seconds < trigger_dt.timestamp():
        return False, "SNAPSHOT_PREDATES_TRIGGER"
    return True, "SNAPSHOT_FROM_TRIGGER_WINDOW"


def _write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Alpha Hunter V4 automation freshness guard")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--mode", choices=("scheduled-scan", "workflow-trigger"), required=True)
    parser.add_argument("--trigger-started-at-utc", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(Path(args.manifest))

    if args.mode == "scheduled-scan":
        if args.force:
            should_run, reason = True, "FORCED"
        else:
            fresh, reason = canonical_snapshot_is_fresh_for_today(manifest)
            should_run = not fresh
    else:
        if not args.trigger_started_at_utc:
            should_run, reason = False, "TRIGGER_START_MISSING"
        else:
            should_run, reason = triggering_run_produced_snapshot(manifest, args.trigger_started_at_utc)

    _write_output("should_run", "true" if should_run else "false")
    _write_output("reason", reason)
    _write_output("existing_run_id", str(manifest.get("run_id") or ""))
    print(json.dumps({"should_run": should_run, "reason": reason, "existing_run_id": manifest.get("run_id")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
