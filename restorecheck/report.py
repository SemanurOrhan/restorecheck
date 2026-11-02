from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CheckResult:
    passed: bool
    row_count_issues: list[str]
    canary_results: list[dict]
    row_counts: dict[str, int]
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def to_json(result: CheckResult) -> str:
    return json.dumps(result.__dict__, indent=2)


def to_slack_summary(result: CheckResult, dump_path: str) -> str:
    status = "PASSED" if result.passed else "FAILED"
    lines = [f"*Restore check {status}* for `{dump_path}`"]

    if result.error:
        lines.append(f"Restore error: {result.error}")

    if result.row_count_issues:
        lines.append("Row count issues:")
        lines.extend(f"- {issue}" for issue in result.row_count_issues)

    failed_canaries = [c for c in result.canary_results if not c["passed"]]
    if failed_canaries:
        lines.append("Failed canary checks:")
        lines.extend(f"- {c['name']}: {c['message']}" for c in failed_canaries)

    if result.passed:
        lines.append(f"All {len(result.row_counts)} tables and {len(result.canary_results)} canary checks look healthy.")

    return "\n".join(lines)
