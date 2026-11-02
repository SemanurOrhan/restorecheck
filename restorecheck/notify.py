from __future__ import annotations

import json
import urllib.request


def send_slack(webhook_url: str, text: str) -> None:
    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=data, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=10)
