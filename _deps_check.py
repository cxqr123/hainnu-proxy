"""检查（并在需要时安装）本地服务运行所需的依赖。

只用标准库，因此**任何** Python 都能跑它 —— 包括还没装依赖的系统 Python。
这点是刻意的：服务本体需要 fastapi/uvicorn/httpx，若本脚本也依赖它们，
就没人能在"缺依赖"的状态下完成检查与修复。

用法：
    python _deps_check.py            仅检查
    python _deps_check.py --install  检查；缺失则建 .venv 并用清华源装上

退出码：
    0   依赖已齐全
    10  缺失依赖（未带 --install，或无需安装）
    11  尝试安装但失败
    12  本机找不到任何可用的 Python
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
REQS = BASE / "requirements.txt"

# 多源按序回退。为什么不能只写一个国内源：实测本机 pip 访问清华源会被 403
# （curl 同 URL 却 200），而官方源正常 —— 镜像对 pip 的封锁是"挑客户端"的，
# 写死单一源就会在别人机器上莫名其妙装不上（这正是"装过依赖还是不行"的成因）。
PIP_INDEXES = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.org/simple",
]

OK, MISSING, INSTALL_FAILED, NO_PYTHON = 0, 10, 11, 12


def venv_python() -> Path | None:
    for name in ("python.exe", "pythonw.exe"):
        p = BASE / ".venv" / "Scripts" / name
        if p.exists():
            return p
    return None


def runtime_python() -> Path | None:
    for name in ("python.exe", "pythonw.exe"):
        p = BASE / "runtime" / name
        if p.exists():
            return p
    return None


def system_python() -> Path | None:
    """随便找一个能用的解释器 —— 不要求它装了依赖。"""
    cands = [Path(sys.executable)]
    for name in ("py", "python", "python3"):
        w = shutil.which(name)
        if w:
            cands.append(Path(w))
    for c in cands:
        try:
            if c.exists() and subprocess.run(
                [str(c), "-c", "pass"], capture_output=True, timeout=30
            ).returncode == 0:
                return c
        except Exception:  # noqa: BLE001
            continue
    return None


def has_deps(py: Path) -> bool:
    try:
        return subprocess.run(
            [str(py), "-c", "import fastapi,uvicorn,httpx"],
            capture_output=True, timeout=60,
        ).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def run(cmd: list[str], timeout: int = 900, live: bool = False) -> subprocess.CompletedProcess:
    """live=True 时输出直通控制台（装包时让人看到进度），否则捕获后按需回显。"""
    if live:
        return subprocess.run(cmd, timeout=timeout)
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def install() -> int:
    """建 .venv（如需要）并装依赖。装到 .venv 而非系统 Python：
    不污染系统环境，且与 _find_python.bat 的探测顺序（runtime → .venv → 系统）一致。"""
    vpy = venv_python()
    if vpy is None:
        syspy = system_python()
        if syspy is None:
            print("[ERROR] 本机找不到可用的 Python，无法创建 .venv。")
            return NO_PYTHON
        print("正在创建 .venv ...")
        r = run([str(syspy), "-m", "venv", str(BASE / ".venv")],
                timeout=600, live=True)
        if r.returncode != 0:
            return INSTALL_FAILED
        vpy = venv_python()
        if vpy is None:
            print("[ERROR] .venv 创建后仍未找到解释器。")
            return INSTALL_FAILED

    # venv 里可能没有 pip（ensurepip 被裁剪时）
    if run([str(vpy), "-m", "pip", "--version"]).returncode != 0:
        print("pip 不可用，正在引导 ...")
        r = run([str(vpy), "-m", "ensurepip", "--upgrade"])
        if r.returncode != 0:
            print(r.stdout or "", r.stderr or "")
            return INSTALL_FAILED

    req_args = ["-r", str(REQS)] if REQS.exists() else ["fastapi", "uvicorn", "httpx"]
    for n, url in enumerate(PIP_INDEXES, 1):
        host = url.split("//", 1)[-1].split("/")[0]
        print(f"正在安装依赖（{host}，第 {n}/{len(PIP_INDEXES)} 个源）...")
        r = run([str(vpy), "-m", "pip", "install", "--disable-pip-version-check",
                 "-i", url, *req_args], timeout=900, live=True)
        if r.returncode == 0 and has_deps(vpy):
            return OK
        print(f"  源 {host} 装不上，换下一个。")

    print("[ERROR] 所有 pip 源都装不上，请检查网络/代理后手动执行 0.安装依赖.bat。")
    return INSTALL_FAILED


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="缺失时自动安装")
    args = ap.parse_args()

    # 便携运行时自带依赖，有它就不用管别的
    rpy = runtime_python()
    if rpy is not None and has_deps(rpy):
        print("[ok] 便携运行时已就绪，依赖齐全。")
        return OK

    vpy = venv_python()
    if vpy is not None and has_deps(vpy):
        print("[ok] .venv 依赖齐全。")
        return OK

    spy = system_python()
    if spy is not None and has_deps(spy):
        print("[ok] 系统 Python 已装依赖。")
        return OK

    if not args.install:
        print("[warn] 缺少 fastapi / uvicorn / httpx（便携运行时 runtime\\ 也不在）。")
        return MISSING

    print("[warn] 缺少依赖，自动安装 ...")
    if spy is None:
        print("[ERROR] 本机找不到可用的 Python。")
        return NO_PYTHON
    return install()


if __name__ == "__main__":
    sys.exit(main())
