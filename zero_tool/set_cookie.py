"""把用户提供的 cookie 内容写入 <workspace>/douyin/cookies.json。

接收两种格式（自动识别）：
1. 浏览器原始 Cookie 头：'msToken=xxx; ttwid=yyy; sessionid_ss=zzz; ...'
2. JSON 对象字符串：'{"msToken":"xxx","ttwid":"yyy",...}'

成功输出：
    {"success": true, "field_count": N, "updated_at": "ISO8601"}
失败输出：
    {"error": "<code>", "msg": "<中文>"}
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Dict, Optional

from zero_tool._io import cookies_path, print_error, print_json


_REQUIRED_HINT_KEYS = ("msToken", "ttwid", "sessionid_ss")


def _try_parse_json(raw: str) -> Optional[Dict[str, str]]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    # 支持两种 JSON 形态：
    # a) 顶层就是 {key: value} 的 cookie dict
    # b) 跟我们写盘 schema 一样的 {"value": {...}, "updated_at": "..."} 直接接受
    if "value" in parsed and isinstance(parsed["value"], dict):
        candidate = parsed["value"]
    else:
        candidate = parsed
    return {str(k): str(v) for k, v in candidate.items() if v not in (None, "")}


def _parse_cookie_header(raw: str) -> Dict[str, str]:
    """解析 'k1=v1; k2=v2; ...' 形式。也容忍换行和单引号包裹。"""
    raw = raw.strip().strip("'").strip('"')
    out: Dict[str, str] = {}
    # 浏览器可能给的是分号分隔，也可能换行——都按非字母数字切
    for chunk in raw.replace("\n", ";").split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v:
            out[k] = v
    return out


def _validate(cookies: Dict[str, str]) -> Optional[str]:
    """返回错误消息或 None。"""
    if not cookies:
        return "解析后 cookie 为空，检查输入格式（应是 'k=v; k=v;' 或 JSON 对象）"
    if not any(k in cookies for k in _REQUIRED_HINT_KEYS):
        return (
            f"未识别到核心 cookie 字段（{'/'.join(_REQUIRED_HINT_KEYS)} 至少要有一个）。"
            "检查是否复制完整、是否在登录状态下抓的"
        )
    return None


def _atomic_write(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)
    # POSIX chmod；Windows 上是 no-op，靠 ACL
    if sys.platform != "win32":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def run() -> None:
    parser = argparse.ArgumentParser(description="set douyin cookies from user input")
    parser.add_argument("--raw", required=True, help="Cookie 内容：浏览器 Cookie 头或 JSON 对象字符串")
    args = parser.parse_args()
    raw = args.raw.strip()

    if not raw:
        print_error("invalid_input", "raw 为空")
        return

    # 优先按 JSON 解析；失败就按 Cookie 头格式
    cookies = _try_parse_json(raw)
    if cookies is None:
        cookies = _parse_cookie_header(raw)

    err = _validate(cookies)
    if err:
        print_error("invalid_input", err)
        return

    updated_at = (
        _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    )
    payload = {"value": cookies, "updated_at": updated_at}

    try:
        _atomic_write(cookies_path(), payload)
    except OSError as exc:
        print_error("internal_error", f"写文件失败：{exc.__class__.__name__}: {exc}")
        return

    print_json(
        {
            "success": True,
            "field_count": len(cookies),
            "updated_at": updated_at,
            "has_required": [k for k in _REQUIRED_HINT_KEYS if k in cookies],
        }
    )
