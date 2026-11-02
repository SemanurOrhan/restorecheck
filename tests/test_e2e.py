import json
import shutil
import subprocess

import pytest
import yaml

from restorecheck import cli, docker_runner

pytestmark = pytest.mark.integration

SEED_SQL = """
CREATE TABLE orders (id serial PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(), total numeric);
CREATE TABLE payments (id serial PRIMARY KEY, order_id int REFERENCES orders(id), amount numeric);
INSERT INTO orders (total) SELECT g FROM generate_series(1, 100) g;
INSERT INTO payments (order_id, amount) SELECT id, total FROM orders;
"""

CANARIES = [
    {
        "name": "recent_orders_exist",
        "sql": "SELECT count(*) FROM orders WHERE created_at > now() - interval '1 day'",
        "expect_min": 1,
    },
    {
        "name": "no_orphan_payments",
        "sql": (
            "SELECT count(*) FROM payments p "
            "LEFT JOIN orders o ON p.order_id = o.id WHERE o.id IS NULL"
        ),
        "expect_max": 0,
    },
]


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], check=False, capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def dumps(tmp_path_factory):
    if not _docker_available():
        pytest.skip("Docker is not available")

    out = tmp_path_factory.mktemp("dumps")
    container_id, _ = docker_runner.start_postgres_container("postgres:16", "pw")
    try:
        docker_runner.wait_until_ready(container_id)
        subprocess.run(
            ["docker", "exec", "-i", container_id, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1"],
            input=SEED_SQL, text=True, check=True, capture_output=True,
        )
        for name, flag in (("shop.dump", "-Fc"), ("shop.sql", "-Fp")):
            subprocess.run(
                ["docker", "exec", container_id, "pg_dump", "-U", "postgres", flag, "postgres",
                 "-f", f"/tmp/{name}"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["docker", "cp", f"{container_id}:/tmp/{name}", str(out / name)],
                check=True, capture_output=True,
            )
    finally:
        docker_runner.stop_container(container_id)
    return out


def _run(tmp_path, capsys, dump_path, dump_format, baseline=None, extra_args=()):
    baseline_path = tmp_path / "baseline.json"
    if baseline is not None:
        baseline_path.write_text(json.dumps(baseline))
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({
        "dump_path": str(dump_path),
        "dump_format": dump_format,
        "baseline_path": str(baseline_path),
        "canaries": CANARIES,
    }))
    code = cli.main(["--config", str(config_path), *extra_args])
    return code, capsys.readouterr().out


@pytest.mark.parametrize("name,fmt", [("shop.dump", "custom"), ("shop.sql", "plain")])
def test_valid_dump_passes(dumps, tmp_path, capsys, name, fmt):
    code, out = _run(tmp_path, capsys, dumps / name, fmt)
    result = json.loads(out)
    assert code == 0
    assert result["passed"] is True
    assert result["row_counts"] == {"public.orders": 100, "public.payments": 100}


def test_save_baseline_then_detect_drift(dumps, tmp_path, capsys):
    code, _ = _run(tmp_path, capsys, dumps / "shop.dump", "custom", extra_args=["--save-baseline"])
    assert code == 0
    baseline = json.loads((tmp_path / "baseline.json").read_text())
    assert baseline == {"public.orders": 100, "public.payments": 100}

    drifted = {**baseline, "public.orders": 1000}
    code, out = _run(tmp_path, capsys, dumps / "shop.dump", "custom", baseline=drifted)
    result = json.loads(out)
    assert code == 1
    assert "public.orders" in result["row_count_issues"][0]


def test_truncated_custom_dump_fails(dumps, tmp_path, capsys):
    bad = tmp_path / "bad.dump"
    bad.write_bytes((dumps / "shop.dump").read_bytes()[:2000])
    code, out = _run(tmp_path, capsys, bad, "custom")
    result = json.loads(out)
    assert code == 1
    assert result["passed"] is False
    assert result["error"]


def test_plain_dump_with_failing_statement_fails(dumps, tmp_path, capsys):
    sql = (dumps / "shop.sql").read_text(encoding="utf-8")
    marker = "CREATE TABLE public.payments"
    assert marker in sql
    bad = tmp_path / "bad.sql"
    bad.write_text(sql.replace(marker, f"INSERT INTO nonexistent_table VALUES (1);\n{marker}", 1),
                   encoding="utf-8")
    code, out = _run(tmp_path, capsys, bad, "plain")
    result = json.loads(out)
    assert code == 1
    assert "nonexistent_table" in result["error"]
