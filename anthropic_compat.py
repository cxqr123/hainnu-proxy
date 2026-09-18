"""
Anthropic Messages API <-> OpenAI Chat Completions 双向转换。

让 Claude Code、OpenCode、Cline 等只说 Anthropic 协议的智能体 harness
也能用上学校的 DeepSeek。

支持：文本、多轮、system、工具调用（tool_use / tool_result）、流式、采样参数。
"""

from __future__ import annotations

import json
import uuid

FINISH_MAP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "stop_sequence",
}


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def _new_id() -> str:
    return "msg_" + uuid.uuid4().hex[:24]


def _schema(t: dict) -> dict:
    """Anthropic 的 input_schema 就是 OpenAI 的 parameters。"""
    return t.get("input_schema") or {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# 请求：Anthropic -> OpenAI
# ---------------------------------------------------------------------------
def to_openai_request(body: dict, resolve_model) -> dict:
    sys_parts: list[str] = []
    sys_raw = body.get("system")
    if isinstance(sys_raw, str):
        sys_parts.append(sys_raw)
    elif isinstance(sys_raw, list):
        for b in sys_raw:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                sys_parts.append(b["text"])

    msgs: list[dict] = []
    if sys_parts:
        msgs.append({"role": "system", "content": "\n".join(sys_parts)})

    for m in body.get("messages") or []:
        role = m.get("role", "user")
        c = m.get("content")

        if isinstance(c, str):
            msgs.append({"role": role, "content": c})
            continue
        if not isinstance(c, list):
            continue

        texts: list[str] = []
        tool_calls: list[dict] = []
        tool_results: list[dict] = []

        for b in c:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "text":
                if b.get("text"):
                    texts.append(b["text"])
            elif t == "tool_use":
                tool_calls.append(
                    {
                        "id": b.get("id") or ("toolu_" + uuid.uuid4().hex[:20]),
                        "type": "function",
                        "function": {
                            "name": b.get("name") or "",
                            "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False),
                        },
                    }
                )
            elif t == "tool_result":
                content = b.get("content")
                if isinstance(content, list):
                    content = "".join(
                        x.get("text", "") for x in content if isinstance(x, dict)
                    )
                if content is None:
                    content = ""
                elif not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                tool_results.append(
                    {"role": "tool", "tool_call_id": b.get("tool_use_id"), "content": content}
                )
            # thinking / redacted_thinking 直接丢弃（OpenAI 侧没有对应位置）

        if role == "assistant":
            msg: dict = {"role": "assistant", "content": "\n".join(texts)}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            msgs.append(msg)
        else:
            if texts:
                msgs.append({"role": role, "content": "\n".join(texts)})
            msgs.extend(tool_results)

    out: dict = {
        "model": resolve_model(str(body.get("model") or "")),
        "messages": msgs,
        "stream": bool(body.get("stream")),
    }

    if body.get("max_tokens") is not None:
        out["max_tokens"] = int(body["max_tokens"])
    else:
        out["max_tokens"] = 4096  # Anthropic 必填，OpenAI 可选

    for src, dst in (("temperature", "temperature"), ("top_p", "top_p")):
        if body.get(src) is not None:
            out[dst] = body[src]
    if body.get("stop_sequences"):
        out["stop"] = body["stop_sequences"]

    tools = body.get("tools")
    if tools:
        out["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.get("name"),
                    "description": t.get("description") or "",
                    "parameters": _schema(t),
                },
            }
            for t in tools
            if isinstance(t, dict)
        ]
        tc = body.get("tool_choice")
        if isinstance(tc, dict):
            kind = tc.get("type")
            if kind == "auto":
                out["tool_choice"] = "auto"
            elif kind == "any":
                out["tool_choice"] = "required"
            elif kind == "tool":
                out["tool_choice"] = {
                    "type": "function",
                    "function": {"name": tc.get("name")},
                }
            elif kind == "none":
                out["tool_choice"] = "none"
        elif isinstance(tc, str):
            out["tool_choice"] = tc

    return out


# ---------------------------------------------------------------------------
# 响应：OpenAI -> Anthropic（非流式）
# ---------------------------------------------------------------------------
def to_anthropic_response(data: dict, model: str, emit_thinking: bool = False) -> dict:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content: list[dict] = []

    if emit_thinking and msg.get("reasoning_content"):
        content.append(
            {"type": "thinking", "thinking": msg["reasoning_content"], "signature": ""}
        )
    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})

    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            inp = json.loads(fn.get("arguments") or "{}")
        except Exception:  # noqa: BLE001
            inp = {}
        content.append(
            {"type": "tool_use", "id": tc.get("id"), "name": fn.get("name"), "input": inp}
        )

    if not content:
        content = [{"type": "text", "text": ""}]

    usage = data.get("usage") or {}
    return {
        "id": _new_id(),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": FINISH_MAP.get(choice.get("finish_reason"), "end_turn"),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0) or 0,
            "output_tokens": usage.get("completion_tokens", 0) or 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


# ---------------------------------------------------------------------------
# 响应：OpenAI 流 -> Anthropic 流
# ---------------------------------------------------------------------------
class AnthropicStreamer:
    """把 OpenAI 的 SSE chunk 序列翻译成 Anthropic 的事件序列。"""

    def __init__(self, model: str, emit_thinking: bool = False):
        self.model = model
        self.emit_thinking = emit_thinking
        self.id = _new_id()
        self.idx = -1
        self.open_kind: str | None = None
        self.cur_tool_idx: int | None = None
        self.usage_in = 0
        self.usage_out = 0
        self.stop_reason = "end_turn"
        self.started = False

    # -- 内部 ---------------------------------------------------------------
    def _start(self) -> bytes:
        self.started = True
        return _sse(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": self.id,
                    "type": "message",
                    "role": "assistant",
                    "model": self.model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": self.usage_in, "output_tokens": 1},
                },
            },
        )

    def _switch(self, out: list, kind: str, block: dict | None = None) -> None:
        if self.open_kind is not None:
            out.append(_sse("content_block_stop", {"type": "content_block_stop", "index": self.idx}))
        self.idx += 1
        self.open_kind = kind
        if block is None:
            block = {"type": "text", "text": ""} if kind == "text" else {"type": "thinking", "thinking": "", "signature": ""}
        out.append(
            _sse(
                "content_block_start",
                {"type": "content_block_start", "index": self.idx, "content_block": block},
            )
        )

    # -- 主流程 -------------------------------------------------------------
    def feed(self, chunk: dict) -> bytes:
        out: list[bytes] = []
        if not self.started:
            u = chunk.get("usage") or {}
            if u.get("prompt_tokens"):
                self.usage_in = u["prompt_tokens"]
            out.append(self._start())

        for ch in chunk.get("choices") or []:
            d = ch.get("delta") or {}

            rc = d.get("reasoning_content")
            if self.emit_thinking and isinstance(rc, str) and rc:
                if self.open_kind != "thinking":
                    self._switch(out, "thinking")
                out.append(
                    _sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": self.idx,
                            "delta": {"type": "thinking_delta", "thinking": rc},
                        },
                    )
                )

            txt = d.get("content")
            if isinstance(txt, str) and txt:
                if self.open_kind != "text":
                    self._switch(out, "text")
                out.append(
                    _sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": self.idx,
                            "delta": {"type": "text_delta", "text": txt},
                        },
                    )
                )

            for tc in d.get("tool_calls") or []:
                ti = tc.get("index", 0)
                fn = tc.get("function") or {}
                if self.open_kind != "tool" or ti != self.cur_tool_idx:
                    self.cur_tool_idx = ti
                    self._switch(
                        out,
                        "tool",
                        {
                            "type": "tool_use",
                            "id": tc.get("id") or ("toolu_" + uuid.uuid4().hex[:20]),
                            "name": fn.get("name") or "",
                            "input": {},
                        },
                    )
                if fn.get("arguments"):
                    out.append(
                        _sse(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": self.idx,
                                "delta": {"type": "input_json_delta", "partial_json": fn["arguments"]},
                            },
                        )
                    )

            fr = ch.get("finish_reason")
            if fr:
                self.stop_reason = FINISH_MAP.get(fr, "end_turn")

        u = chunk.get("usage") or {}
        if u.get("completion_tokens") is not None:
            self.usage_out = u["completion_tokens"]
        if u.get("prompt_tokens"):
            self.usage_in = u["prompt_tokens"]

        return b"".join(out)

    def finish(self) -> bytes:
        out: list[bytes] = []
        if not self.started:
            out.append(self._start())
        if self.idx < 0:  # 至少给一个空的 text 块，部分客户端要求非空 content
            self._switch(out, "text")
        if self.open_kind is not None:
            out.append(_sse("content_block_stop", {"type": "content_block_stop", "index": self.idx}))
            self.open_kind = None
        out.append(
            _sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": self.stop_reason, "stop_sequence": None},
                    "usage": {"output_tokens": self.usage_out},
                },
            )
        )
        out.append(_sse("message_stop", {"type": "message_stop"}))
        return b"".join(out)
