"""列博主作品元数据。

不下载视频文件，只取 aweme_id / 描述 / 时长 / 封面等元信息。
返回结果可直接作为 download_submit 的 ids 参数。

参数：
    --sec-uid <str>       博主 sec_uid（必填，由 resolve_user 返回）
    --mode <post|like>    默认 post
    --limit <int>         默认 30，上限 200
    --start-time <YYYY-MM-DD>  起始过滤（按作品创建时间 inclusive）
    --end-time <YYYY-MM-DD>    结束过滤（inclusive）；字面值 now = 今天
"""

from __future__ import annotations

import argparse
import datetime as _dt
from typing import Any, Dict, List, Optional

from zero_tool._io import (
    CookieFormatError,
    load_cookies,
    print_error,
    print_json,
    run_async,
)

_LIMIT_MAX = 200
_PAGE_SIZE = 20  # 每次 API 请求的页大小

_COOKIE_MISSING_MSG = (
    "Cookie 未配置或失效：请先确认 <workspace>/douyin/cookies.json 已就绪"
)


def _parse_date(s: Optional[str]) -> Optional[int]:
    """YYYY-MM-DD → epoch (本地零点)。'now' 字面值 → 今天零点。"""
    if not s:
        return None
    if s == "now":
        d = _dt.date.today()
    else:
        try:
            d = _dt.datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"日期格式应为 YYYY-MM-DD：{s}") from exc
    return int(_dt.datetime(d.year, d.month, d.day).timestamp())


def _truncate(s: str, n: int) -> str:
    s = "".join(ch for ch in s if ch >= " " or ch == " ")  # 剥离控制字符
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ").strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _aweme_to_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    cover = ""
    cover_obj = (item.get("video") or {}).get("cover") or {}
    url_list = cover_obj.get("url_list") or []
    if url_list:
        cover = url_list[0]

    duration_ms = int((item.get("video") or {}).get("duration") or 0)
    is_image = bool(item.get("images") or (item.get("aweme_type") in (68, 51)))

    return {
        "aweme_id": str(item.get("aweme_id", "")),
        "desc": _truncate(str(item.get("desc") or ""), 80),
        "create_time": int(item.get("create_time") or 0),
        "duration_ms": duration_ms,
        "is_image": is_image,
        "cover_url": cover,
    }


async def _list(
    sec_uid: str,
    mode: str,
    limit: int,
    start_ts: Optional[int],
    end_ts: Optional[int],
    cookies: Dict[str, str],
) -> Dict[str, Any]:
    """拉取博主作品元数据列表。

    退出条件（满足任一）：
    1. 累计达到 limit
    2. 抖音明确告知 has_more=False
    3. cursor 不再前进（卡死）
    4. **连续** 5 次空页（抖音 shadow throttle 下偶尔会插空页，单次空不退）
    5. 总 page 请求数达到上限 30（兜底）

    Throttled 状态：has_more 一直 True 但累计实际只拿到极少（avg < 2 items/page）
    时标记 throttled=True，让上游知道"抖音在限流"。
    """
    from core import DouyinAPIClient

    works: List[Dict[str, Any]] = []
    truncated = False
    max_cursor = 0
    empty_page_streak = 0
    pages_fetched = 0
    items_observed_total = 0
    MAX_EMPTY_STREAK = 5
    MAX_PAGES = 30

    async with DouyinAPIClient(cookies) as api_client:
        while len(works) < limit and pages_fetched < MAX_PAGES:
            if mode == "post":
                page = await api_client.get_user_post(
                    sec_uid, max_cursor=max_cursor, count=_PAGE_SIZE
                )
            else:
                page = await api_client.get_user_like(
                    sec_uid, max_cursor=max_cursor, count=_PAGE_SIZE
                )
            pages_fetched += 1

            if not page:
                break

            items = page.get("aweme_list") or []
            items_observed_total += len(items)

            if items:
                empty_page_streak = 0
                for item in items:
                    ct = int(item.get("create_time") or 0)
                    if start_ts is not None and ct < start_ts:
                        continue
                    if end_ts is not None and ct > end_ts + 86399:
                        continue
                    works.append(_aweme_to_meta(item))
                    if len(works) >= limit:
                        truncated = True
                        break
            else:
                empty_page_streak += 1
                if empty_page_streak >= MAX_EMPTY_STREAK:
                    break

            if page.get("has_more") in (0, False, None):
                break
            new_cursor = int(page.get("max_cursor") or 0)
            if new_cursor == max_cursor:
                break  # cursor 卡死，真的没了
            max_cursor = new_cursor

    # Shadow throttle 检测：page 拉了至少 3 次，但平均每页 < 2 items
    throttled = (
        pages_fetched >= 3
        and items_observed_total / pages_fetched < 2
        and len(works) < limit
    )

    return {
        "works": works,
        "count": len(works),
        "truncated": truncated,
        "throttled": throttled,
        "pages_fetched": pages_fetched,
    }


def run() -> None:
    parser = argparse.ArgumentParser(description="list douyin user works metadata")
    parser.add_argument("--sec-uid", dest="sec_uid", required=True)
    parser.add_argument(
        "--mode", choices=["post", "like"], default="post", help="default: post"
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--start-time", dest="start_time", default=None)
    parser.add_argument("--end-time", dest="end_time", default=None)
    args = parser.parse_args()

    limit = max(1, min(args.limit, _LIMIT_MAX))

    try:
        start_ts = _parse_date(args.start_time)
        end_ts = _parse_date(args.end_time)
    except ValueError as exc:
        print_error("invalid_input", str(exc))
        return

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
        result = run_async(
            lambda: _list(args.sec_uid, args.mode, limit, start_ts, end_ts, cookies)
        )
    except Exception as exc:
        print_error("network_error", f"列作品时出错：{exc.__class__.__name__}: {exc}")
        return

    print_json(result)
