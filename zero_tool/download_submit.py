"""异步提交下载任务，立即返回 task_id（不阻塞）。

实际下载由 fork 出去的 zero_tool._worker 后台进程执行。
进度通过 download_status 工具查询。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import List

from zero_tool._io import (
    print_error,
    print_json,
    tasks_dir,
)

_MAX_IDS_PER_TASK = 50


def _to_bool(s: str) -> bool:
    return s.strip().lower() in {"1", "true", "yes", "on"}


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_ids(raw: str) -> List[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def _write_initial_state(task_id: str, ids: List[str], opts: dict) -> Path:
    d = tasks_dir()
    d.mkdir(parents=True, exist_ok=True)
    state_path = d / f"{task_id}.json"
    state = {
        "task_id": task_id,
        "state": "pending",
        "submitted_at": _now_iso(),
        "started_at": None,
        "finished_at": None,
        "request": {"ids": ids, **opts},
        "progress": {"total": len(ids), "succeeded": 0, "failed": 0},
        "results": [],
        "error": None,
    }
    tmp = state_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, state_path)
    return state_path


def _spawn_worker(task_id: str) -> None:
    """fork 后台 worker。stdin/stdout/stderr → DEVNULL，detached。"""
    cmd = [sys.executable, "-m", "zero_tool._worker", "--task-id", task_id]
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        # 新 process group + 不继承 console，避免子进程被父进程关闭时一起被杀
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen(cmd, **kwargs)


def run() -> None:
    parser = argparse.ArgumentParser(description="submit douyin download task (async)")
    parser.add_argument("--ids", required=True, help="逗号分隔 aweme_id 列表")
    parser.add_argument("--music", default="true")
    parser.add_argument("--cover", default="true")
    parser.add_argument("--json", default="true", dest="json_meta")
    args = parser.parse_args()

    ids = _parse_ids(args.ids)
    if not ids:
        print_error("invalid_input", "ids 为空")
        return
    if len(ids) > _MAX_IDS_PER_TASK:
        print_error(
            "invalid_input",
            f"一次最多提交 {_MAX_IDS_PER_TASK} 个 aweme_id（当前 {len(ids)}），请分批",
        )
        return

    opts = {
        "music": _to_bool(args.music),
        "cover": _to_bool(args.cover),
        "json": _to_bool(args.json_meta),
    }

    task_id = f"task_{int(time.time() * 1000)}_{secrets.token_hex(3)}"
    state_path = _write_initial_state(task_id, ids, opts)

    try:
        _spawn_worker(task_id)
    except Exception as exc:
        # worker 拉起失败时，把状态文件改为 failed 让 download_status 能读到
        state_path.unlink(missing_ok=True)
        print_error(
            "internal_error",
            f"后台 worker 启动失败：{exc.__class__.__name__}: {exc}",
        )
        return

    print_json(
        {
            "task_id": task_id,
            "state": "pending",
            "submitted_at": _now_iso(),
            "ids_count": len(ids),
        }
    )
