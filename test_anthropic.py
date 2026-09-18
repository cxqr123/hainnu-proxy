"""通过本地代理测试 Anthropic Messages API 兼容层。"""
import json
import os
import sys
import time

# 本机回环绕过系统代理，否则 HTTP_PROXY 会把本地请求送去代理并拿到 403。
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

import httpx

HOST = "http://127.0.0.1:8787"
KEY = "sk-hainnu"
H = {
    "x-api-key": KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
    # 冒烟自检用 low 档思考：桥的全局兜底是 medium，会把小 max_tokens 吃在思考里导致
    # 正文为空（实测）。优先级：请求体 > 请求头 > config.extra_body。
    "X-Reasoning-Effort": "low",
}
MODEL = "claude-sonnet-4-5"  # 故意用 Claude 的模型名，测试别名回退

TOOLS = [
    {
        "name": "get_weather",
        "description": "查询指定城市的天气",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名"}},
            "required": ["city"],
        },
    }
]

ok_all = True


def check(name, cond, extra=""):
    global ok_all
    mark = "PASS" if cond else "FAIL"
    if not cond:
        ok_all = False
    print(f"  [{mark}] {name} {extra}")


def post(path, body, timeout=180):
    return httpx.post(HOST + path, headers=H, json=body, timeout=timeout)


def main():
    print("=" * 66)
    print("[1] 非流式 · 纯文本 + system")
    r = post("/v1/messages", {
        "model": MODEL,
        "max_tokens": 1500,
        "system": "你是一个简洁的助手，回答不超过20字。",
        "messages": [{"role": "user", "content": "海南师范大学在哪个城市？"}],
    })
    print("  HTTP", r.status_code)
    d = r.json()
    print("  resp:", json.dumps(d, ensure_ascii=False)[:400])
    check("状态码 200", r.status_code == 200)
    check("type=message", d.get("type") == "message")
    check("role=assistant", d.get("role") == "assistant")
    check("content是数组", isinstance(d.get("content"), list))
    check("stop_reason=end_turn", d.get("stop_reason") == "end_turn")
    check("usage有input/output", "input_tokens" in (d.get("usage") or {}))
    txt = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    check("正文无 </think> 残留", "</think>" not in txt, repr(txt[:60]))

    print("\n" + "=" * 66)
    print("[2] 非流式 · 工具调用")
    r = post("/v1/messages", {
        "model": MODEL,
        "max_tokens": 1500,
        "tools": TOOLS,
        "messages": [{"role": "user", "content": "海口天气怎么样？"}],
    })
    d = r.json()
    print("  resp:", json.dumps(d, ensure_ascii=False)[:400])
    check("状态码 200", r.status_code == 200)
    check("stop_reason=tool_use", d.get("stop_reason") == "tool_use")
    tu = [b for b in d.get("content", []) if b.get("type") == "tool_use"]
    check("有 tool_use 块", len(tu) == 1)
    if tu:
        check("工具名正确", tu[0].get("name") == "get_weather", str(tu[0].get("name")))
        check("input 是对象", isinstance(tu[0].get("input"), dict), str(tu[0].get("input")))
        check("有 id", bool(tu[0].get("id")))

    print("\n" + "=" * 66)
    print("[3] 非流式 · 工具结果回传（完整 agent 回合）")
    if tu:
        r = post("/v1/messages", {
            "model": MODEL,
            "max_tokens": 1500,
            "tools": TOOLS,
            "messages": [
                {"role": "user", "content": "海口天气怎么样？"},
                {"role": "assistant", "content": d["content"]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": tu[0]["id"], "content": "晴，28度"}
                ]},
            ],
        })
        d2 = r.json()
        print("  resp:", json.dumps(d2, ensure_ascii=False)[:400])
        check("状态码 200", r.status_code == 200)
        t2 = "".join(b.get("text", "") for b in d2.get("content", []) if b.get("type") == "text")
        check("模型用上了工具结果", "28" in t2 or "晴" in t2, repr(t2[:80]))
    else:
        check("跳过（无 tool_use）", False)

    print("\n" + "=" * 66)
    print("[4] 流式 · 纯文本")
    events = []
    t0 = time.time()
    with httpx.stream("POST", HOST + "/v1/messages", headers=H, json={
        "model": MODEL,
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": "用一句话介绍海口"}],
        "stream": True,
    }, timeout=180) as r:
        check("状态码 200", r.status_code == 200)
        buf = ""
        for chunk in r.iter_bytes():
            buf += chunk.decode("utf-8", "replace")
            while "\n\n" in buf:
                ev, buf = buf.split("\n\n", 1)
                for line in ev.splitlines():
                    if line.startswith("data:"):
                        try:
                            events.append(json.loads(line[5:].strip()))
                        except Exception:
                            pass
    types = [e.get("type") for e in events]
    print("  事件序列:", types[:6], "...", types[-4:], f"(共{len(events)}个, {time.time()-t0:.1f}s)")
    check("首个是 message_start", types and types[0] == "message_start")
    check("最后是 message_stop", types and types[-1] == "message_stop")
    check("有 content_block_delta", "content_block_delta" in types)
    check("有 message_delta", "message_delta" in types)
    text = "".join(
        e.get("delta", {}).get("text", "")
        for e in events
        if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta"
    )
    check("正文非空", len(text) > 0, repr(text[:60]))
    check("正文无 </think>", "</think>" not in text)
    starts = [e for e in events if e.get("type") == "content_block_start"]
    stops = [e for e in events if e.get("type") == "content_block_stop"]
    check("block_start/stop 配对", len(starts) == len(stops), f"{len(starts)}/{len(stops)}")

    print("\n" + "=" * 66)
    print("[5] 流式 · 工具调用")
    events = []
    with httpx.stream("POST", HOST + "/v1/messages", headers=H, json={
        "model": MODEL,
        "max_tokens": 1500,
        "tools": TOOLS,
        "messages": [{"role": "user", "content": "查询三亚的天气"}],
        "stream": True,
    }, timeout=180) as r:
        buf = ""
        for chunk in r.iter_bytes():
            buf += chunk.decode("utf-8", "replace")
            while "\n\n" in buf:
                ev, buf = buf.split("\n\n", 1)
                for line in ev.splitlines():
                    if line.startswith("data:"):
                        try:
                            events.append(json.loads(line[5:].strip()))
                        except Exception:
                            pass
    types = [e.get("type") for e in events]
    print("  事件序列:", types[:8], "...", types[-4:], f"(共{len(events)}个)")
    blocks = [e.get("content_block", {}) for e in events if e.get("type") == "content_block_start"]
    check("有 tool_use 块", any(b.get("type") == "tool_use" for b in blocks), str([b.get("type") for b in blocks]))
    partial = "".join(
        e.get("delta", {}).get("partial_json", "")
        for e in events
        if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "input_json_delta"
    )
    check("input_json 可解析", (lambda: (json.loads(partial), True)[1])() if partial.strip() else False, repr(partial[:60]))
    md = [e for e in events if e.get("type") == "message_delta"]
    check("message_delta stop_reason=tool_use", bool(md) and md[-1].get("delta", {}).get("stop_reason") == "tool_use")

    print("\n" + "=" * 66)
    print("[6] count_tokens")
    r = post("/v1/messages/count_tokens", {
        "model": MODEL,
        "messages": [{"role": "user", "content": "你好"}],
    })
    check("状态码 200", r.status_code == 200, str(r.json()))

    print("\n" + "=" * 66)
    print("全部通过 ✅" if ok_all else "存在失败项 ❌")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
