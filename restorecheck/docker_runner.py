from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def start_postgres_container(image: str, password: str) -> tuple[str, int]:
    port = _free_port()
    result = subprocess.run(
        [
            "docker", "run", "-d", "--rm",
            "--label", "restorecheck=1",
            "-e", f"POSTGRES_PASSWORD={password}",
            "-p", f"127.0.0.1:{port}:5432",
            image,
        ],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip(), port


def wait_until_ready(container_id: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            # tcp check: the init-time server only listens on the unix socket
            ["docker", "exec", container_id, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
            check=False, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError(f"Postgres container {container_id} did not become ready in {timeout}s")


def create_database(container_id: str, db_name: str) -> None:
    subprocess.run(
        ["docker", "exec", container_id, "createdb", "-U", "postgres", db_name],
        capture_output=True, text=True, check=True,
    )


def restore_dump(container_id: str, dump_path: str, db_name: str, dump_format: str) -> None:
    dump_name = Path(dump_path).name
    dest = f"/tmp/{dump_name}"
    subprocess.run(["docker", "cp", dump_path, f"{container_id}:{dest}"], check=True)

    if dump_format == "plain":
        cmd = [
            "docker", "exec", container_id, "psql",
            "-U", "postgres", "-d", db_name, "-v", "ON_ERROR_STOP=1", "-f", dest,
        ]
    elif dump_format == "custom":
        cmd = [
            "docker", "exec", container_id, "pg_restore",
            "-U", "postgres", "-d", db_name, "--no-owner", "--exit-on-error", dest,
        ]
    else:
        raise ValueError(f"Unknown dump_format: {dump_format!r} (expected 'custom' or 'plain')")

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Restore failed:\n{result.stderr}")


def stop_container(container_id: str) -> None:
    subprocess.run(["docker", "stop", container_id], check=False, capture_output=True, text=True)
