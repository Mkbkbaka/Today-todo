"""自检：把数据层与界面层在临时目录里真实跑一遍，不动你的正式数据。

用法：python tools/selftest.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows 控制台默认是 GBK，重设为 UTF-8 以免中文/符号输出报错
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="todaytodo_selftest_"))

    from app import config as appconfig
    from app import paths
    from app.core import carryover, schedule, store
    from app.core.model import Plan

    # 把数据目录指向临时目录，避免污染正式数据
    paths.DATA_DIR = tmp
    paths.PLANS_DIR = tmp / "plans"
    paths.MD_DIR = tmp / "md"
    paths.LOGS_DIR = tmp / "logs"
    paths.CONFIG_PATH = tmp / "config.json"
    paths.SHOW_REQUEST = tmp / "show.request"
    paths.ensure_dirs()

    # ---- 配置 ----
    cfg = appconfig.load()
    check("配置默认值可加载并落盘", paths.CONFIG_PATH.exists())
    cfg.delay_seconds = 3
    appconfig.save(cfg)
    check("配置可保存并读回", appconfig.load().delay_seconds == 3)
    paths.CONFIG_PATH.write_text("{ 坏掉的 json", encoding="utf-8")
    check("配置损坏时回落默认值", appconfig.load().delay_seconds == 8)

    # ---- 计划读写 ----
    today = schedule.today_str()
    yesterday = schedule.date_str(schedule.parse_date(today) - timedelta(days=1))

    plan = store.load_plan(today)
    check("空白日期返回空计划", plan.items == [])
    plan.add("把方案初稿发给老王")
    plan.add("预约牙医")
    plan.add("   ")
    check("空文本不会被添加", len(plan.items) == 2, f"实际 {len(plan.items)} 条")
    store.save_plan(plan)
    check("计划文件写入成功", store.plan_path(today).exists())

    loaded = store.load_plan(today)
    check("重新读取内容一致", [i.text for i in loaded.items] == ["把方案初稿发给老王", "预约牙医"])

    next(i for i in loaded.items if i.text == "预约牙医").done = True
    store.save_plan(loaded)
    check("勾选状态可持久化", store.load_plan(today).finished_count() == 1)

    # ---- 损坏文件隔离 ----
    store.plan_path(today).write_text("这不是 json", encoding="utf-8")
    recovered = store.load_plan(today)
    check("计划文件损坏时返回空计划", recovered.items == [])
    check(
        "损坏文件被隔离备份",
        any(".bad-" in p.name for p in paths.PLANS_DIR.iterdir()),
    )

    # ---- 顺延 ----
    prev = Plan(date=yesterday)
    prev.add("读一章书")
    prev.add("整理桌面")
    next(i for i in prev.items if i.text == "整理桌面").done = True
    store.save_plan(prev)

    source, pending = carryover.previous_unfinished(today)
    check("能找到前一天的未完成项", source == yesterday and [i.text for i in pending] == ["读一章书"])

    today_plan = store.load_plan(today)
    today_plan.add("读一章书")  # 故意重复
    added = carryover.carry_over(today_plan, source or yesterday, pending)
    check("重复文本不会被重复带入", added == 0)
    pending2 = [i for i in prev.unfinished() if i.text == "整理桌面"]
    check("已完成项不在候选里", pending2 == [])

    # ---- Markdown 归档 ----
    target = store.export_month(today[:7])
    check("可导出 Markdown 归档", target is not None and target.exists())
    if target:
        text = target.read_text(encoding="utf-8")
        check("归档内容包含待办文本", "读一章书" in text and "完成 " in text)

    # ---- 时间策略 ----
    check("日期格式化带星期", "周" in schedule.pretty_date(today))
    plan2 = Plan(date=today)
    plan2.snooze_until = (schedule.now() + timedelta(minutes=5)).isoformat(timespec="seconds")
    check("稍后提醒未到点时有剩余时间", schedule.snooze_remaining(plan2) is not None)
    plan2.snooze_until = (schedule.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    check("稍后提醒过期后返回 None", schedule.snooze_remaining(plan2) is None)

    # ---- 优先级 ----
    prio = Plan(date=today)
    a = prio.add("A 事项")
    b = prio.add("B 事项")
    c = prio.add("C 事项")
    check("初始状态没有优先级", [i.priority for i in prio.items] == [None, None, None])

    prio.toggle_priority(c.id)   # 第一个被点的 → P1
    prio.toggle_priority(a.id)   # 第二个被点的 → P2
    check("按点击顺序给出 1、2 号优先级", (c.priority, a.priority) == (1, 2))
    check("列表自动按优先级排序", [i.text for i in prio.ordered_items()] == ["C 事项", "A 事项", "B 事项"])

    prio.toggle_priority(c.id)   # 取消 P1
    check("取消中间优先级后自动紧凑编号", [i.priority for i in prio.ranked_items()] == [1])
    check("被取消的项回到无优先级", c.priority is None)
    # 剩下 A 有优先级排最前，B、C 都无优先级则保持添加顺序
    check("排序随之更新", [i.text for i in prio.ordered_items()] == ["A 事项", "B 事项", "C 事项"])

    store.save_plan(prio)
    check("优先级能持久化", store.load_plan(today).find(a.id).priority == 1)
    archive = store.export_month(today[:7])
    check(
        "Markdown 归档带优先级标记",
        archive is not None and "[P1]" in archive.read_text(encoding="utf-8"),
    )

    from app.ui.theme import PRIORITY_COLORS, priority_color

    check("第一优先级是红色", priority_color(1) == "#e5484d")
    check("颜色随优先级递减且不重复", len({priority_color(i) for i in range(1, 6)}) == 5)
    check("超出调色板时循环取色", priority_color(len(PRIORITY_COLORS) + 1) == PRIORITY_COLORS[0])

    # ---- 自启动模块 ----
    from app.host import autostart

    check("能定位启动文件夹", autostart.startup_dir().is_dir(), str(autostart.startup_dir()))
    check("能定位 pythonw.exe", Path(autostart.pythonw_executable()).exists(), autostart.pythonw_executable())

    # ---- 界面层 ----
    try:
        from app.ui.todo_window import TodoWindow

        ui_plan = store.load_plan(today)
        window = TodoWindow(ui_plan, appconfig.Config(), autostart=True)
        window.update_idletasks()
        window._add_text("界面测试条目")
        window._toggle(window.plan.items[-1])
        window.update_idletasks()
        check("界面能构建并渲染清单", window.plan.items[-1].done is True)
        window._refresh_candidates()
        window.update_idletasks()
        check("窗口保持隐藏（未调用 show）", window.state() == "withdrawn")
        window.destroy()
    except Exception as exc:  # 无图形环境时也要给出明确结论
        check("界面层可正常构建", False, f"{type(exc).__name__}: {exc}")

    print()
    if failures:
        print(f"❌ {len(failures)} 项失败：{'、'.join(failures)}")
        return 1
    print("✅ 全部自检通过")
    print(f"（临时数据目录：{tmp}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
