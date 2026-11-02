from restorecheck.report import CheckResult, to_slack_summary


def test_slack_summary_includes_restore_error():
    result = CheckResult(
        passed=False, row_count_issues=[], canary_results=[], row_counts={}, error="pg_restore: boom"
    )
    summary = to_slack_summary(result, "/backups/a.dump")
    assert "FAILED" in summary
    assert "pg_restore: boom" in summary


def test_slack_summary_lists_failed_canaries():
    result = CheckResult(
        passed=False,
        row_count_issues=["public.orders: row count changed 100 -> 10 (90.0%, threshold 10.0%)"],
        canary_results=[{"name": "c1", "value": 0, "passed": False, "message": "value=0 is below expect_min=1"}],
        row_counts={"public.orders": 10},
    )
    summary = to_slack_summary(result, "/backups/a.dump")
    assert "public.orders" in summary
    assert "c1" in summary


def test_slack_summary_passed():
    result = CheckResult(passed=True, row_count_issues=[], canary_results=[], row_counts={"public.t": 1})
    assert "PASSED" in to_slack_summary(result, "/backups/a.dump")
