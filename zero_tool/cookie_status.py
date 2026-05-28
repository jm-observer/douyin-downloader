"""检查抖音 Cookie 是否可用。

输出：
    valid=True ：cookies.json 存在 + 抖音返回了登录态用户信息
    valid=False：缺失 / 格式错误 / 探测被拒（cookie 已失效）/ 探测失败
"""

from __future__ import annotations

import argparse
from typing import Optional

from zero_tool._io import (
    CookieFormatError,
    load_cookies,
    print_json,
    run_async,
)

# 失效话术固定模板（不让 LLM 编造细节）
_MSG_MISSING = (
    "Cookie 未配置：请按 docs/cookie-setup.md 在 "
    "<workspace>/douyin/cookies.json 创建文件"
)
_MSG_INVALID_FORMAT = (
    "Cookie 文件格式错误：请按 docs/cookie-setup.md 检查 cookies.json schema"
)
_MSG_EXPIRED = (
    "Cookie 已失效：请按 docs/cookie-setup.md 在 g10 上更新 "
    "<workspace>/douyin/cookies.json"
)


async def _probe(cookies: dict, updated_at: str) -> dict:
    from core import DouyinAPIClient

    async with DouyinAPIClient(cookies) as api_client:
        user = await api_client.get_self_info()
        if user and user.get("sec_uid"):
            return {"valid": True, "updated_at": updated_at}
        return {"valid": False, "msg": _MSG_EXPIRED, "updated_at": updated_at}


def run() -> None:
    parser = argparse.ArgumentParser(description="check douyin cookie status")
    parser.parse_args()  # 无参数，但允许 --help

    try:
        loaded: Optional[tuple] = load_cookies()
    except CookieFormatError as exc:
        print_json({"valid": False, "msg": _MSG_INVALID_FORMAT, "detail": str(exc)})
        return

    if loaded is None:
        print_json({"valid": False, "msg": _MSG_MISSING})
        return

    cookies, updated_at = loaded

    try:
        result = run_async(lambda: _probe(cookies, updated_at))
    except Exception as exc:  # 网络异常等
        print_json(
            {
                "valid": False,
                "msg": f"Cookie 探测失败：{exc.__class__.__name__}: {exc}",
                "updated_at": updated_at,
            }
        )
        return

    print_json(result)
