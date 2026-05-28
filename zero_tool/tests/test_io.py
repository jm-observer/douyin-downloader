"""测试 _io.py 的纯函数与文件 IO。"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from zero_tool import _io


def test_resolve_workspace_env_override(monkeypatch):
    monkeypatch.setenv("ZERO_WORKSPACE", "/tmp/foo-zero-ws")
    assert _io.resolve_workspace() == Path("/tmp/foo-zero-ws")


def test_resolve_workspace_default_linux(monkeypatch):
    monkeypatch.delenv("ZERO_WORKSPACE", raising=False)
    monkeypatch.setenv("HOME", "/home/zerotest")
    monkeypatch.setattr(sys, "platform", "linux")
    assert _io.resolve_workspace() == Path("/home/zerotest/.config/zero")


def test_resolve_workspace_default_windows(monkeypatch):
    monkeypatch.delenv("ZERO_WORKSPACE", raising=False)
    monkeypatch.setenv("USERPROFILE", "C:\\Users\\zerotest")
    monkeypatch.setattr(sys, "platform", "win32")
    assert _io.resolve_workspace() == Path("C:\\Users\\zerotest") / ".config" / "zero"


def test_load_cookies_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERO_WORKSPACE", str(tmp_path))
    assert _io.load_cookies() is None


def test_load_cookies_parse_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERO_WORKSPACE", str(tmp_path))
    (tmp_path / "douyin").mkdir(parents=True)
    (tmp_path / "douyin" / "cookies.json").write_text("not json", encoding="utf-8")
    with pytest.raises(_io.CookieFormatError):
        _io.load_cookies()


def test_load_cookies_missing_value_field(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERO_WORKSPACE", str(tmp_path))
    (tmp_path / "douyin").mkdir(parents=True)
    (tmp_path / "douyin" / "cookies.json").write_text(
        json.dumps({"updated_at": "x"}), encoding="utf-8"
    )
    with pytest.raises(_io.CookieFormatError):
        _io.load_cookies()


def test_load_cookies_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERO_WORKSPACE", str(tmp_path))
    (tmp_path / "douyin").mkdir(parents=True)
    (tmp_path / "douyin" / "cookies.json").write_text(
        json.dumps(
            {
                "value": {"msToken": "T1", "ttwid": "T2", "empty": ""},
                "updated_at": "2026-05-28T10:00:00+08:00",
            }
        ),
        encoding="utf-8",
    )
    cookies, updated_at = _io.load_cookies()
    # 空值被过滤
    assert cookies == {"msToken": "T1", "ttwid": "T2"}
    assert updated_at == "2026-05-28T10:00:00+08:00"


def test_print_json_compact(capsys):
    _io.print_json({"a": "中文", "b": 1})
    captured = capsys.readouterr()
    # 紧凑无空格、保留中文
    assert captured.out == '{"a":"中文","b":1}'


def test_print_error(capsys):
    _io.print_error("x", "msg", extra="v")
    captured = capsys.readouterr()
    assert captured.out == '{"error":"x","msg":"msg","extra":"v"}'


def test_cookies_path_under_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERO_WORKSPACE", str(tmp_path))
    assert _io.cookies_path() == tmp_path / "douyin" / "cookies.json"


def test_downloads_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERO_WORKSPACE", str(tmp_path))
    assert _io.downloads_root() == tmp_path / "downloads" / "douyin"


def test_tasks_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERO_WORKSPACE", str(tmp_path))
    assert _io.tasks_dir() == tmp_path / "downloads" / ".tasks"
