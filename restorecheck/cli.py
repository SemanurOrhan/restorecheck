from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import checks, docker_runner, notify, report
from .config import load_config


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

    container_id, port = docker_runner.start_postgres_container(cfg.docker_image, cfg.db_password)
    try:
        docker_runner.wait_until_ready(container_id)
        docker_runner.create_database(container_id, cfg.db_name)
        docker_runner.restore_dump(container_id, cfg.dump_path, cfg.db_name, cfg.dump_format)

        conn = checks.connect(port, cfg.db_password, cfg.db_name)
        try:
            row_counts = checks.get_row_counts(conn)

            if args.save_baseline:
                if not cfg.baseline_path:
                    print("baseline_path is not set in config", file=sys.stderr)
                    return 2
                Path(cfg.baseline_path).write_text(json.dumps(row_counts, indent=2))
                print(f"Baseline saved to {cfg.baseline_path}")
                return 0

            baseline: dict[str, int] = {}
            if cfg.baseline_path and Path(cfg.baseline_path).exists():
                baseline = json.loads(Path(cfg.baseline_path).read_text())

            row_issues = checks.compare_row_counts(row_counts, baseline, cfg.row_count_threshold_pct)
            canary_results = checks.run_canary_queries(conn, cfg.canaries)
        finally:
            conn.close()
    finally:
        docker_runner.stop_container(container_id)

    passed = not row_issues and all(c["passed"] for c in canary_results)
    result = report.CheckResult(
        passed=passed,
        row_count_issues=row_issues,
        canary_results=canary_results,
        row_counts=row_counts,
    )

    print(report.to_json(result))

    if cfg.slack_webhook_url:
        notify.send_slack(cfg.slack_webhook_url, report.to_slack_summary(result, cfg.dump_path))

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
