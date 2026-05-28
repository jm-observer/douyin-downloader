"""解析抖音博主 handle/URL → sec_uid + 基本信息。

支持输入：
- 完整主页 URL（https://www.douyin.com/user/MS4w...）
- 分享短链（v.douyin.com/xxx / v.iesdouyin.com/xxx）
- 已知的 sec_uid 直接传（以 "MS4w" 开头）

不支持：
- @nickname（抖音无公开"按昵称查"接口；提示用户改发主页链接）
"""

from __future__ import annotations

import argparse
from typing import Any, Dict, Optional

from zero_tool._io import (
    CookieFormatError,
    load_cookies,
    print_error,
    print_json,
    run_async,
)

_COOKIE_MISSING_MSG = (
    "Cookie 未配置或失效：请先确认 <workspace>/douyin/cookies.json 已就绪"
)


def _looks_like_sec_uid(s: str) -> bool:
    # 抖音 sec_uid 都以 MS4w 开头、长度约 55-90、字母数字下划线减号
    return s.startswith("MS4w") and 40 <= len(s) <= 120


async def _resolve(handle: str, cookies: Dict[str, str]) -> Dict[str, Any]:
    from core import DouyinAPIClient, URLParser
    from utils.validators import is_short_url, normalize_short_url

    sec_uid: Optional[str] = None

    if _looks_like_sec_uid(handle):
        sec_uid = handle
    else:
        url = handle.strip()
        async with DouyinAPIClient(cookies) as api_client:
            if is_short_url(url):
                resolved = await api_client.resolve_short_url(normalize_short_url(url))
                if not resolved:
                    return {"error": "invalid_input", "msg": "短链解析失败，请检查链接"}
                url = resolved

            parsed = URLParser.parse(url)
            if not parsed:
                return {
                    "error": "invalid_input",
                    "msg": "无法识别该链接类型，请发博主主页链接",
                }
            if parsed.get("type") != "user":
                return {
                    "error": "invalid_input",
                    "msg": (
                        "提供的链接不是博主主页（type="
                        f"{parsed.get('type')!r}），请发博主主页链接"
                    ),
                }
            sec_uid = parsed.get("sec_uid")
            if not sec_uid:
                return {
                    "error": "invalid_input",
                    "msg": "URL 中未提取到 sec_uid，请确认是完整主页链接",
                }

            user = await api_client.get_user_info(sec_uid)
            if not user:
                return {"error": "not_found", "msg": "未找到该博主，请确认链接正确"}
            return _user_to_payload(sec_uid, user)

    # sec_uid 直传分支：单独开 client 探询
    async with DouyinAPIClient(cookies) as api_client:
        user = await api_client.get_user_info(sec_uid)
        if not user:
            return {"error": "not_found", "msg": "未找到该博主，请确认 sec_uid 正确"}
        return _user_to_payload(sec_uid, user)


def _user_to_payload(sec_uid: str, user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sec_uid": sec_uid,
        "nickname": user.get("nickname", ""),
        "signature": (user.get("signature") or "").strip(),
        "aweme_count": int(user.get("aweme_count") or 0),
        "follower_count": int(user.get("follower_count") or 0),
        "following_count": int(user.get("following_count") or 0),
    }


def run() -> None:
    parser = argparse.ArgumentParser(description="resolve douyin user handle to sec_uid")
    parser.add_argument(
        "--handle",
        required=True,
        help="主页 URL / 短链 / sec_uid",
    )
    args = parser.parse_args()

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
        result = run_async(lambda: _resolve(args.handle, cookies))
    except Exception as exc:
        print_error("network_error", f"解析博主时出错：{exc.__class__.__name__}: {exc}")
        return

    if "error" in result:
        print_error(result["error"], result["msg"])
    else:
        print_json(result)
