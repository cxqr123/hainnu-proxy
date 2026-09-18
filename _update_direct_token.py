"""把学校登录 JWT 写进 opencode 配置里的「直连」供应商（`hainnu-direct`）。

为什么要单独一个脚本：
  opencode 的自定义 provider **只能在 options.apiKey 里内联密钥**，官方文档不支持
  `{env:VAR}` / `{file:...}` 这类取值语法（查过 providers 文档）。所以直连时令牌一定
  落在配置文件里，失效后需要有人帮它更新一下 —— 就是这个脚本的职责。

它做什么：
  1. 读项目里的 `token.txt`（**DPAPI 加密**），用 `token_codec` 解出明文 JWT；
  2. 在 `~/.config/opencode/opencode.jsonc` 里**定点替换** `hainnu-direct` 块内的 `apiKey`；
  3. **先备份**（带时间戳），改完**校验 JSONC 仍能解析**，不过就自动回滚。

⚠️ 必须是「定点文本替换」，**不能**用 json 反序列化再 dump —— 那个配置文件里有大量注释，
   一序列化就全没了。

用法：
    python _update_direct_token.py                 # 默认改 ~/.config/opencode/opencode.jsonc
    python _update_direct_token.py --show          # 只看当前写的是什么（打码），不改
    python _update_direct_token.py --config <路径>  # 指定别的配置文件
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import token_codec  # noqa: E402

PROVIDER = "hainnu-direct"
DEFAULT_CONFIG = Path(os.path.expanduser("~/.config/opencode/opencode.jsonc"))


# --------------------------------------------------------------------------- 读令牌
def load_jwt() -> str:
    tf = BASE / "token.txt"
    if not tf.exists():
        raise SystemExit(f"找不到 {tf}。请先双击「1.获取令牌.bat」登录学校站点。")
    payload = tf.read_text(encoding="utf-8").strip()
    if not payload:
        raise SystemExit("token.txt 是空的。请先双击「1.获取令牌.bat」。")
    tok = token_codec.decrypt(payload)
    if not tok:
        raise SystemExit(
            "token.txt 是加密的，但在本机当前用户下解不开（可能文件来自别的电脑/别的用户）。\n"
            "请重新双击「1.获取令牌.bat」拿一份新的。"
        )
    tok = tok.replace("Bearer ", "").strip()
    if tok.count(".") != 2:
        raise SystemExit(f"解出来的东西不像 JWT（端点数量 {tok.count('.')}）。")
    return tok


def mask(tok: str) -> str:
    return f"{tok[:6]}…{tok[-4:]}（长度 {len(tok)}）"


# --------------------------------------------------------------------------- JSONC 工具
def find_block(text: str, key: str):
    """返回 key 对应对象的花括号区间 [start, end)。扫描时**跳过字符串与注释**。"""
    m = re.search(r'"' + re.escape(key) + r'"\s*:\s*\{', text)
    if not m:
        return None
    start = m.end() - 1
    depth = 0
    i = start
    in_str = False
    esc = False
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":      # 行注释
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":      # 块注释
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (start, i + 1)
        i += 1
    return None


def strip_jsonc(text: str) -> str:
    """把 JSONC 变成 JSON：去注释、去尾逗号。字符串内容原样保留。"""
    out = []
    i = 0
    n = len(text)
    in_str = False
    esc = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def current_key(text: str):
    rng = find_block(text, PROVIDER)
    if not rng:
        return None, None
    seg = text[rng[0]:rng[1]]
    m = re.search(r'"apiKey"\s*:\s*"([^"]*)"', seg)
    return (m.group(1) if m else None), rng


# --------------------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--show", action="store_true", help="只显示当前的 apiKey（打码），不写入")
    args = ap.parse_args()

    cfg = Path(os.path.expanduser(args.config))
    if not cfg.exists():
        raise SystemExit(f"找不到配置文件：{cfg}")

    text = cfg.read_text(encoding="utf-8")
    old, rng = current_key(text)
    if rng is None:
        raise SystemExit(
            f"在 {cfg} 里找不到 provider 「{PROVIDER}」的对象块。\n"
            "请确认直连供应商的配置已经加进去了（见项目 README）。"
        )
    if args.show:
        print(f"配置文件：{cfg}")
        print(f"provider：{PROVIDER}")
        print(f"当前 apiKey：{mask(old) if old else '（空）'}")
        return 0

    jwt = load_jwt()
    if old == jwt:
        print("令牌没变化 —— 配置里已经是当前这一枚，未做修改。")
        print(f"（{mask(jwt)}）")
        return 0

    new_text = text[:rng[0]] + re.sub(
        r'("apiKey"\s*:\s*")[^"]*(")',
        lambda m: m.group(1) + jwt + m.group(2),
        text[rng[0]:rng[1]], count=1,
    ) + text[rng[1]:]

    # 写前先验证：JSONC 必须仍能解析
    try:
        json.loads(strip_jsonc(new_text))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"新内容 JSONC 解析不过，已放弃写入：{exc}")

    bak = cfg.with_name(cfg.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(cfg, bak)
    tmp = cfg.with_name(cfg.name + ".tmp")
    try:
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, cfg)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:  # noqa: BLE001
                pass

    # 回读校验（值 + 仍可解析）
    check = cfg.read_text(encoding="utf-8")
    got, _ = current_key(check)
    ok_parse = True
    try:
        json.loads(strip_jsonc(check))
    except Exception:  # noqa: BLE001
        ok_parse = False
    if got != jwt or not ok_parse:
        shutil.copy2(bak, cfg)
        raise SystemExit("写入后校验失败，已回滚。请把 opencode.jsonc 发我看一下。")

    print("✅ 已更新直连令牌")
    print(f"   配置文件：{cfg}")
    print(f"   provider：{PROVIDER}")
    print(f"   旧：{mask(old) if old else '（空）'}")
    print(f"   新：{mask(jwt)}")
    print(f"   备份：{bak.name}")
    print()
    print("   重启 opencode 后生效（改的是它启动时读的配置文件）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
