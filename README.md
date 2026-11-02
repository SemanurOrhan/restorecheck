# restorecheck

[![CI](https://github.com/SemanurOrhan/restorecheck/actions/workflows/ci.yml/badge.svg)](https://github.com/SemanurOrhan/restorecheck/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Restore a PostgreSQL dump into a throwaway Docker container and check that it actually works.

A backup you have never restored is a hope, not a backup. Most teams take a nightly `pg_dump`
and find out it is truncated, empty or missing a table on the day they need it. `restorecheck`
runs that restore for you on a schedule, checks the result, and tells you when it breaks.

## What it does

1. Starts a fresh `postgres` container and restores your dump into it
2. Compares per-table row counts against a baseline from a known-good run
3. Runs your own SQL "canary" queries (e.g. *orders from the last day exist*, *no orphaned payments*)
4. Prints a JSON report, optionally posts it to Slack, and exits non-zero if anything is wrong
5. Removes the container, whatever the outcome

It is meant for the common case: logical backups made with `pg_dump` (`-Fc` or plain SQL).

> `pg_verifybackup` checks that a base backup matches its manifest. It does not restore anything,
> so it cannot tell you whether the data comes back usable. The two are complementary.

## Quick start

Requirements: Python 3.10+ and a running Docker daemon.

```bash
git clone https://github.com/SemanurOrhan/restorecheck.git
cd restorecheck
pip install -e .

cp config.example.yaml config.yaml    # point dump_path at your dump, define your canaries
restorecheck --config config.yaml --save-baseline   # first run: record row counts of a good backup
restorecheck --config config.yaml                    # every later run: verify
```

Example report (passing run):

```json
{
  "passed": true,
  "row_count_issues": [],
  "canary_results": [
    { "name": "recent_orders_exist", "value": 100, "passed": true, "message": "value=100" },
    { "name": "no_orphan_payments", "value": 0, "passed": true, "message": "value=0" }
  ],
  "row_counts": { "public.orders": 100, "public.payments": 100 },
  "error": null,
  "timestamp": "2026-11-02T20:23:14.220400+00:00"
}
```

When something is off, the run fails and says why:

```json
{
  "passed": false,
  "row_count_issues": [
    "public.orders: row count changed 1000 -> 100 (90.0%, threshold 10.0%)"
  ],
  ...
}
```

## Configuration

```yaml
dump_path: /backups/nightly/shop.dump
dump_format: custom            # custom = pg_dump -Fc, plain = pg_dump -Fp
docker_image: postgres:16      # use the major version you run in production
db_name: restorecheck
baseline_path: ./baseline.json
row_count_threshold_pct: 10.0

canaries:
  - name: recent_orders_exist
    sql: "SELECT count(*) FROM orders WHERE created_at > now() - interval '1 day'"
    expect_min: 1
  - name: no_orphan_payments
    sql: >
      SELECT count(*) FROM payments p
      LEFT JOIN orders o ON p.order_id = o.id
      WHERE o.id IS NULL
    expect_max: 0

slack_webhook_url: null
```

| Key | Default | Description |
| --- | --- | --- |
| `dump_path` | required | Path to the dump file on the machine running `restorecheck` |
| `dump_format` | `custom` | `custom` (restored with `pg_restore`) or `plain` (restored with `psql`) |
| `docker_image` | `postgres:16` | Image used for the throwaway database |
| `db_name` | `restorecheck` | Database the dump is restored into |
| `db_password` | `restorecheck` | Password of the throwaway container; it is only reachable from `127.0.0.1` |
| `baseline_path` | none | JSON file with known-good row counts. Without one, the row-count check is skipped |
| `row_count_threshold_pct` | `10.0` | Allowed change per table, in percent, before the run fails |
| `canaries` | none | List of queries returning one number, checked against `expect_min` / `expect_max` |
| `slack_webhook_url` | none | Incoming-webhook URL; one message per run |

Canary queries must return a single numeric value in the first column of the first row.

## What counts as a failure

The run exits with code `1` when any of these happens:

- the dump cannot be restored: a truncated or corrupt custom dump, or any failing statement in a
  plain SQL dump (reported in the `error` field, not as a crash)
- a table's row count moved more than `row_count_threshold_pct` from the baseline, or a table in
  the baseline is gone
- a canary query returns a value outside its `expect_min` / `expect_max`

Tables that are new since the baseline, and tables with an empty baseline, are not flagged.

## Running it on a schedule

```cron
0 3 * * * cd /opt/restorecheck && restorecheck --config config.yaml >> /var/log/restorecheck.log 2>&1
```

Re-record the baseline (`--save-baseline`) after a deliberate change such as a large data cleanup.

## Notes and limitations

- PostgreSQL only; logical dumps only. WAL archives and physical base backups are not supported.
- Row counts use `count(*)` on every table, which is fine for small and mid-size databases and slow
  on very large ones. Restore time grows with the dump.
- The container is started with the label `restorecheck=1`. If a run is killed hard,
  `docker ps -a --filter label=restorecheck` shows what is left over.
- Canary SQL runs against the restored copy only, but it is still arbitrary SQL from your config file.
  Keep that file as trusted as the rest of your ops tooling.

## Roadmap

- [ ] MySQL / MariaDB support
- [ ] Fetch dumps straight from S3 / GCS
- [ ] Prometheus metrics or a heartbeat ping (healthchecks.io style) for "the check did not run" alerts
- [ ] Compare schema, not just row counts

Ideas and pull requests are welcome, see below.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -m "not integration"   # unit tests, no Docker needed
pytest -m integration         # restores real dumps in Docker, takes a few minutes
```

The integration tests create a small database, dump it in both formats and run the whole tool against
the dumps, including truncated and partly broken ones.

## Contributing

Open an issue before starting anything large. For small fixes, a pull request with a test is plenty.
CI runs `ruff` and the test suite on every PR.

## License

[MIT](LICENSE)
