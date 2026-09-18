"""token 落盘加密：Windows DPAPI（CryptProtectData），绑定“当前用户 + 本机”。

作用：token.txt 落盘不再存明文，只有在本机当前用户下读取时才临时解密到内存，
避免项目被拷贝/同步/丢 U 盘时令牌泄露给他人电脑。

文件格式：一行 `enc:<base64>`。无该前缀视为旧版明文（自动兼容迁移）。
非 Windows 平台无法 DPAPI，退化为透明透传（项目仍可运行，只是本平台不加密）。

依赖：仅标准库（ctypes）。
"""
from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes

_DPAPI_OK = False


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


if sys.platform == "win32":
    try:
        _crypt32 = ctypes.windll.crypt32
        _kernel32 = ctypes.windll.kernel32
        _BLOB = ctypes.POINTER(_DATA_BLOB)
        _crypt32.CryptProtectData.argtypes = [
            _BLOB, wintypes.LPCWSTR, _BLOB, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD, _BLOB,
        ]
        _crypt32.CryptProtectData.restype = wintypes.BOOL
        _crypt32.CryptUnprotectData.argtypes = [
            _BLOB, ctypes.POINTER(wintypes.LPWSTR), _BLOB, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD, _BLOB,
        ]
        _crypt32.CryptUnprotectData.restype = wintypes.BOOL
        _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        _kernel32.LocalFree.restype = ctypes.c_void_p
        _DPAPI_OK = True
    except Exception:  # noqa: BLE001
        _DPAPI_OK = False


def _to_blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))


def _blob_bytes(blob: _DATA_BLOB) -> bytes:
    n = int(blob.cbData)
    return ctypes.string_at(blob.pbData, n) if (n and blob.pbData) else b""


def _protect(data: bytes) -> bytes:
    if not _DPAPI_OK:
        return data
    buf_in = _to_blob(data)
    out = _DATA_BLOB()
    if not _crypt32.CryptProtectData(ctypes.byref(buf_in), None, None,
                                     None, None, 0, ctypes.byref(out)):
        raise OSError("CryptProtectData 失败（无法加密令牌）")
    try:
        return _blob_bytes(out)
    finally:
        if out.pbData:
            _kernel32.LocalFree(out.pbData)


def _unprotect(data: bytes) -> bytes:
    if not _DPAPI_OK:
        return data
    buf_in = _to_blob(data)
    out = _DATA_BLOB()
    if not _crypt32.CryptUnprotectData(ctypes.byref(buf_in), None, None,
                                       None, None, 0, ctypes.byref(out)):
        raise OSError("CryptUnprotectData 失败（无法在本机解密令牌）")
    try:
        return _blob_bytes(out)
    finally:
        if out.pbData:
            _kernel32.LocalFree(out.pbData)


def is_encrypted(payload: str) -> bool:
    """判断该字符串是否已是加密格式。"""
    return payload.startswith("enc:")


def encrypt(plain: str) -> str:
    """明文 -> 加密存储串（`enc:<base64>`）。"""
    return "enc:" + base64.b64encode(_protect(plain.encode("utf-8"))).decode("ascii")


def decrypt(payload: str) -> str | None:
    """把存储串解回明文。若为旧版明文直接原样返回（迁移兼容）；
    加密串在本机解密失败返回 None（换机/换用户）。"""
    if not payload.startswith("enc:"):
        return payload
    try:
        raw = base64.b64decode(payload[4:])
        return _unprotect(raw).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None


def encrypt_if_not(payload: str) -> str:
    """已是加密就原样返回，否则转成加密（用于把明文旧文件升级成加密）。"""
    return payload if is_encrypted(payload) else encrypt(payload)


def migrate_file_write(path, plain: str) -> None:
    """便捷写入：先加密再落盘。"""
    import pathlib
    pathlib.Path(path).write_text(encrypt(plain), encoding="utf-8")


__all__ = ["is_encrypted", "encrypt", "decrypt", "encrypt_if_not",
           "migrate_file_write", "_DPAPI_OK"]
