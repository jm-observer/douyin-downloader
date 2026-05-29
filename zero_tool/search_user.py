"""按昵称 / 抖音号 / 关键词搜索抖音博主，返回候选列表。

LLM 用此工具在用户只给了"抖音号"或"博主昵称"（没给主页 URL / sec_uid）时
找到对应 sec_uid，然后串到 resolve_user / list_works / download。
"""

from __future__ import annotations

import argparse
from typing import Any, Dict, List

from zero_tool._io import (
    CookieFormatError,
    load_cookies,
    print_error,
    print_json,
    run_async,
)

_LIMIT_DEFAULT = 5
_LIMIT_MAX = 20

_COOKIE_MISSING_MSG = (
    "Cookie 未配置或失效：请先确认 <workspace>/douyin/cookies.json 已就绪"
)


def _user_to_compact(u: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sec_uid": u.get("sec_uid", ""),
        "nickname": u.get("nickname", ""),
        "unique_id": u.get("unique_id", ""),  # 抖音号
        "short_id": u.get("short_id", ""),  # 旧版抖音号
        "signature": (u.get("signature") or "").replace("\n", " ").strip()[:80],
        "follower_count": int(u.get("follower_count") or 0),
        "aweme_count": int(u.get("aweme_count") or 0),
        "verification_type": int(u.get("verification_type") or 0),
        "custom_verify": u.get("custom_verify", ""),
    }


async def _search(keyword: str, limit: int, cookies: Dict[str, str]) -> Dict[str, Any]:
    from core import DouyinAPIClient

    async with DouyinAPIClient(cookies) as api:
        result = await api.search_user(keyword, count=min(limit, 20))
        items = result.get("items", [])
        users: List[Dict[str, Any]] = [_user_to_compact(u) for u in items[:limit]]
        return {
            "users": users,
            "count": len(users),
            "truncated": len(items) > limit,
        }


def run() -> None:
    parser = argparse.ArgumentParser(description="search douyin users by keyword")
    parser.add_argument(
        "--keyword",
        required=True,
        help="搜索关键词：博主昵称 / 抖音号 / 任意关键词",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_LIMIT_DEFAULT,
        help=f"最多返回博主数，默认 {_LIMIT_DEFAULT}，上限 {_LIMIT_MAX}",
    )
    args = parser.parse_args()

    keyword = args.keyword.strip()
    if not keyword:
        print_error("invalid_input", "keyword 为空")
        return

    limit = max(1, min(args.limit, _LIMIT_MAX))

    try:
        loaded = load_cookies()
    except CookieFormatError as exc:
        print_error("cookie_invalid", f"Cookie 文件格式错误：{exc}")
        return

    if loaded is None:
        print_error("cookie_missing", _COOKIE_MISSING_MSG)
        return

    cookies, _ = loaded

    try:
        result = run_async(lambda: _search(keyword, limit, cookies))
    except Exception as exc:
        print_error(
            "network_error", f"搜索博主时出错：{exc.__class__.__name__}: {exc}"
        )
        return

    print_json(result)
