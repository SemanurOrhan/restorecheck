# restorecheck

[![CI](https://github.com/SemanurOrhan/restorecheck/actions/workflows/ci.yml/badge.svg)](https://github.com/SemanurOrhan/restorecheck/actions/workflows/ci.yml)

Most teams back up their Postgres database with `pg_dump` and never actually restore it until
the day they need to — by which point they find out the backup is empty, corrupt, or missing a
table. `pg_verifybackup` only checks file integrity, and tools like Probavi focus on
`pgBackRest`/WAL-based physical backups. **restorecheck** fills the gap for the common case: a
plain `pg_dump` file that nobody has test-restored.

It restores your dump into a throwaway Docker container, runs sanity checks against it, and
reports pass/fail — so a broken backup gets caught on a schedule, not during an outage.

## What it checks

- **Row counts** for every table, compared against a saved baseline (flags drops/spikes past a
  configurable threshold)
- **Canary queries** you define in YAML — e.g. "orders from the last 24h exist" or "no orphaned
  payment rows"

## Quickstart

```bash
pip install -e .
cp config.example.yaml config.yaml   # edit dump_path, canaries, etc.

# first run: establish a baseline
restorecheck --config config.yaml --save-baseline

# subsequent runs: verify against that baseline
restorecheck --config config.yaml
```

A run **fails** (exit code `1`) if the dump cannot be restored at all (truncated/corrupt custom
dump, or any failing statement in a plain `.sql` dump), a table's row count drifts past the
threshold, or a canary query is out of range. Restore failures are reported like any other
failure (JSON `error` field + Slack message), not as a crash. Exit code is `0` on pass — wire it
into cron:

```cron
0 3 * * * cd /opt/restorecheck && restorecheck --config config.yaml >> /var/log/restorecheck.log 2>&1
```

Set `slack_webhook_url` in the config to get a Slack notification on every run.

## Requirements

- Docker (the host running restorecheck needs access to the Docker daemon)
- Python 3.10+

## v1 scope

Deliberately narrow:

- Logical dumps only (`pg_dump -Fc` or `-Fp`), not WAL-based/PITR backups
- PostgreSQL only
- No dashboard — CLI output + JSON report + optional Slack webhook
- Tuned for small/mid-size databases; no special handling for very large restores

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -m "not integration"   # fast unit tests, no Docker needed
pytest -m integration         # real restores in Docker (needs a running Docker daemon)
```

The throwaway containers are started with the label `restorecheck=1` and published on
`127.0.0.1` only; `docker ps -a --filter label=restorecheck` shows any that were left behind.
