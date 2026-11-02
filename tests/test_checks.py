from restorecheck.checks import _evaluate_canary, compare_row_counts


def test_compare_row_counts_no_baseline():
    assert compare_row_counts({"public.orders": 100}, {}, 10.0) == []


def test_compare_row_counts_within_threshold():
    assert compare_row_counts({"public.orders": 105}, {"public.orders": 100}, 10.0) == []


def test_compare_row_counts_exceeds_threshold():
    issues = compare_row_counts({"public.orders": 50}, {"public.orders": 100}, 10.0)
    assert len(issues) == 1
    assert "public.orders" in issues[0]


def test_compare_row_counts_missing_table():
    issues = compare_row_counts({}, {"public.orders": 100}, 10.0)
    assert "missing" in issues[0]


def test_compare_row_counts_ignores_new_table():
    assert compare_row_counts({"public.new_table": 5}, {}, 10.0) == []


def test_evaluate_canary_passes_with_no_bounds():
    passed, _ = _evaluate_canary(5, expect_min=None, expect_max=None)
    assert passed


def test_evaluate_canary_fails_below_min():
    passed, msg = _evaluate_canary(0, expect_min=1, expect_max=None)
    assert not passed
    assert "below" in msg


def test_evaluate_canary_fails_above_max():
    passed, msg = _evaluate_canary(5, expect_min=None, expect_max=0)
    assert not passed
    assert "above" in msg
