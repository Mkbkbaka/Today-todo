"""把之前没做完的事项带进新的一天，并做去重。"""

from __future__ import annotations

from app.core import store
from app.core.model import Plan, TodoItem, normalize_text


def previous_unfinished(today: str) -> tuple[str | None, list[TodoItem]]:
    return store.previous_unfinished(today)


def carry_over(today: Plan, source_date: str, items: list[TodoItem]) -> int:
    """把 items 复制到 today，返回实际新增条数（同文本的会跳过）。"""
    existing = today.texts()
    added = 0
    for item in items:
        key = normalize_text(item.text)
        if not item.text.strip() or key in existing:
            continue
        today.add(item.text, carried_from=source_date)
        existing.add(key)
        added += 1
    return added
