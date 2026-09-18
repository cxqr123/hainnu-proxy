"""本地代理自检：OpenAI 接口侧。Anthropic 侧见 test_anthropic.py。"""
import json
import os
import sys
import time

os.environ["NO_PROXY"] = os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

import httpx

HOST = "http://127.0.0.1:8787"
KEY = "sk-hainnu"
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
     "X-Reasoning-Effort": "low"}

ok_all = True


def check(name, cond, extra=""):
    global ok_all
    if not cond:
        ok_all = False
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")


def main():
    print("=" * 62)
    print("本地代理自检 · OpenAI 接口")
    print("=" * 62)

    print("\n[0] 服务状态")
    try:
        d = httpx.get(HOST + "/health", timeout=15).json()
        check("health ok", d.get("ok") is True)
        models = d.get("models") or []
        check("拿到模型列表", bool(models), str(models))
        # /health 不再回传 token_len（长度属无关信息），ok=True 即代表令牌已成功读取
        check("令牌已加载", d.get("ok") is True and bool(models))
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] 连不上 {HOST}/health -> {exc}")
        print("\n  请先双击 2.启动代理.bat 再自检。")
        return 1

    print("\n[1] GET /v1/models")
    r = httpx.get(HOST + "/v1/models", headers=H, timeout=20)
    d = r.json()
    check("状态码 200", r.status_code == 200)
    check("object=list", d.get("object") == "list")
    ids = [m["id"] for m in d.get("data", [])]
    check("有模型 id", bool(ids), str(ids))

    print("\n[2] 非流式对话（别名 deepseek-chat）")
    t0 = time.time()
    r = httpx.post(HOST + "/v1/chat/completions", headers=H, timeout=180, json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "1+1等于几？只回答数字"}],
        "stream": False,
    })
    d = r.json()
    check("状态码 200", r.status_code == 200, f"{time.time()-t0:.1f}s")
    content = d["choices"][0]["message"].get("content")
    check("正文非空", bool(content), repr(content)[:60])
    check("无 </think> 残留", "</think>" not in str(content))

    print("\n[3] 流式对话")
    txt, done, n = [], False, 0
    t0 = time.time()
    with httpx.stream("POST", HOST + "/v1/chat/completions", headers=H, timeout=180, json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "用一句话介绍海口"}],
        "stream": True,
    }) as r:
        check("状态码 200", r.status_code == 200)
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            p = line[5:].strip()
            if p == "[DONE]":
                done = True
                continue
            try:
                o = json.loads(p)
            except Exception:  # noqa: BLE001
                continue
            n += 1
            for c in o.get("choices", []):
                v = (c.get("delta") or {}).get("content")
                if isinstance(v, str):
                    txt.append(v)
    joined = "".join(txt)
    check("收到多个分片", n > 1, f"{n} 个, {time.time()-t0:.1f}s")
    check("收到 [DONE]", done)
    check("正文非空", bool(joined), repr(joined)[:60])
    check("无 </think> 残留", "</think>" not in joined)

    print("\n[4] 未知模型名回退")
    r = httpx.post(HOST + "/v1/chat/completions", headers=H, timeout=120, json={
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    })
    check("状态码 200", r.status_code == 200)
    # 不断言写死的模型名：学校随时可能改 id（学校曾把 deepseek-ai/DeepSeek-V4-Flash
    # 改成了 deepseek-flash）。只要求回退结果确实是上游列表里的一个真实模型。
    _fallback = r.json().get("model", "")
    _upstream_ids = [m.get("id") for m in httpx.get(
        HOST + "/v1/models", headers=H, timeout=20).json().get("data", [])]
    check("回退到上游真实模型", _fallback in _upstream_ids, f"{_fallback} (上游: {_upstream_ids})")

    print("\n[5] 错误 key 应被拒绝")
    r = httpx.get(HOST + "/v1/models", headers={"Authorization": "Bearer wrong"}, timeout=20)
    check("返回 401", r.status_code == 401, str(r.status_code))

    print("\n" + "=" * 62)
    print("OpenAI 侧全部通过 ✅" if ok_all else "存在失败项 ❌")
    return 0 if ok_all else 1

if __name__ == "__main__":
    sys.exit(main())
