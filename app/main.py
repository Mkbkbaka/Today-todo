"""今日待办 —— 入口。

用法：
    pythonw app/main.py --autostart      开机自启（延迟后弹窗，出错不打扰）
    pythonw app/main.py                  手动启动（立刻弹窗；已在运行则唤出原窗口）
    python  app/main.py --install-autostart
    python  app/main.py --uninstall-autostart
    python  app/main.py --status         打印当前状态
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import logging.handlers
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import __version__, paths  # noqa: E402
from app import config as appconfig  # noqa: E402
from app.core import schedule, store  # noqa: E402
from app.host import autostart, singleinstance  # noqa: E402

log = logging.getLogger("app")


def out(text: str = "") -> None:
    """pythonw 下没有控制台，这里静默忽略。"""
    if sys.stdout is None:
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        print(text)
    except Exception:
        pass


def setup_logging(verbose: bool = False) -> None:
    paths.ensure_dirs()
    handler = logging.handlers.RotatingFileHandler(
        paths.LOGS_DIR / "app.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)


def enable_dpi_awareness() -> float:
    """声明进程 DPI 感知，避免高分屏下界面发虚、坐标偏移。必须在创建 Tk 之前调用。"""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                log.debug("无法设置 DPI 感知，使用系统默认", exc_info=True)
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def run_gui(autostart_mode: bool) -> int:
    cfg = appconfig.load()
    guard = singleinstance.SingleInstance()
    if not guard.acquire():
        log.info("已有实例在运行，请求唤出窗口")
        singleinstance.request_show(paths.SHOW_REQUEST)
        return 0

    enable_dpi_awareness()

    from app.ui.todo_window import TodoWindow  # 延迟导入，让 --status 等命令不加载 GUI

    plan = store.load_plan(schedule.today_str())
    log.info(
        "启动：%s，已有 %d 条，模式=%s",
        plan.date,
        len(plan.items),
        "autostart" if autostart_mode else "manual",
    )
    window = TodoWindow(plan, cfg, autostart=autostart_mode)
    window.start()
    try:
        window.mainloop()
    finally:
        guard.release()
    return 0


def print_status() -> None:
    cfg = appconfig.load()
    today = schedule.today_str()
    plan = store.load_plan(today)
    out(f"今日待办 v{__version__}")
    out(f"  项目目录   : {paths.ROOT}")
    out(f"  解释器     : {sys.executable}")
    out(f"  数据目录   : {paths.DATA_DIR}")
    out(f"  今日文件   : {store.plan_path(today)}")
    out(f"  今日待办   : {len(plan.items)} 条（已完成 {plan.finished_count()}）")
    out(f"  今天问过没 : {'是 ' + str(plan.asked_at) if plan.asked_at else '否'}")
    out(f"  跳过/不再提醒: {'是' if (plan.skipped or plan.dismissed) else '否'}")
    out(f"  开机自启   : {'已安装' if autostart.is_installed() else '未安装'}")
    out(f"  快捷方式   : {autostart.shortcut_path()}")
    out(f"  启动目标   : {autostart.pythonw_executable()}")
    out(f"  延迟秒数   : {cfg.delay_seconds}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="today-todo", description="登录后询问今日待办")
    parser.add_argument("--autostart", action="store_true", help="开机自启模式")
    parser.add_argument("--install-autostart", action="store_true", help="安装开机自启")
    parser.add_argument("--uninstall-autostart", action="store_true", help="移除开机自启")
    parser.add_argument("--status", action="store_true", help="打印当前状态")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    if args.install_autostart:
        ok, message = autostart.install()
        out(("✅ " if ok else "❌ ") + message)
        return 0 if ok else 1

    if args.uninstall_autostart:
        ok, message = autostart.uninstall()
        out(("✅ " if ok else "❌ ") + message)
        return 0 if ok else 1

    if args.status:
        print_status()
        return 0

    try:
        return run_gui(args.autostart)
    except Exception:
        log.exception("程序异常退出")
        if not args.autostart:
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
