"""download_submit fork 出来的后台 worker。

读 task 状态文件 → 下载每个 aweme_id → 原子更新状态文件 → 退出。

绝对不向 stdout/stderr 输出任何内容（父进程已 DEVNULL）；
诊断信息写到 <workspace>/downloads/.tasks/<task_id>.log。
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

from zero_tool._io import (
    CookieFormatError,
    downloads_root,
    load_cookies,
    tasks_dir,
)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _state_path(task_id: str) -> Path:
    return tasks_dir() / f"{task_id}.json"


def _log_path(task_id: str) -> Path:
    return tasks_dir() / f"{task_id}.log"


def _read_state(task_id: str) -> Dict[str, Any]:
    with open(_state_path(task_id), "r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_state(task_id: str, state: Dict[str, Any]) -> None:
    p = _state_path(task_id)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)


def _log(task_id: str, msg: str) -> None:
    try:
        with open(_log_path(task_id), "a", encoding="utf-8") as f:
            f.write(f"[{_now_iso()}] {msg}\n")
    except OSError:
        pass


def _walk_files(root: Path) -> List[str]:
    if not root.exists():
        return []
    out: List[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            out.append(str(Path(dirpath) / name))
    return sorted(out)


async def _download_one(
    aweme_id: str,
    opts: Dict[str, bool],
    cookies: Dict[str, str],
) -> Tuple[bool, List[str], str]:
    """下载单个 aweme，返回 (success, paths, error_msg)。"""
    from auth import CookieManager
    from config import ConfigLoader
    from control import QueueManager, RateLimiter, RetryHandler
    from core import DouyinAPIClient, DownloaderFactory, URLParser
    from storage import FileManager

    # 每个 aweme 独立目录，便于事后扫描产物
    per_item_root = downloads_root() / aweme_id
    per_item_root.mkdir(parents=True, exist_ok=True)

    config = ConfigLoader(None)
    config.update(path=str(per_item_root))
    config.update(music=opts["music"])
    config.update(cover=opts["cover"])
    config.update(json=opts["json"])
    config.update(database=False)  # 关掉 SQLite 历史，避免与全局 db 冲突
    config.update(progress={"quiet_logs": True})
    # 关掉两个可选能力，避免触发 playwright / whisper 等 optional deps
    config.update(browser_fallback={"enabled": False})
    config.update(transcript={"enabled": False})

    cm = CookieManager()
    cm.set_cookies(cookies)

    file_manager = FileManager(config.get("path"))
    rate_limiter = RateLimiter(max_per_second=float(config.get("rate_limit", 2) or 2))
    retry_handler = RetryHandler(max_retries=config.get("retry_times", 3))
    queue_manager = QueueManager(max_workers=int(config.get("thread", 5) or 5))

    fake_url = f"https://www.douyin.com/video/{aweme_id}"
    parsed = URLParser.parse(fake_url)
    if not parsed:
        return False, [], "URL 解析失败（aweme_id 格式异常？）"

    async with DouyinAPIClient(cookies) as api_client:
        downloader = DownloaderFactory.create(
            parsed["type"],
            config,
            api_client,
            file_manager,
            cm,
            None,  # database
            rate_limiter,
            retry_handler,
            queue_manager,
            progress_reporter=None,
        )
        if not downloader:
            return False, [], f"未找到匹配下载器（type={parsed.get('type')!r}）"
        try:
            result = await downloader.download(parsed)
        except Exception as exc:
            return False, [], f"{exc.__class__.__name__}: {exc}"

    paths = _walk_files(per_item_root)
    if result.success > 0:
        return True, paths, ""
    if result.skipped > 0 and paths:
        # 已有本地文件 → 视为成功（幂等）
        return True, paths, ""
    return False, paths, f"DownloadResult: {result}"


async def _run(task_id: str) -> None:
    _log(task_id, f"worker start pid={os.getpid()}")

    try:
        loaded = load_cookies()
    except CookieFormatError as exc:
        state = _read_state(task_id)
        state["state"] = "failed"
        state["finished_at"] = _now_iso()
        state["error"] = f"cookie_invalid: {exc}"
        _atomic_write_state(task_id, state)
        _log(task_id, f"abort: cookie_invalid: {exc}")
        return

    if loaded is None:
        state = _read_state(task_id)
        state["state"] = "failed"
        state["finished_at"] = _now_iso()
        state["error"] = "cookie_missing"
        _atomic_write_state(task_id, state)
        _log(task_id, "abort: cookie_missing")
        return

    cookies, _ = loaded

    state = _read_state(task_id)
    state["state"] = "running"
    state["started_at"] = _now_iso()
    _atomic_write_state(task_id, state)

    ids: List[str] = state["request"]["ids"]
    opts = {
        "music": bool(state["request"].get("music", True)),
        "cover": bool(state["request"].get("cover", True)),
        "json": bool(state["request"].get("json", True)),
    }

    results = []
    succeeded = 0
    failed = 0

    for aweme_id in ids:
        _log(task_id, f"download begin {aweme_id}")
        try:
            ok, paths, err = await _download_one(aweme_id, opts, cookies)
        except Exception as exc:
            ok, paths, err = False, [], f"{exc.__class__.__name__}: {exc}"
            _log(task_id, f"download exception {aweme_id}: {err}\n{traceback.format_exc()}")

        item = {
            "aweme_id": aweme_id,
            "status": "succeeded" if ok else "failed",
            "paths": paths,
            "error": None if ok else err,
        }
        results.append(item)
        if ok:
            succeeded += 1
        else:
            failed += 1
        _log(task_id, f"download done {aweme_id}: ok={ok} files={len(paths)}")

        # 每个 aweme 完成后即时刷状态文件，让 status 工具能看到中间进度
        live = _read_state(task_id)
        live["progress"] = {"total": len(ids), "succeeded": succeeded, "failed": failed}
        live["results"] = results
        _atomic_write_state(task_id, live)

    state = _read_state(task_id)
    state["state"] = "succeeded" if succeeded > 0 else "failed"
    state["finished_at"] = _now_iso()
    state["progress"] = {"total": len(ids), "succeeded": succeeded, "failed": failed}
    state["results"] = results
    if failed > 0 and succeeded == 0:
        state["error"] = "all_failed"
    _atomic_write_state(task_id, state)
    _log(task_id, f"worker end succeeded={succeeded} failed={failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="zero_tool background download worker")
    parser.add_argument("--task-id", dest="task_id", required=True)
    args = parser.parse_args()

    try:
        asyncio.run(_run(args.task_id))
    except Exception as exc:
        _log(args.task_id, f"worker crash: {exc!r}\n{traceback.format_exc()}")
        # 兜底：把状态写成 failed
        try:
            state = _read_state(args.task_id)
            state["state"] = "failed"
            state["finished_at"] = _now_iso()
            state["error"] = f"worker_crash: {exc!r}"
            _atomic_write_state(args.task_id, state)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
