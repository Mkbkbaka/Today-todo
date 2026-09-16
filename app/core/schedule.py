"""日期与提醒时间的计算。"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime, timedelta
from typing import Optional

from app.core.model import Plan

WEEKDAYS_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def now() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def today_str() -> str:
    return now().strftime("%Y-%m-%d")


def date_str(d: _date) -> str:
    return d.strftime("%Y-%m-%d")


def parse_date(text: str) -> Optional[_date]:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def parse_iso(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def pretty_date(text: str) -> str:
    d = parse_date(text)
    if not d:
        return text
    return f"{text} {WEEKDAYS_CN[d.weekday()]}"


def snooze_remaining(plan: Plan) -> Optional[timedelta]:
    """距离“稍后提醒”触发还剩多久；已到点或未设置则返回 None。"""
    target = parse_iso(plan.snooze_until)
    if target is None:
        return None
    delta = target - now()
    return delta if delta.total_seconds() > 0 else None
