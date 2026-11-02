from __future__ import annotations

from .config import Canary


def connect(port: int, password: str, db_name: str):
    import psycopg

    return psycopg.connect(
        host="localhost", port=port, user="postgres", password=password, dbname=db_name
    )


def get_row_counts(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT schemaname, relname FROM pg_stat_user_tables ORDER BY schemaname, relname"
        )
        tables = cur.fetchall()

    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for schema, table in tables:
            cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
            counts[f"{schema}.{table}"] = cur.fetchone()[0]
    return counts


def compare_row_counts(
    current: dict[str, int], baseline: dict[str, int], threshold_pct: float
) -> list[str]:
    issues: list[str] = []
    for table in sorted(set(current) | set(baseline)):
        cur = current.get(table)
        base = baseline.get(table)
        if cur is None:
            issues.append(f"{table}: present in baseline but missing from restored database")
            continue
        if base is None or base == 0:
            continue
        delta_pct = abs(cur - base) / base * 100
        if delta_pct > threshold_pct:
            issues.append(
                f"{table}: row count changed {base} -> {cur} "
                f"({delta_pct:.1f}%, threshold {threshold_pct}%)"
            )
    return issues


def _evaluate_canary(
    value: int, expect_min: int | None, expect_max: int | None
) -> tuple[bool, str]:
    if expect_min is not None and value < expect_min:
        return False, f"value={value} is below expect_min={expect_min}"
    if expect_max is not None and value > expect_max:
        return False, f"value={value} is above expect_max={expect_max}"
    return True, f"value={value}"


def run_canary_queries(conn, canaries: list[Canary]) -> list[dict]:
    results = []
    with conn.cursor() as cur:
        for canary in canaries:
            cur.execute(canary.sql)
            value = cur.fetchone()[0]
            passed, message = _evaluate_canary(value, canary.expect_min, canary.expect_max)
            results.append({"name": canary.name, "value": value, "passed": passed, "message": message})
    return results
