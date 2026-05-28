"""测试 zero_tool 各子命令的高层骨架（不打真实抖音 API）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest


# ------------------------ deps coverage smoke ------------------------------


def test_upstream_imports_resolvable():
    """确保 requirements.txt 装齐后，zero_tool 用到的所有上游模块都能 import。

    既有 smoke 测试全走 cookie_missing 早退路径，从未触发 core/*
    的真实 import；如果 requirements.txt 漏了 aiosqlite 这类 dep，
    既有测试不会发现。本测试在 collection 阶段就强制把全部上游 import 走一遍。
    """
    from auth import CookieManager  # noqa: F401
    from config import ConfigLoader  # noqa: F401
    from control import QueueManager, RateLimiter, RetryHandler  # noqa: F401
    from core import DouyinAPIClient, DownloaderFactory, URLParser  # noqa: F401
    from storage import FileManager  # noqa: F401
    from utils.validators import is_short_url, normalize_short_url  # noqa: F401


# ----------------------------- __main__ dispatch ----------------------------

def test_dispatch_unknown_subcommand():
    proc = subprocess.run(
        [sys.executable, "-m", "zero_tool", "foo"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "unknown subcommand" in proc.stderr


def test_dispatch_no_args():
    proc = subprocess.run(
        [sys.executable, "-m", "zero_tool"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "unknown subcommand" in proc.stderr


# ----------------------------- cookie_status -------------------------------

def test_cookie_status_no_cookie(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "zero_tool", "cookie_status"],
        capture_output=True,
        text=True,
        env={"ZERO_WORKSPACE": str(tmp_path), **_safe_env()},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["valid"] is False
    assert "Cookie 未配置" in out["msg"]


def test_cookie_status_invalid_format(tmp_path):
    (tmp_path / "douyin").mkdir(parents=True)
    (tmp_path / "douyin" / "cookies.json").write_text("not json", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "zero_tool", "cookie_status"],
        capture_output=True,
        text=True,
        env={"ZERO_WORKSPACE": str(tmp_path), **_safe_env()},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["valid"] is False
    assert "格式错误" in out["msg"]


# ----------------------------- resolve_user --------------------------------

def test_resolve_user_no_cookie(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zero_tool",
            "resolve_user",
            "--handle",
            "https://www.douyin.com/user/MS4wLjABAA",
        ],
        capture_output=True,
        text=True,
        env={"ZERO_WORKSPACE": str(tmp_path), **_safe_env()},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["error"] == "cookie_missing"


# ----------------------------- list_works ----------------------------------

def test_list_works_no_cookie(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zero_tool",
            "list_works",
            "--sec-uid",
            "MS4wLjABAAFAKE",
        ],
        capture_output=True,
        text=True,
        env={"ZERO_WORKSPACE": str(tmp_path), **_safe_env()},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["error"] == "cookie_missing"


def test_list_works_bad_date(tmp_path):
    # 即使 cookies 缺失，参数校验也得通过；这里直接装 fake cookies 让流程走到日期校验
    (tmp_path / "douyin").mkdir(parents=True)
    (tmp_path / "douyin" / "cookies.json").write_text(
        json.dumps({"value": {"ttwid": "T"}, "updated_at": ""}),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zero_tool",
            "list_works",
            "--sec-uid",
            "MS4wLjABAAFAKE",
            "--start-time",
            "not-a-date",
        ],
        capture_output=True,
        text=True,
        env={"ZERO_WORKSPACE": str(tmp_path), **_safe_env()},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["error"] == "invalid_input"
    assert "日期格式" in out["msg"]


# ----------------------------- download_submit -----------------------------

def test_download_submit_empty_ids(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "zero_tool", "download_submit", "--ids", ""],
        capture_output=True,
        text=True,
        env={"ZERO_WORKSPACE": str(tmp_path), **_safe_env()},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["error"] == "invalid_input"


def test_download_submit_too_many_ids(tmp_path):
    ids = ",".join(str(i) for i in range(100))
    proc = subprocess.run(
        [sys.executable, "-m", "zero_tool", "download_submit", "--ids", ids],
        capture_output=True,
        text=True,
        env={"ZERO_WORKSPACE": str(tmp_path), **_safe_env()},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["error"] == "invalid_input"
    assert "分批" in out["msg"]


def test_download_submit_writes_task_file(tmp_path, monkeypatch):
    """submit 成功后断言状态文件存在 + state=pending + worker 已被 spawn（mock Popen 不真跑）。"""
    from zero_tool import download_submit

    monkeypatch.setenv("ZERO_WORKSPACE", str(tmp_path))

    with mock.patch.object(download_submit.subprocess, "Popen") as mock_popen:
        # 模拟成功 fork
        mock_popen.return_value = mock.MagicMock()

        # 直接调 run() 走完整路径
        import sys as _sys
        old_argv = _sys.argv
        _sys.argv = ["zero_tool", "--ids", "111,222,333"]
        try:
            from io import StringIO
            buf = StringIO()
            old_stdout = _sys.stdout
            _sys.stdout = buf
            try:
                download_submit.run()
            finally:
                _sys.stdout = old_stdout
            out = json.loads(buf.getvalue())
        finally:
            _sys.argv = old_argv

    assert out["state"] == "pending"
    assert out["ids_count"] == 3
    assert out["task_id"].startswith("task_")

    # 状态文件存在
    state_file = tmp_path / "downloads" / ".tasks" / f"{out['task_id']}.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["state"] == "pending"
    assert state["request"]["ids"] == ["111", "222", "333"]
    assert state["progress"] == {"total": 3, "succeeded": 0, "failed": 0}

    # worker 被 spawn
    mock_popen.assert_called_once()
    spawn_argv = mock_popen.call_args[0][0]
    assert "zero_tool._worker" in spawn_argv
    assert "--task-id" in spawn_argv
    assert out["task_id"] in spawn_argv


# ----------------------------- download_status -----------------------------

def test_download_status_not_found(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zero_tool",
            "download_status",
            "--task-id",
            "task_doesnotexist",
        ],
        capture_output=True,
        text=True,
        env={"ZERO_WORKSPACE": str(tmp_path), **_safe_env()},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["error"] == "not_found"


def test_download_status_pending(tmp_path):
    # 预写一个 pending 状态文件
    tasks = tmp_path / "downloads" / ".tasks"
    tasks.mkdir(parents=True)
    state = {
        "task_id": "task_test_1",
        "state": "pending",
        "submitted_at": "2026-05-28T10:00:00+08:00",
        "started_at": None,
        "finished_at": None,
        "request": {"ids": ["aaa"], "music": True, "cover": True, "json": True},
        "progress": {"total": 1, "succeeded": 0, "failed": 0},
        "results": [],
        "error": None,
    }
    (tasks / "task_test_1.json").write_text(
        json.dumps(state, ensure_ascii=False),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "zero_tool",
            "download_status",
            "--task-id",
            "task_test_1",
        ],
        capture_output=True,
        text=True,
        env={"ZERO_WORKSPACE": str(tmp_path), **_safe_env()},
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["task_id"] == "task_test_1"
    assert out["state"] == "pending"
    assert "elapsed_secs" in out
    assert out["elapsed_secs"] == 0  # started_at 为 None


# ----------------------------- helpers --------------------------------------

def _safe_env():
    """给 subprocess 一个干净但能找到 python 的环境。"""
    import os as _os

    keep = {}
    for k in ("PATH", "PYTHONPATH", "SYSTEMROOT", "HOME", "USERPROFILE", "TEMP", "TMP"):
        if k in _os.environ:
            keep[k] = _os.environ[k]
    return keep
