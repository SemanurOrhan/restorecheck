import pytest

from restorecheck.config import load_config


def test_load_config_minimal(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
dump_path: /tmp/backup.dump
canaries:
  - name: recent_orders
    sql: "SELECT count(*) FROM orders"
    expect_min: 1
"""
    )
    cfg = load_config(str(config_file))
    assert cfg.dump_path == "/tmp/backup.dump"
    assert cfg.dump_format == "custom"
    assert cfg.canaries[0].name == "recent_orders"
    assert cfg.canaries[0].expect_min == 1


def test_load_config_rejects_unknown_field(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("dump_path: /tmp/backup.dump\ntypo_field: oops\n")
    with pytest.raises(ValueError):
        load_config(str(config_file))
