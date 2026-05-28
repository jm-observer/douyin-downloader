"""zero_tool 子命令分派入口。

调用形式：
    python -m zero_tool <subcommand> [args...]

子命令：
    cookie_status     检查 cookie 是否可用
    resolve_user      根据 handle/URL 解析博主 sec_uid
    list_works        列博主作品元数据
    download_submit   异步提交下载任务，返回 task_id
    download_status   查询任务进度
"""

from __future__ import annotations

import importlib
import sys

_SUBCOMMANDS = {
    "cookie_status": "zero_tool.cookie_status",
    "resolve_user": "zero_tool.resolve_user",
    "list_works": "zero_tool.list_works",
    "download_submit": "zero_tool.download_submit",
    "download_status": "zero_tool.download_status",
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _SUBCOMMANDS:
        names = ", ".join(_SUBCOMMANDS.keys())
        sys.stderr.write(f"unknown subcommand; expected one of: {names}\n")
        sys.exit(1)

    sub = sys.argv[1]
    mod = importlib.import_module(_SUBCOMMANDS[sub])
    # 让子模块从 sys.argv[2:] 取自己的参数（让 argparse 看到原始 prog 名 + 真正参数）
    sys.argv = [f"python -m zero_tool {sub}"] + sys.argv[2:]
    mod.run()


if __name__ == "__main__":
    main()
