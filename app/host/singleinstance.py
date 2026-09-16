"""单实例互斥体 + “唤出已有窗口”的信号文件。"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger(__name__)

_ERROR_ALREADY_EXISTS = 183
_MUTEX_NAME = "Local\\TodayTodo_SingleInstance"


class SingleInstance:
    """命名互斥体实现单实例；第二个实例通过信号文件让第一个实例弹窗。"""

    def __init__(self, name: str = _MUTEX_NAME) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        self._kernel32.CreateMutexW.restype = wintypes.HANDLE
        self._handle = None
        self._name = name
        self.already_running = False

    def acquire(self) -> bool:
        """返回 True 表示本进程是唯一实例；False 表示已有实例在运行。"""
        handle = self._kernel32.CreateMutexW(None, False, self._name)
        self._handle = handle
        if not handle:
            log.warning("创建互斥体失败，按单实例继续运行")
            return True
        if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
            self.already_running = True
            return False
        return True

    def release(self) -> None:
        if self._handle:
            try:
                self._kernel32.CloseHandle(self._handle)
            finally:
                self._handle = None


def request_show(flag_path: Path) -> None:
    """第二个实例调用：请正在运行的实例把窗口弹出来。"""
    try:
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.write_text("show", encoding="utf-8")
    except OSError:
        log.exception("写入唤出信号失败：%s", flag_path)


def consume_show_request(flag_path: Path) -> bool:
    """主实例轮询：有信号就消费掉并返回 True。"""
    if not flag_path.exists():
        return False
    try:
        flag_path.unlink()
    except OSError:
        pass
    return True
