"""按天读写 JSON 计划文件，并生成人类可读的 Markdown 归档。"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Optional

from app import paths
from app.core import schedule
from app.core.model import Plan, TodoItem

log = logging.getLogger(__name__)


def plan_path(date: str) -> Path:
    return paths.PLANS_DIR / f"{date}.json"


def load_plan(date: str) -> Plan:
    """读取某天的计划；文件损坏时隔离备份并返回空计划，绝不阻塞启动。"""
    path = plan_path(date)
    if not path.exists():
        return Plan(date=date)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("顶层不是对象")
        return Plan.from_dict(raw, date)
    except Exception as exc:
        broken = path.with_name(f"{path.name}.bad-{schedule.now().strftime('%Y%m%d%H%M%S')}")
        try:
            path.replace(broken)
            log.error("计划文件损坏，已隔离为 %s：%s", broken.name, exc)
        except OSError:
            log.exception("计划文件损坏且无法隔离：%s", path)
        return Plan(date=date)


def save_plan(plan: Plan) -> None:
    plan.updated_at = schedule.now_iso()
    paths.atomic_write_text(
        plan_path(plan.date),
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )


def previous_unfinished(today: str, lookback_days: int = 14) -> tuple[Optional[str], list[TodoItem]]:
    """往前找最近一天里未完成的事项，用于“昨日未完成”候选区。"""
    start = schedule.parse_date(today)
    if start is None:
        return None, []
    for offset in range(1, lookback_days + 1):
        day = schedule.date_str(start - timedelta(days=offset))
        if not plan_path(day).exists():
            continue
        pending = load_plan(day).unfinished()
        if pending:
            return day, pending
    return None, []


def export_month(month: str) -> Optional[Path]:
    """把某个月的所有计划汇总成一份 Markdown，便于回顾与备份。"""
    files = sorted(paths.PLANS_DIR.glob(f"{month}-*.json"))
    if not files:
        return None
    lines = [f"# {month} 今日待办归档", ""]
    for path in files:
        plan = load_plan(path.stem)
        if not plan.items and not plan.asked_at:
            continue
        lines.append(f"## {schedule.pretty_date(path.stem)}")
        lines.append("")
        if not plan.items:
            lines.append("_（当天没有记录待办）_")
            lines.append("")
            continue
        for item in plan.ordered_items():
            mark = "x" if item.done else " "
            prefix = f"[P{item.priority}] " if item.priority else ""
            suffix = f"  <!-- 顺延自 {item.carried_from} -->" if item.carried_from else ""
            lines.append(f"- [{mark}] {prefix}{item.text}{suffix}")
        lines.append("")
        lines.append(f"完成 {plan.finished_count()}/{len(plan.items)}")
        lines.append("")
    target = paths.MD_DIR / f"{month}.md"
    paths.atomic_write_text(target, "\n".join(lines).rstrip() + "\n")
    return target
