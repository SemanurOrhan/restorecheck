from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import checks, docker_runner, notify, report
from .config import Config, load_config


def _restore_and_check(cfg: Config, baseline: dict[str, int]) -> report.CheckResult:
    container_id, port = docker_runner.start_postgres_container(cfg.docker_image, cfg.db_password)
    try:
        try:
            docker_runner.wait_until_ready(container_id)
            docker_runner.create_database(container_id, cfg.db_name)
            docker_runner.restore_dump(container_id, cfg.dump_path, cfg.db_name, cfg.dump_format)
        except (RuntimeError, TimeoutError) as exc:
            return report.CheckResult(
                passed=False, row_count_issues=[], canary_results=[], row_counts={}, error=str(exc)
            )

        conn = checks.connect(port, cfg.db_password, cfg.db_name)
        try:
            row_counts = checks.get_row_counts(conn)
            row_issues = checks.compare_row_counts(row_counts, baseline, cfg.row_count_threshold_pct)
            canary_results = checks.run_canary_queries(conn, cfg.canaries)
        finally:
            conn.close()
    finally:
        docker_runner.stop_container(container_id)

    passed = not row_issues and all(c["passed"] for c in canary_results)
    return report.CheckResult(
        passed=passed,
        row_count_issues=row_issues,
        canary_results=canary_results,
        row_counts=row_counts,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="restorecheck",
        description="Restore a Postgres dump into a throwaway container and verify it actually works.",
    )
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Save this run's row counts as the new baseline instead of comparing against one",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)

    if args.save_baseline:
        if not cfg.baseline_path:
            print("baseline_path is not set in config", file=sys.stderr)
            return 2
        result = _restore_and_check(cfg, baseline={})
        if result.error:
            print(f"Restore failed, baseline not saved:\n{result.error}", file=sys.stderr)
            return 1
        Path(cfg.baseline_path).write_text(json.dumps(result.row_counts, indent=2))
        print(f"Baseline saved to {cfg.baseline_path}")
        return 0

    baseline: dict[str, int] = {}
    if cfg.baseline_path and Path(cfg.baseline_path).exists():
        baseline = json.loads(Path(cfg.baseline_path).read_text())

    result = _restore_and_check(cfg, baseline)
    print(report.to_json(result))

    if cfg.slack_webhook_url:
        notify.send_slack(cfg.slack_webhook_url, report.to_slack_summary(result, cfg.dump_path))

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
