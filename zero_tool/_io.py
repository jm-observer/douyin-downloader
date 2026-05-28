"""共用 IO 与 workspace 辅助函数。

zero_tool 各子命令公用：
- workspace 路径解析（环境变量 / 平台 fallback）
- cookie 文件加载（结构化 schema {value, updated_at} → plain dict）
- 紧凑 JSON 输出 / 错误模板
- asyncio 入口 wrapper
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple


class CookieFormatError(Exception):
    """cookies.json 存在但格式不对。"""


def resolve_workspace() -> Path:
    """优先 ZERO_WORKSPACE 环境变量；否则按平台 fallback。

    不自动创建目录——创建职责由具体子命令在写入路径前完成。
    """
    env_value = os.environ.get("ZERO_WORKSPACE")
    if env_value:
        return Path(env_value)

    if sys.platform == "win32":
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    else:
        home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".config" / "zero"


def cookies_path() -> Path:
    return resolve_workspace() / "douyin" / "cookies.json"


def downloads_root() -> Path:
    return resolve_workspace() / "downloads" / "douyin"


def tasks_dir() -> Path:
    return resolve_workspace() / "downloads" / ".tasks"


def load_cookies() -> Optional[Tuple[Dict[str, str], str]]:
    """读 cookies.json。

    返回：
    - None：文件不存在
    - (cookies_dict, updated_at)：成功

    抛 CookieFormatError：文件存在但解析失败 / schema 不符
    """
    path = cookies_path()
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise CookieFormatError(f"cookies.json JSON 解析失败：{exc}") from exc
    except OSError as exc:
        raise CookieFormatError(f"cookies.json 读取失败：{exc}") from exc

    if not isinstance(raw, dict):
        raise CookieFormatError("cookies.json 顶层应为对象")

    value = raw.get("value")
    if not isinstance(value, dict):
        raise CookieFormatError("cookies.json 缺少 value 字段或不是对象")

    updated_at = raw.get("updated_at")
    if not isinstance(updated_at, str):
        updated_at = ""

    # 过滤掉空值并强制 str 类型，避免下游 sanitize 抛错
    cookies = {str(k): str(v) for k, v in value.items() if v not in (None, "")}
    return cookies, updated_at


def print_json(obj: Dict[str, Any]) -> None:
    """紧凑 JSON 输出到 stdout。无空格、ensure_ascii=False。"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.flush()


def print_error(code: str, msg: str, **extra: Any) -> None:
    """固定错误模板输出。code 用 snake_case，msg 中文。"""
    payload: Dict[str, Any] = {"error": code, "msg": msg}
    payload.update(extra)
    print_json(payload)


def run_async(coro: Callable[[], Awaitable[Any]]) -> Any:
    """统一 async 入口：asyncio.run 包一层，捕获 KeyboardInterrupt。"""
    try:
        return asyncio.run(coro())
    except KeyboardInterrupt:
        sys.stderr.write("interrupted\n")
        sys.exit(130)
