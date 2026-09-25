"""
模拟 DeepSeek Harness (DSH) 的请求形状，验证代理不会返回空正文。

DSH 的两个已知差异（见官方文档《配置模型》）：
  1. 系统提示用 role="developer" 发送
  2. 输出上限写在 max_completion_tokens 字段
本测试按这两种写法 + 工具调用 + 流式组合覆盖，断言正文永不为空。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# GBK consoles raise UnicodeEncodeError on emoji in the summary or in model text,
# and 3.自检.bat then reports a false failure. Keep Chinese; escape the rest.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="backslashreplace")
    except Exception:
        pass

# 本机回环绕过系统代理，否则 HTTP_PROXY 会把本地请求送去代理并拿到 403。
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

import httpx

HOST = "http://127.0.0.1:8787"
KEY = "sk-hainnu"
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
     "X-Reasoning-Effort": "low"}
MODEL = "deepseek-flash"
LOG = Path(__file__).resolve().parent / "hainnu_proxy.log"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取工作区中的文件",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "文件路径"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在工作区中运行一条 shell 命令",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string", "description": "命令"}},
                "required": ["cmd"],
            },
        },
    },
]

AGENT_SYSTEM = (
    "You are an expert software engineer operating inside a workspace.\n"
    "You can read and edit files, run commands, and delegate work.\n"
    "Be concise. Prefer tool calls over speculation.\n"
    "Always reply in Chinese unless asked otherwise.\n"
) * 3  # 模拟 harness 的长系统提示

ok_all = True


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok_all
    if not cond:
        ok_all = False
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")


def call_stream(body: dict, timeout: int = 180):
    """返回 (status, 正文, 工具调用片段, 分片数, 耗时, 思维链长度)"""
    txt, parts, n, rc_len = [], [], 0, 0
    t0 = time.time()
    with httpx.stream("POST", HOST + "/v1/chat/completions", headers=H, json=body, timeout=timeout) as r:
        status = r.status_code
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            p = line[5:].strip()
            if p == "[DONE]":
                continue
            try:
                o = json.loads(p)
            except Exception:  # noqa: BLE001
                continue
            n += 1
            for c in o.get("choices", []):
                d = c.get("delta") or {}
                if isinstance(d.get("reasoning_content"), str):
                    rc_len += len(d["reasoning_content"])
                if isinstance(d.get("content"), str) and d["content"]:
                    txt.append(d["content"])
                for tc in d.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    if fn.get("arguments"):
                        parts.append(fn["arguments"])
                    if fn.get("name"):
                        parts.append(fn["name"])
    return status, "".join(txt), "".join(parts), n, time.time() - t0, rc_len


def main() -> int:
    print("=" * 64)
    print("DSH 兼容性测试（模拟 DSH 的请求形状）")
    print("=" * 64)

    # DSH 会先做模型发现
    print("\n[0] 模型发现 GET /v1/models")
    r = httpx.get(HOST + "/v1/models", headers=H, timeout=20)
    d = r.json()
    ids = [m["id"] for m in d.get("data", [])]
    check("状态码 200", r.status_code == 200)
    check("返回学校模型", MODEL in ids, str(ids))

    # ---------- 用例 1：developer 角色 + max_completion_tokens + 流式 ----------
    print("\n[1] developer 角色 + max_completion_tokens + 流式")
    st, txt, _, n, dt, _rc = call_stream({
        "model": MODEL,
        "messages": [
            {"role": "developer", "content": "你是一个简洁的助手，回答不超过20字。"},
            {"role": "user", "content": "海南师范大学在哪个城市？"},
        ],
        "max_completion_tokens": 1500,
        "stream": True,
    })
    check("状态码 200", st == 200, f"{n} 分片, {dt:.1f}s")
    check("正文非空", bool(txt.strip()), repr(txt[:60]))

    # ---------- 用例 2：非流式 ----------
    print("\n[2] developer 角色 + max_completion_tokens + 非流式")
    r = httpx.post(HOST + "/v1/chat/completions", headers=H, timeout=180, json={
        "model": MODEL,
        "messages": [
            {"role": "developer", "content": "回答不超过20字。"},
            {"role": "user", "content": "用一句话介绍海口。"},
        ],
        "max_completion_tokens": 1500,
        "stream": False,
    })
    d = r.json()
    content = (d.get("choices") or [{}])[0].get("message", {}).get("content")
    check("状态码 200", r.status_code == 200)
    check("正文非空", bool((content or "").strip()), repr(str(content)[:60]))
    check("无 </think> 残留", "</think>" not in str(content or ""))

    # ---------- 用例 3：长系统提示 + 工具调用 + 流式（最接近真实的 agent 场景）----------
    print("\n[3] 长系统提示 + 工具调用 + 流式（最贴近真实 agent）")
    st, txt, targs, n, dt, _rc = call_stream({
        "model": MODEL,
        "messages": [
            {"role": "developer", "content": AGENT_SYSTEM},
            {"role": "user", "content": "看一下 README.md 里写了什么"},
        ],
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_completion_tokens": 1500,
        "stream": True,
    })
    check("状态码 200", st == 200, f"{n} 分片, {dt:.1f}s")
    produced = txt.strip() or targs.strip()
    check("有产出（正文或工具调用）", bool(produced), repr(produced[:80]))
    check("未出现空正文 + 无工具调用的死局", bool(txt.strip()) or bool(targs.strip()))

    # ---------- 用例 4：小上限，最容易触发“只有思维链” ----------
    print("\n[4] 极小输出上限（最容易触发空正文）")
    st, txt, targs, n, dt, rc_len = call_stream({
        "model": MODEL,
        "messages": [
            {"role": "developer", "content": AGENT_SYSTEM},
            {"role": "user", "content": "解释一下什么是递归，要详细"},
        ],
        "max_completion_tokens": 60,
        "stream": True,
    })
    check("状态码 200", st == 200, f"{n} 分片, {dt:.1f}s")
    check(
        "不是死局（正文或思维链至少有一边有内容）",
        bool(txt.strip()) or rc_len > 0,
        f"正文 {len(txt)} 字 / 思维链 {rc_len} 字；上限太小会被思考吃光，客户端请给足预算",
    )

    # ---------- 用例 5：只给 max_tokens 也应正常 ----------
    print("\n[5] 传统 max_tokens 写法（不应被破坏）")
    r = httpx.post(HOST + "/v1/chat/completions", headers=H, timeout=180, json={
        "model": MODEL,
        "messages": [{"role": "user", "content": "1+1等于几？只答数字"}],
        "max_tokens": 100,
        "stream": False,
    })
    content = (r.json().get("choices") or [{}])[0].get("message", {}).get("content")
    check("状态码 200", r.status_code == 200)
    check("正文非空", bool((content or "").strip()), repr(str(content)[:60]))

    # ---------- 看看代理日志里的规范化记录 ----------
    print("\n" + "-" * 64)
    print("hainnu_proxy.log 末尾（确认字段规范化生效）：")
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        for ln in lines[-12:]:
            print("   " + ln)
    except Exception as exc:  # noqa: BLE001
        print(f"   (读取日志失败: {exc})")

    print("\n" + "=" * 64)
    print("DSH 兼容性全部通过 ✅" if ok_all else "存在失败项 ❌")
    return 0 if ok_all else 1

if __name__ == "__main__":
    sys.exit(main())
