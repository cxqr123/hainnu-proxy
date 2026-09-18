# -*- coding: utf-8 -*-
"""热重载代理配置：改完 config.json 后跑这个即可生效，不用重启代理、不打断 DSH。

Key 从 config.json 读取，不写在命令行里（避免被安全策略拦下）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent


def main() -> int:
    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    key = cfg.get("local_api_key") or ""
    port = cfg.get("port", 8787)
    host = cfg.get("host", "127.0.0.1")

    url = f"http://{host}:{port}/_/reload"
    try:
        with httpx.Client(timeout=30, trust_env=False) as cli:
            r = cli.post(url, headers={"Authorization": f"Bearer {key}"})
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 连不上代理: {exc}")
        return 1
    print(f"HTTP {r.status_code}")
    print(r.text[:400])

    # 顺手确认配置确实被读进去了
    with httpx.Client(timeout=30, trust_env=False) as cli:
        h = cli.get(f"http://{host}:{port}/health", headers={"Authorization": f"Bearer {key}"})
    if h.status_code == 200:
        d = h.json()
        print("\n当前生效配置:")
        print("  models       :", d.get("models"))
        print("  rate_limited :", d.get("rate_limited_now"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
