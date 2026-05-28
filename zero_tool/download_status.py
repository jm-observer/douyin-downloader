"""查询 download_submit 返回的 task_id 状态。

state ∈ {pending, running, succeeded, failed}
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

from zero_tool._io import print_error, print_json, tasks_dir


def _parse_iso(s):
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def run() -> None:
    parser = argparse.ArgumentParser(description="query douyin download task status")
    parser.add_argument("--task-id", dest="task_id", required=True)
    args = parser.parse_args()

    p: Path = tasks_dir() / f"{args.task_id}.json"
    if not p.exists():
        print_error(
            "not_found",
            "task_id 不存在或已被清理",
            task_id=args.task_id,
        )
        return

    try:
        with open(p, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print_error(
            "internal_error",
            f"状态文件读取失败：{exc.__class__.__name__}: {exc}",
            task_id=args.task_id,
        )
        return

    started = _parse_iso(state.get("started_at"))
    finished = _parse_iso(state.get("finished_at"))
    if started is not None:
        end = finished or _dt.datetime.now(_dt.timezone.utc).astimezone()
        elapsed = max(0, int((end - started).total_seconds()))
        state["elapsed_secs"] = elapsed
    else:
        state["elapsed_secs"] = 0

    print_json(state)
