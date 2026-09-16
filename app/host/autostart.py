"""开机自启：在“启动”文件夹里放一个指向 pythonw.exe 的快捷方式。

选这个方案的原因：不需要管理员权限、用户可在任务管理器里直接禁用、
想停用只要删掉那个 .lnk，不改注册表也不动计划任务。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from app import paths

log = logging.getLogger(__name__)

LNK_NAME = "今日待办.lnk"
MAIN_SCRIPT = paths.ROOT / "app" / "main.py"

_PS_TEMPLATE = """
$ErrorActionPreference = 'Stop'
$lnkPath = {lnk!r}
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = {target!r}
$lnk.Arguments = {args!r}
$lnk.WorkingDirectory = {cwd!r}
$lnk.WindowStyle = 7
$lnk.Description = '登录后询问今日待办'
$lnk.Save()
Write-Output ('OK ' + $lnkPath)
"""


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / LNK_NAME


def is_installed() -> bool:
    return shortcut_path().exists()


def pythonw_executable() -> str:
    """拿到不带控制台的解释器路径。"""
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    if candidate.exists():
        return str(candidate)
    return str(exe)


def _run_powershell(script: str) -> tuple[bool, str]:
    fd, tmp_name = tempfile.mkstemp(suffix=".ps1", prefix="todaytodo_")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(script, encoding="utf-8-sig")
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(tmp),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return completed.returncode == 0, output.strip()
    except Exception as exc:  # 打不开 PowerShell 或超时
        return False, str(exc)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def install() -> tuple[bool, str]:
    if not MAIN_SCRIPT.exists():
        return False, f"找不到入口脚本：{MAIN_SCRIPT}"
    script = _PS_TEMPLATE.format(
        lnk=str(shortcut_path()),
        target=pythonw_executable(),
        args=f'"{MAIN_SCRIPT}" --autostart',
        cwd=str(paths.ROOT),
    )
    ok, output = _run_powershell(script)
    if ok and is_installed():
        log.info("已安装开机自启：%s", shortcut_path())
        return True, f"已创建启动快捷方式：{shortcut_path()}"
    return False, output or "创建快捷方式失败"


def uninstall() -> tuple[bool, str]:
    path = shortcut_path()
    if not path.exists():
        return True, "本来就没有安装开机自启"
    try:
        path.unlink()
        log.info("已移除开机自启：%s", path)
        return True, f"已删除启动快捷方式：{path}"
    except OSError as exc:
        return False, f"删除失败：{exc}"
