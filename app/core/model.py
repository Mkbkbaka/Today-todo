"""数据结构：一条待办（TodoItem）与一天的计划（Plan）。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_text(text: str) -> str:
    return "".join(text.split()).casefold()


def clean_priority(value: Any) -> Optional[int]:
    """把存进 JSON 的值收拾成 None 或 >=1 的整数。"""
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return None
    return rank if rank >= 1 else None


@dataclass
class TodoItem:
    text: str
    id: str = field(default_factory=new_id)
    done: bool = False
    done_at: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    # 由哪一天顺延而来（YYYY-MM-DD），非顺延则为 None
    carried_from: Optional[str] = None
    # 优先级：1 为最高（红），None 表示还没排优先级
    priority: Optional[int] = None
    tag: Optional[str] = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "done": self.done,
            "done_at": self.done_at,
            "created_at": self.created_at,
            "carried_from": self.carried_from,
            "priority": self.priority,
            "tag": self.tag,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TodoItem":
        return cls(
            text=str(raw.get("text", "")).strip(),
            id=str(raw.get("id") or new_id()),
            done=bool(raw.get("done", False)),
            done_at=raw.get("done_at"),
            created_at=str(raw.get("created_at") or now_iso()),
            carried_from=raw.get("carried_from"),
            priority=clean_priority(raw.get("priority")),
            tag=raw.get("tag"),
            note=str(raw.get("note") or ""),
        )


@dataclass
class Plan:
    """某一天的计划。"""

    date: str
    items: list[TodoItem] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    # 首次弹窗询问的时间；有值说明今天已经问过了
    asked_at: Optional[str] = None
    # 用户点了“今天先跳过”
    skipped: bool = False
    # 用户点了“今天不再提醒”
    dismissed: bool = False
    # “稍后提醒”的目标时间（ISO 字符串）
    snooze_until: Optional[str] = None

    # ---- 查询 ----

    def unfinished(self) -> list[TodoItem]:
        return [i for i in self.items if not i.done]

    def finished_count(self) -> int:
        return sum(1 for i in self.items if i.done)

    def find(self, item_id: str) -> Optional[TodoItem]:
        return next((i for i in self.items if i.id == item_id), None)

    def texts(self) -> set[str]:
        return {normalize_text(i.text) for i in self.items}

    def ordered_items(self) -> list[TodoItem]:
        """展示顺序：排过优先级的按序号排在前，其余保持添加顺序。"""
        indexed = list(enumerate(self.items))
        indexed.sort(key=lambda pair: (pair[1].priority is None, pair[1].priority or 0, pair[0]))
        return [item for _, item in indexed]

    def ranked_items(self) -> list[TodoItem]:
        return sorted((i for i in self.items if i.priority), key=lambda i: i.priority or 0)

    # ---- 修改 ----

    def next_priority(self) -> int:
        used = [i.priority for i in self.items if i.priority]
        return max(used) + 1 if used else 1

    def toggle_priority(self, item_id: str) -> Optional[int]:
        """点一下按点击顺序排到当前最后一位，再点一下取消并重新紧凑编号。"""
        item = self.find(item_id)
        if item is None:
            return None
        if item.priority:
            item.priority = None
            self.compact_priorities()
            return None
        item.priority = self.next_priority()
        self.touch()
        return item.priority

    def compact_priorities(self) -> None:
        """取消中间某一项后把剩余优先级收紧为 1..N，保证颜色连续。"""
        for index, item in enumerate(self.ranked_items(), start=1):
            item.priority = index
        self.touch()

    def add(self, text: str, *, carried_from: Optional[str] = None) -> Optional[TodoItem]:
        text = text.strip()
        if not text:
            return None
        item = TodoItem(text=text, carried_from=carried_from)
        self.items.append(item)
        self.touch()
        return item

    def remove(self, item_id: str) -> bool:
        before = len(self.items)
        self.items = [i for i in self.items if i.id != item_id]
        if len(self.items) != before:
            self.touch()
            return True
        return False

    def touch(self) -> None:
        self.updated_at = now_iso()

    # ---- 序列化 ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "asked_at": self.asked_at,
            "skipped": self.skipped,
            "dismissed": self.dismissed,
            "snooze_until": self.snooze_until,
            "items": [i.to_dict() for i in self.items],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any], date: str) -> "Plan":
        items_raw = raw.get("items")
        items = (
            [
                TodoItem.from_dict(i)
                for i in items_raw
                if isinstance(i, dict) and str(i.get("text", "")).strip()
            ]
            if isinstance(items_raw, list)
            else []
        )
        return cls(
            date=str(raw.get("date") or date),
            items=items,
            created_at=str(raw.get("created_at") or now_iso()),
            updated_at=str(raw.get("updated_at") or now_iso()),
            asked_at=raw.get("asked_at"),
            skipped=bool(raw.get("skipped", False)),
            dismissed=bool(raw.get("dismissed", False)),
            snooze_until=raw.get("snooze_until"),
        )
