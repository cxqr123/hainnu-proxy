"""
一键获取 chat.hainnu.edu.cn (Open WebUI) 的登录令牌。

用法：双击「1.获取令牌.bat」，会弹出一个 Chrome 窗口。
      在学校统一身份认证页面登录后（可用 CAS 已登录态直接跳过），
      本脚本自动抓取 JWT 并写入 token.txt，然后自动关闭窗口。

说明：
  * 使用独立的用户数据目录 chrome-profile/，不会影响你正在用的 Chrome。
  * 登录状态会保存在 chrome-profile/ 里，下次再跑通常无需重新登录。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import token_codec          # token 落盘加密（Windows DPAPI）

BASE = Path(__file__).resolve().parent
TOKEN_FILE = BASE / "token.txt"
USER_NAME_FILE = BASE / "user_name.txt"
PROFILE = BASE / "chrome-profile"
SITE = "https://chat.hainnu.edu.cn/"
TIMEOUT_S = 600
# 备用链路开关：--legacy 时只用 chat 稳定取令牌，不再访问网上服务大厅抓姓名
LEGACY = "--legacy" in sys.argv

# 保证中文输出不乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def say(msg: str) -> None:
    print(msg, flush=True)


def grab(page) -> str:
    """从当前页面的 localStorage / cookie 里取 JWT。"""
    try:
        val = page.evaluate("() => { try { return localStorage.getItem('token') || '' } catch (e) { return '' } }")
        if val and val.startswith("eyJ"):
            return val
    except Exception:  # noqa: BLE001
        pass
    try:
        for ck in page.context.cookies():
            if ck.get("name") == "token" and str(ck.get("value", "")).startswith("eyJ"):
                if "hainnu" in (ck.get("domain") or ""):
                    return ck["value"]
    except Exception:  # noqa: BLE001
        pass
    return ""


def grab_user_name(page) -> str:
    """登录后从浏览器 localStorage 抓 Open WebUI 的 user 对象里的姓名；取不到返回空串。

    JWT 载荷里只有用户 id，姓名存在登录后的 localStorage['user'] 中。
    """
    try:
        raw = page.evaluate(
            "() => { try { return localStorage.getItem('user') || '' } catch (e) { return '' } }"
        )
        if raw:
            obj = json.loads(raw)
            n = obj.get("name") or obj.get("username") or obj.get("nickname") or ""
            if isinstance(n, str) and n:
                return n.strip()[:32]
    except Exception:  # noqa: BLE001
        pass
    return ""


def grab_jw_name(page) -> str:
    """从教务系统（zfjw.hainnu.edu.cn，正方教务）抓真实姓名。

    教务与超星、chat 共用同一学校统一认证 CAS 会话；登录 chat 后该会话仍在浏览器内，
    直接进入教务首页即自动免登录。姓名优先从页面 DOM / 用户信息接口取。
    """
    _DOM = """() => {
      const pick = s => { const e = document.querySelector(s);
                          return e ? (e.textContent||'').replace(/\\s+/g,'').trim() : ''; };
      const cands = ['#yhmc','#yhxm','.user-name','.user_name','#topmenu .user',
                     '.user-info','.welcome','[id*="name"]','[id*="xm"]'];
      for (const s of cands) { const v = pick(s);
        if (v && v.length >= 2 && v.length <= 24 && /[\\u4e00-\\u9fa5]/.test(v)) return v; }
      const b = document.body ? document.body.innerText || '' : '';
      const m = b.match(/欢迎[，,：:\\s]*([\\u4e00-\\u9fa5]{2,8})/);
      return m ? m[1] : '';
    }"""
    _API = """() => {
      return fetch('/jwglxt/xtgl/index_cxYhxxIndex.html?gnmkdm=index&layout=default',
                   {credentials:'include'}).then(r=>r.text()).then(t=>{
        try { return JSON.parse(t); } catch(e) { return null; }});
    }"""
    try:
        page.goto("https://zfjw.hainnu.edu.cn/jwglxt/xtgl/index_initMenu.html?jsdm=xs",
                  wait_until="domcontentloaded", timeout=45000)
    except Exception:  # noqa: BLE001
        return ""
    # 等待真正进入教务已登录页(URL 含 index_initMenu)，避免在 CAS/跳转中抓空
    for _ in range(13):
        try:
            cur = page.url
        except Exception:  # noqa: BLE001
            cur = ""
        if "index_initMenu" in cur:
            break
        time.sleep(1.5)
    time.sleep(1.5)
    try:
        v = page.evaluate(_DOM)
        if isinstance(v, str) and v:
            return v.strip()[:32]
    except Exception:  # noqa: BLE001
        pass
    try:
        obj = page.evaluate(_API)
        if isinstance(obj, dict):
            for k in ("xm", "xsmc", "xxm"):
                val = obj.get(k)
                if isinstance(val, str) and val.strip():
                    return val.strip()[:32]
            sub = obj.get("yhxx")
            if isinstance(sub, dict):
                for k in ("name", "xm", "xsmc"):
                    val = sub.get(k)
                    if isinstance(val, str) and val.strip():
                        return val.strip()[:32]
    except Exception:  # noqa: BLE001
        pass
    return ""


def grab_ehall_name(page) -> str:
    """从一网通办（ehall.hainnu.edu.cn，服务端渲染、姓名可见）抓真实姓名。

    与 chat 共用同一学校 CAS 会话；登录后导航到此即免登录。页面为服务端渲染，
    DOM 扫描 + 正则（欢迎/你好、学号相邻姓名）取姓名。
    """
    _DOM = """() => {
      const pick = s => { const e = document.querySelector(s);
                          return e ? (e.textContent||'').replace(/\\s+/g,'').trim() : ''; };
      const cands = ['[id*="name"]','[class*="name"]','[class*="user-name"]','.user',
                     '.userinfo','.topbar .name','.head .name','#username',
                     '[class*="userinfo"]','[class*="username"]'];
      for (const s of cands) { const v = pick(s);
        if (v && v.length >= 2 && v.length <= 12 && /[\\u4e00-\\u9fa5]/.test(v)) return v; }
      const b = document.body ? document.body.innerText || '' : '';
      let m = b.match(/(?:你好|欢迎|您好)，?\\s*([\\u4e00-\\u9fa5]{2,6})/);
      if (m) return m[1];
      m = b.match(/([\\u4e00-\\u9fa5]{2,6})\\s*\\d{8,12}/);
      if (m) return m[1];
      m = b.match(/\\d{8,12}\\s*([\\u4e00-\\u9fa5]{2,6})/);
      if (m) return m[1];
      return '';
    }"""
    try:
        page.goto("https://ehall.hainnu.edu.cn:4430/yy-sys/pc/home",
                  wait_until="networkidle", timeout=45000)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(1.5)
    for _ in range(20):                      # 至多等约 30s 等免登录渲染完成
        try:
            cur = page.url
        except Exception:  # noqa: BLE001
            cur = ""
        if "ehall.hainnu.edu.cn" in cur and "cas/login" not in cur and "sso/login" not in cur:
            try:
                v = page.evaluate(_DOM)
                if v:
                    return v.strip()[:32]
            except Exception:  # noqa: BLE001
                pass
        time.sleep(1.5)
    return ""


def grab_chaoxing_name(page) -> str:
    """进入超星管理平台（hnsf.qmx.chaoxing.com），抢真实姓名。

    说明：该平台走 microcas.chaoxing.com -> 学校 CAS 单点登录；本脚本刚完成 chat 登录，
    同一浏览器会话里 CAS 已登录，打开超星会自动免登录，然后从页面/ cookie 取真实姓名。
    取不到返回空串（尽力而为，不影响令牌）。
    """
    _JS = """() => {
      const pick = s => { const e = document.querySelector(s);
                          return e ? (e.textContent || '').trim() : ''; };
      const cands = ['#userName','#fans_fans','[id^="fans"]','.user_img_info','.uname',
                     '#showMore','.user_info','.top_right .user','.head_user_name','.user-name'];
      for (const s of cands) { const v = pick(s);
        if (v && v.length >= 2 && v.length <= 12 && /[\\u4e00-\\u9fa5]/.test(v)) return v; }
      const b = document.body ? document.body.innerText || '' : '';
      let m = b.match(/([\\u4e00-\\u9fa5]{2,6})\\s*(\\d{6,12}|同学|老师)/);  // 姓名+学号/称谓
      if (m) return m[1];
      return '';
    }"""
    try:
        page.goto("https://hnsf.qmx.chaoxing.com/home",
                  wait_until="domcontentloaded", timeout=45000)
    except Exception:  # noqa: BLE001
        return ""
    time.sleep(1)
    for _ in range(50):                       # 至多等约 25s 等免登录+SPA 渲染完成
        try:
            cur = page.url
        except Exception:  # noqa: BLE001
            cur = ""
        if "chaoxing.com" in cur and "login" not in cur.lower():
            try:
                val = page.evaluate(_JS)
                if val:
                    return val.strip()[:32]
            except Exception:  # noqa: BLE001
                pass
            try:
                for c in page.context.cookies():
                    if "chaoxing" in c.get("domain", "") and c.get("name") == "uname" \
                            and c.get("value"):
                        val = c["value"].strip()[:32]
                        if val and not (val.isdigit() and len(val) <= 12):
                            return val
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.5)
    return ""


def verify(token: str) -> str:
    """用令牌调一次 /api/models，确认有效并列出模型。"""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        "https://chat.hainnu.edu.cn/api/models",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"令牌被拒绝：HTTP {exc.code} {exc.read()[:200]!r}")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"校验请求失败：{exc}")

    items = data.get("data", data) if isinstance(data, dict) else data
    names = []
    for it in items:
        if isinstance(it, dict):
            mid = it.get("id") or it.get("name") or it.get("model")
        else:
            mid = it
        if mid:
            names.append(str(mid))
    return ", ".join(names) if names else "(上游返回空列表)"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        say("[错误] 缺少 playwright（令牌工具专用，运行时不需要）。")
        say("       直接双击「1.获取令牌.bat」会自动安装；或手动执行：")
        say("       python -m pip install playwright")
        return 2

    say("=" * 62)
    say("  海南师范大学 DeepSeek 令牌获取工具")
    say("=" * 62)
    say("即将打开一个 Chrome 窗口，请在里面完成学校统一身份认证登录。")
    say(f"登录成功后会自动保存令牌到：{TOKEN_FILE.name}")
    say(f"最多等待 {TIMEOUT_S // 60} 分钟，按 Ctrl+C 可中断。")
    say("-" * 62)

    PROFILE.mkdir(exist_ok=True)
    deadline = time.time() + TIMEOUT_S

    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE),
                channel="chrome",          # 使用系统已安装的 Chrome，无需下载
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
                viewport={"width": 1280, "height": 900},
                no_viewport=False,
            )
        except Exception as exc:  # noqa: BLE001
            say(f"[错误] 无法启动 Chrome（{exc}）。")
            say("      若未安装 Chrome，可改用 Playwright 自带内核：")
            say(r"      python -m playwright install chromium  然后把脚本里的 channel='chrome' 去掉")
            return 2

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(SITE, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:  # noqa: BLE001
            say(f"[提示] 打开页面时出错（{exc}），继续等待你手动操作…")

        token = ""
        last_hint = 0.0
        while time.time() < deadline:
            token = grab(page)
            if token:
                break
            now = time.time()
            if now - last_hint > 20:
                last_hint = now
                try:
                    cur = page.url
                except Exception:  # noqa: BLE001
                    cur = "?"
                say(f"  等待登录中… 当前页面：{cur[:80]}")
            time.sleep(2)

        if not token:
            say("\n[超时] 没有等到令牌。请确认已成功登录并进入聊天界面后重试。")
            ctx.close()
            return 1

        say(f"\n[1/2] 已捕获令牌（长度 {len(token)}），正在校验…")
        try:
            models = verify(token)
            say(f"[2/2] 校验通过！可用模型：{models}")
        except Exception as exc:  # noqa: BLE001
            say(f"[警告] {exc}")
            say("       令牌仍会保存，但可能无效，建议重新运行本工具。")

        TOKEN_FILE.write_text(token_codec.encrypt(token), encoding="utf-8")  # DPAPI 加密落盘
        # 姓名抓取是“尽力而为”：拿不到账号/姓名绝不失败，也不影响已保存的令牌。
        # 全程 try/except 包裹：任何异常只提示、被忽略。
        try:
            if LEGACY:
                # 备用链路：完全不访问门户，只用 chat 页的姓名（尽力而为，可能没有）
                say("\n[姓名] 备用链路：仅尝试聊天页姓名（不访问门户，取不到也正常）…")
                local = grab_user_name(page)
                cands = [x for x in (local,) if x]
            else:
                # 正常链路：只从网上服务大厅（ehall）静默取姓名：全校通用，教师也能用。
                # 仅在尚未取得真实姓名时访问一次学校门户读取，不跳多个站。
                cached = ""
                try:
                    cached = (BASE / "user_name.txt").read_text(encoding="utf-8").strip()[:32]
                except Exception:  # noqa: BLE001
                    cached = ""
                eh = ""
                if not cached or (cached.isdigit() and len(cached) <= 12):
                    say("\n[姓名] 读取网上服务大厅中的用户姓名（本次登录的共享会话内、静默完成）…")
                    eh = grab_ehall_name(page)
                else:
                    say(f"\n[姓名] 已缓存真实姓名「{cached}」，本次不再改它（保持静默）。")
                local = grab_user_name(page) if not eh else ""
                cands = [x for x in (eh, local) if x]
            uname = next((x for x in cands if not (x.isdigit() and len(x) <= 12)),
                         cands[0] if cands else "")
            if uname:
                USER_NAME_FILE.write_text(uname, encoding="utf-8")
                say(f"[姓名] 已保存姓名：{uname}")
            else:
                say("[姓名] 未能取到姓名（不影响令牌使用，管理台问候将无姓名）。")
        except Exception as exc:  # noqa: BLE001
            say(f"[姓名] 抓取异常（已忽略，不影响令牌）：{exc}")
        say("-" * 62)
        say(f"令牌已保存到：{TOKEN_FILE}")
        say("下一步：双击「2.启动代理.bat」，即可用 http://127.0.0.1:8787/v1 调用。")
        say("窗口将在 5 秒后关闭…")
        time.sleep(5)
        ctx.close()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say("\n已取消。")
        sys.exit(130)
