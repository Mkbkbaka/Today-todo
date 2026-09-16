"""今日待办小窗口：录入与清单两种模式共用同一个窗口。

设计要点：
- 关闭窗口 ≠ 退出：点 ✕ 会问“后台运行还是退出程序”。
- 已提交的条目即时落盘，强制结束进程也不会丢。
- 每天最多主动打断一次：今天问过就不再强弹录入窗口。
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from datetime import timedelta
from tkinter import ttk
from typing import Callable, Optional

from app import config as appconfig
from app import paths
from app.core import carryover, schedule, store
from app.core.model import Plan, TodoItem
from app.host import singleinstance
from app.ui.theme import (
    ACCENT,
    BG,
    BORDER,
    CARD,
    INSET,
    FG,
    FONT,
    FONT_ITEM_DONE,
    FONT_SMALL,
    FONT_TITLE,
    MUTED,
    Check3D,
    PriorityBadge,
    Solid3DButton,
    apply_dark_titlebar,
    priority_color,
)

log = logging.getLogger(__name__)

MAX_HIDDEN_HOURS = 8      # 后台驻留超时
TICK_MS = 15_000          # 统一心跳：跨天、稍后提醒、空闲收起、后台超时
POLL_MS = 1_500           # 轮询“唤出窗口”信号
TOPMOST_MS = 60_000       # 弹出后置顶多久


class ScrollFrame(tk.Frame):
    """可滚动容器，内容放在 .inner 里。"""

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(master, bg=CARD, **kwargs)
        # 滚动区最多长到这么高，超出就出现滚动条，窗口不再继续变高
        self.max_content_height = 300
        self.canvas = tk.Canvas(self, bg=CARD, highlightthickness=0, bd=0)
        self.vbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview, style="Dark.Vertical.TScrollbar"
        )
        self.inner = tk.Frame(self.canvas, bg=CARD)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))
        self.width_callbacks: list[Callable[[int], None]] = []

    def _on_inner(self, _event: tk.Event) -> None:
        self.refresh_scrollregion()

    def refresh_scrollregion(self) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._sync_height()

    def _sync_height(self) -> None:
        """让画布高度跟着内容走（有上限），这样窗口能刚好装下清单。"""
        try:
            target = max(56, min(self.inner.winfo_reqheight(), self.max_content_height))
            if int(self.canvas.cget("height")) != target:
                self.canvas.configure(height=target)
        except (tk.TclError, ValueError):
            pass

    def _on_canvas(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)
        for cb in self.width_callbacks:
            cb(event.width)

    def _on_wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class ChoiceDialog(tk.Toplevel):
    """深蓝主题的模态选择框。返回被选中项的 key；直接关掉返回 None。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        title: str,
        message: str,
        options: list[tuple[str, str, str]],
        default: Optional[str] = None,
    ) -> None:
        super().__init__(master)
        self.result: Optional[str] = None
        self._default = default or options[0][0]
        self.withdraw()
        self.title(title)
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(master)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=16)
        tk.Label(body, text=title, bg=BG, fg=FG, font=FONT_TITLE, anchor="w").pack(fill="x")
        tk.Label(
            body,
            text=message,
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
            justify="left",
            anchor="w",
            wraplength=340,
        ).pack(fill="x", pady=(8, 16))

        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        for index, (key, label, kind) in enumerate(options):
            button = Solid3DButton(
                row,
                label,
                command=lambda k=key: self._choose(k),
                kind=kind,
                padx=16,
                pady=7,
            )
            button.pack(side="left", expand=True, fill="x", padx=(0 if index == 0 else 10, 0))

        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._choose(self._default))
        self.update_idletasks()
        self._center_on(master)
        self.deiconify()
        apply_dark_titlebar(self)
        self.grab_set()
        self.focus_force()

    def _center_on(self, master: tk.Misc) -> None:
        try:
            width, height = self.winfo_reqwidth(), self.winfo_reqheight()
            x = master.winfo_rootx() + (master.winfo_width() - width) // 2
            y = master.winfo_rooty() + (master.winfo_height() - height) // 3
            screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(0, min(x, screen_w - width))
            y = max(0, min(y, screen_h - height))
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _choose(self, key: str) -> None:
        self.result = key
        self._close()

    def _cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    @classmethod
    def ask(cls, master: tk.Misc, **kwargs) -> Optional[str]:
        dialog = cls(master, **kwargs)
        master.wait_window(dialog)
        return dialog.result


class TodoWindow(tk.Tk):
    def __init__(self, plan: Plan, cfg: appconfig.Config, *, autostart: bool = False) -> None:
        super().__init__()
        self.plan = plan
        self.cfg = cfg
        self.autostart = autostart

        self._candidate_source: Optional[str] = None
        self._candidate_items: list[TodoItem] = []
        self._candidate_checks: dict[str, Check3D] = {}
        self._item_labels: list[tk.Label] = []
        self._editing = False
        self._hidden_since: Optional[float] = None
        self._last_activity = time.time()
        self._dialog_open = False
        self._fitted = False

        self.withdraw()  # 先藏起来，等逻辑决定何时出现
        self.title("今日待办")
        self.configure(bg=BG)
        self.minsize(380, 400)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._init_ttk()
        self._apply_geometry()
        self._build()
        self._refresh_candidates()
        self._refresh_items()
        self._bind_activity()

    # ------------------------------------------------------------------ 布局

    def _init_ttk(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.Vertical.TScrollbar",
            background="#1d4467",
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=MUTED,
            lightcolor="#1d4467",
            darkcolor="#1d4467",
            relief="flat",
            gripcount=0,
        )
        style.map("Dark.Vertical.TScrollbar", background=[("active", "#2f7cf6")])

    def _apply_geometry(self) -> None:
        w, h = self.cfg.window_width, self.cfg.window_height
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = self.cfg.window_x, self.cfg.window_y
        if x is None or y is None or not (0 <= x <= screen_w - 200) or not (0 <= y <= screen_h - 150):
            x = max(0, screen_w - w - 24)
            y = max(0, screen_h - h - 72)
        self.geometry(f"{w}x{h}+{x}+{y}")

    @staticmethod
    def _card(parent: tk.Misc) -> tk.Frame:
        return tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)

    def _build(self) -> None:
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=14, pady=12)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        head = tk.Frame(outer, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        self.title_label = tk.Label(
            head,
            text=f"今天是 {schedule.pretty_date(self.plan.date)}",
            bg=BG,
            fg=FG,
            font=FONT_TITLE,
            anchor="w",
        )
        self.title_label.pack(side="left")
        self.stats_label = tk.Label(head, text="", bg=BG, fg=MUTED, font=FONT_SMALL, anchor="e")
        self.stats_label.pack(side="right")

        tk.Label(
            outer,
            text="今天要完成什么？回车添加一条，Shift+回车换行。",
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        # ---- 昨日未完成（有候选时才显示） ----
        self.candidates_card = self._card(outer)
        self.candidates_card.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.candidates_head = tk.Frame(self.candidates_card, bg=CARD)
        self.candidates_head.pack(fill="x", padx=12, pady=(9, 4))
        self.candidates_title = tk.Label(
            self.candidates_head, text="", bg=CARD, fg=FG, font=FONT_SMALL, anchor="w"
        )
        self.candidates_title.pack(side="left")
        Solid3DButton(
            self.candidates_head,
            "全部带入",
            command=self._carry_all,
            kind="link",
            font=FONT_SMALL,
            padx=8,
            pady=2,
            flat_bg=CARD,
        ).pack(side="right")
        self.candidates_body = tk.Frame(self.candidates_card, bg=CARD)
        self.candidates_body.pack(fill="x", padx=12, pady=(0, 10))
        self.candidates_card.grid_remove()

        # ---- 输入区 ----
        entry_card = self._card(outer)
        entry_card.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.entry = tk.Text(
            entry_card,
            height=2,
            font=FONT,
            wrap="word",
            bd=0,
            relief="flat",
            bg=INSET,
            fg=FG,
            insertbackground=ACCENT,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            padx=10,
            pady=8,
            undo=True,
        )
        self.entry.pack(fill="x", padx=8, pady=(8, 6))
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Control-Return>", lambda _e: self._submit_entry())
        self.entry.bind("<Shift-Return>", lambda _e: None)

        self.templates_row = tk.Frame(entry_card, bg=CARD)
        self.templates_row.pack(fill="x", padx=8, pady=(0, 9))
        self._build_templates()

        # ---- 清单区 ----
        list_card = self._card(outer)
        list_card.grid(row=4, column=0, sticky="nsew")
        list_head = tk.Frame(list_card, bg=CARD)
        list_head.pack(fill="x", padx=12, pady=(9, 2))
        tk.Label(
            list_head, text="今日清单", bg=CARD, fg=MUTED, font=FONT_SMALL, anchor="w"
        ).pack(side="left")
        tk.Label(
            list_head,
            text="点左侧圆标按点击顺序排优先级",
            bg=CARD,
            fg="#6f88a3",
            font=FONT_SMALL,
            anchor="e",
        ).pack(side="right")
        self.scroll = ScrollFrame(list_card)
        self.scroll.pack(fill="both", expand=True, padx=(6, 2), pady=(0, 8))
        self.scroll.width_callbacks.append(self._on_list_width)
        self.items_inner = self.scroll.inner

        # ---- 底部按钮 ----
        footer = tk.Frame(outer, bg=BG)
        footer.grid(row=5, column=0, sticky="ew", pady=(12, 0))

        self.save_btn = Solid3DButton(
            footer, "保存并关闭", command=self._save_and_hide, kind="primary", padx=16, pady=7
        )
        self.save_btn.pack(side="left")

        self.snooze_btn = Solid3DButton(
            footer, "稍后提醒 ▾", command=self._post_snooze_menu, kind="secondary", padx=12, pady=7
        )
        self.snooze_btn.pack(side="left", padx=(10, 0))

        self.snooze_menu = tk.Menu(
            self,
            tearoff=False,
            bg=CARD,
            fg=FG,
            activebackground=ACCENT,
            activeforeground="#ffffff",
            bd=0,
            relief="flat",
            font=FONT_SMALL,
        )
        for minutes in self.cfg.snooze_options:
            self.snooze_menu.add_command(
                label=f"{minutes} 分钟后", command=lambda m=minutes: self._snooze(m)
            )
        self.snooze_menu.add_separator()
        self.snooze_menu.add_command(label="今天不再提醒", command=self._dismiss_today)

        Solid3DButton(
            footer,
            "今天先跳过",
            command=self._skip_today,
            kind="ghost",
            font=FONT_SMALL,
            padx=8,
            pady=5,
            flat_bg=BG,
        ).pack(side="right")

        self.bind("<Escape>", lambda _e: self._hide())

    def _build_templates(self) -> None:
        for child in self.templates_row.winfo_children():
            child.destroy()
        if not self.cfg.templates:
            return
        tk.Label(self.templates_row, text="常用：", bg=CARD, fg=MUTED, font=FONT_SMALL).pack(
            side="left", pady=(4, 0)
        )
        for text in self.cfg.templates:
            Solid3DButton(
                self.templates_row,
                text,
                command=lambda t=text: self._add_text(t),
                kind="chip",
                font=FONT_SMALL,
                padx=9,
                pady=3,
                thickness=2,
            ).pack(side="left", padx=(6, 0), pady=(2, 0))

    def _on_list_width(self, width: int) -> None:
        wrap = max(120, width - 80)
        for label in self._item_labels:
            label.configure(wraplength=wrap)

    # ------------------------------------------------------------- 清单渲染

    def _refresh_items(self) -> None:
        for child in self.items_inner.winfo_children():
            child.destroy()
        self._item_labels.clear()

        if not self.plan.items:
            tk.Label(
                self.items_inner,
                text="还没有待办。在上面输入一条，回车即可添加。",
                bg=CARD,
                fg=MUTED,
                font=FONT_SMALL,
                anchor="w",
                justify="left",
            ).pack(fill="x", padx=10, pady=8)
        else:
            for item in self.plan.ordered_items():
                self._build_item_row(item)

        total = len(self.plan.items)
        done = self.plan.finished_count()
        self.stats_label.configure(text=f"{done}/{total} 已完成" if total else "")
        self.after_idle(self.scroll.refresh_scrollregion)

    def _build_item_row(self, item: TodoItem) -> None:
        rank = item.priority
        row = tk.Frame(self.items_inner, bg=CARD)
        row.pack(fill="x", padx=(6, 2), pady=2)

        # 左侧色条：把优先级一眼铺满整行；没排优先级时用卡片色占位以保持对齐
        tk.Frame(row, bg=priority_color(rank) if rank else CARD, width=3).pack(
            side="left", fill="y", padx=(0, 7)
        )

        Check3D(
            row,
            checked=item.done,
            command=lambda: self._toggle(item),
            bg=CARD,
        ).pack(side="left", anchor="n", pady=(3, 0))

        PriorityBadge(
            row,
            rank=rank,
            command=lambda: self._assign_priority(item),
            bg=CARD,
        ).pack(side="left", anchor="n", padx=(7, 0), pady=(2, 0))

        label = tk.Label(
            row,
            text=item.text,
            bg=CARD,
            fg=MUTED if item.done else FG,
            font=FONT_ITEM_DONE if item.done else FONT,
            justify="left",
            anchor="w",
            wraplength=280,
        )
        label.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=3)
        label.bind("<Double-Button-1>", lambda _e, it=item, lb=label: self._begin_edit(it, lb))
        self._item_labels.append(label)

        if item.carried_from:
            tk.Label(
                row,
                text=f"↪{item.carried_from[5:]}",
                bg=CARD,
                fg="#6f88a3",
                font=FONT_SMALL,
            ).pack(side="right", padx=(0, 6))

        Solid3DButton(
            row,
            "✕",
            command=lambda: self._delete(item),
            kind="ghost",
            font=FONT_SMALL,
            padx=6,
            pady=2,
            flat_bg=CARD,
        ).pack(side="right")

    def _begin_edit(self, item: TodoItem, label: tk.Label) -> None:
        if self._editing:
            return
        self._editing = True
        parent = label.master
        entry = tk.Entry(
            parent,
            font=FONT,
            bd=0,
            relief="flat",
            bg=INSET,
            fg=FG,
            insertbackground=ACCENT,
            highlightthickness=1,
            highlightbackground=ACCENT,
            highlightcolor=ACCENT,
        )
        label.pack_forget()
        entry.pack(side="left", fill="x", expand=True, padx=(6, 4), pady=2)
        entry.insert(0, item.text)
        entry.focus_set()
        entry.select_range(0, "end")
        done = {"value": False}

        def finish(save: bool) -> None:
            if done["value"]:
                return
            done["value"] = True
            text = entry.get().strip()
            if save and text and text != item.text:
                item.text = text
                self.plan.touch()
                self._save()
            self._editing = False
            self._refresh_items()

        entry.bind("<Return>", lambda _e: finish(True))
        entry.bind("<Escape>", lambda _e: finish(False))
        entry.bind("<FocusOut>", lambda _e: finish(True))

    # --------------------------------------------------------------- 顶部候选

    def _refresh_candidates(self) -> None:
        source, items = carryover.previous_unfinished(self.plan.date)
        for child in self.candidates_body.winfo_children():
            child.destroy()
        self._candidate_checks.clear()
        self._candidate_source = source

        existing = self.plan.texts()
        pending = [i for i in items if "".join(i.text.split()).casefold() not in existing]
        self._candidate_items = pending

        if not pending:
            self.candidates_card.grid_remove()
            return

        self.candidates_title.configure(text=f"{source} 没做完的（勾选后带入今天）")
        for item in pending:
            row = tk.Frame(self.candidates_body, bg=CARD)
            row.pack(fill="x", pady=1)
            check = Check3D(row, checked=False, bg=CARD)
            check.pack(side="left", anchor="n", pady=(1, 0))
            self._candidate_checks[item.id] = check
            label = tk.Label(
                row,
                text=item.text,
                bg=CARD,
                fg=FG,
                font=FONT_SMALL,
                anchor="w",
                justify="left",
                wraplength=300,
                cursor="hand2",
            )
            label.pack(side="left", fill="x", expand=True, padx=(7, 0))
            label.bind("<Button-1>", lambda _e, c=check: self._toggle_check(c))
        self.candidates_card.grid()

    @staticmethod
    def _toggle_check(check: Check3D) -> None:
        check.set_checked(not check.checked)

    def _carry_all(self) -> None:
        for check in self._candidate_checks.values():
            check.set_checked(True)
        self._carry_selected()

    def _carry_selected(self) -> None:
        if not self._candidate_source:
            return
        chosen = [
            item for item in self._candidate_items if self._is_checked(item.id)
        ]
        added = carryover.carry_over(self.plan, self._candidate_source, chosen)
        if added:
            self._save()
            log.info("带入 %d 条未完成事项", added)
        self._refresh_candidates()
        self._refresh_items()

    def _is_checked(self, item_id: str) -> bool:
        check = self._candidate_checks.get(item_id)
        return bool(check and check.checked)

    # ----------------------------------------------------------------- 操作

    def _on_return(self, event: tk.Event) -> Optional[str]:
        if event.state & 0x0001:  # 按住 Shift → 换行
            return None
        if not self.cfg.enter_submits:
            return None
        return self._submit_entry()

    def _submit_entry(self) -> str:
        raw = self.entry.get("1.0", "end").strip()
        if raw:
            for line in [l.strip() for l in raw.splitlines() if l.strip()]:
                self.plan.add(line)
            self.entry.delete("1.0", "end")
            self._save()
            self._refresh_items()
            self._refresh_candidates()
        self._touch()
        return "break"

    def _add_text(self, text: str) -> None:
        self.plan.add(text)
        self._save()
        self._refresh_items()
        self._refresh_candidates()
        self._touch()

    def _toggle(self, item: TodoItem) -> None:
        item.done = not item.done
        item.done_at = schedule.now_iso() if item.done else None
        self.plan.touch()
        self._save()
        self._refresh_items()
        self._touch()

    def _delete(self, item: TodoItem) -> None:
        self.plan.remove(item.id)
        self._save()
        self._refresh_items()
        self._touch()

    def _assign_priority(self, item: TodoItem) -> None:
        """点圆标：按点击顺序排到末位；已排过的再点一次取消。"""
        rank = self.plan.toggle_priority(item.id)
        self._save()
        self._refresh_items()
        self._touch()
        if rank:
            log.info("设定优先级 P%d：%s", rank, item.id)
        else:
            log.info("取消优先级：%s", item.id)

    # ------------------------------------------------------------- 显隐与提醒

    def start(self) -> None:
        """按启动方式决定第一屏行为。"""
        # 无论哪种启动方式，都要持续处理“稍后提醒/跨天/被再次唤出”
        self.after(TICK_MS, self._tick)
        self.after(POLL_MS, self._poll_show_request)

        if not self.autostart:
            self._show()
            return
        if self.plan.dismissed or self.plan.skipped:
            log.info("今天已跳过/不再提醒，静默退出")
            self.destroy()
            return

        mode = "ask" if (not self.plan.asked_at and not self.plan.items) else "list"
        if mode == "list" and self.cfg.hide_when_recorded:
            log.info("今天已有记录且配置为静默，退出")
            self.destroy()
            return

        if schedule.snooze_remaining(self.plan):
            log.info("处于稍后提醒状态，先隐藏")
            self._hidden_since = time.time()
        else:
            self.after(max(0, self.cfg.delay_seconds) * 1000, self._show)

    def _show(self, manual: bool = False) -> None:
        self.plan.snooze_until = None
        self._hidden_since = None
        self.deiconify()
        if self.cfg.auto_fit_height and not self._fitted:
            self._fitted = True
            self._fit_to_content()
        self.lift()
        if self.cfg.keep_on_top:
            self.attributes("-topmost", True)
            self.after(TOPMOST_MS, self._release_topmost)
        self.focus_force()
        if not manual:
            self.entry.focus_set()
        if not self.plan.asked_at:
            self.plan.asked_at = schedule.now_iso()
        apply_dark_titlebar(self)
        self._save()
        self._refresh_candidates()
        self._refresh_items()
        self._touch()
        log.info("窗口已显示（%s）", "手动" if manual else "自动")

    def _fit_to_content(self) -> None:
        """按内容定高，并保持右下角不跑出屏幕。"""
        try:
            self.update_idletasks()
            screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
            width = self.cfg.window_width
            height = max(400, min(self.winfo_reqheight(), int(screen_h * 0.9)))
            right = min(self.winfo_x() + self.winfo_width(), screen_w - 12)
            bottom = min(self.winfo_y() + self.winfo_height(), screen_h - 12)
            x = max(12, right - width)
            y = max(12, bottom - height)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            pass

    def _release_topmost(self) -> None:
        try:
            if self.state() != "withdrawn":
                self.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _hide(self) -> None:
        self._persist_geometry()
        self._save()
        self.withdraw()
        self._hidden_since = time.time()
        log.info("窗口收起，后台继续运行")

    def _save_and_hide(self) -> None:
        self._hide()

    def _on_close(self) -> None:
        """点 ✕：问用户是后台运行还是彻底退出。"""
        if self._dialog_open:
            return
        self._dialog_open = True
        try:
            choice = ChoiceDialog.ask(
                self,
                title="关掉窗口后要怎么处理？",
                message=(
                    "后台运行：窗口收起来，稍后提醒仍然生效，"
                    "再点一次图标就能唤回。\n"
                    "退出程序：彻底结束，今天不再提醒（明天开机照常）。"
                ),
                options=[
                    ("background", "后台运行", "primary"),
                    ("quit", "退出程序", "danger"),
                ],
                default="background",
            )
        finally:
            self._dialog_open = False
        if choice == "quit":
            self._quit()
        elif choice == "background":
            self._hide()
        else:
            log.info("关闭对话框被取消，窗口保持打开")

    def _post_snooze_menu(self) -> None:
        try:
            x = self.snooze_btn.winfo_rootx()
            y = self.snooze_btn.winfo_rooty() + self.snooze_btn.winfo_height()
            self.snooze_menu.tk_popup(x, y)
        finally:
            self.snooze_menu.grab_release()

    def _snooze(self, minutes: int) -> None:
        target = schedule.now() + timedelta(minutes=minutes)
        self.plan.snooze_until = target.isoformat(timespec="seconds")
        self.plan.dismissed = False
        self._save()
        log.info("稍后提醒：%s", self.plan.snooze_until)
        self._hide()

    def _dismiss_today(self) -> None:
        self.plan.dismissed = True
        self.plan.snooze_until = None
        self._save()
        store.export_month(self.plan.date[:7])
        log.info("今天不再提醒")
        self.destroy()

    def _skip_today(self) -> None:
        self.plan.skipped = True
        self.plan.snooze_until = None
        self._save()
        store.export_month(self.plan.date[:7])
        log.info("今天先跳过")
        self.destroy()

    def _quit(self) -> None:
        self._persist_geometry()
        self._save()
        store.export_month(self.plan.date[:7])
        log.info("用户退出程序")
        self.destroy()

    def _poll_show_request(self) -> None:
        try:
            if singleinstance.consume_show_request(paths.SHOW_REQUEST):
                log.info("收到唤出信号")
                self._show(manual=True)
        except tk.TclError:
            return  # 窗口已销毁
        finally:
            self._safe_after(POLL_MS, self._poll_show_request)

    # ---------------------------------------------------------------- 定时任务

    def _tick(self) -> None:
        try:
            self._check_rollover()
            self._check_snooze()
            self._check_idle()
            self._check_hidden_timeout()
        except tk.TclError:
            return
        except Exception:
            log.exception("定时任务出错")
        finally:
            self._safe_after(TICK_MS, self._tick)

    def _safe_after(self, ms: int, func: Callable[[], None]) -> None:
        """窗口已销毁时安静地放弃下一次调度。"""
        try:
            self.after(ms, func)
        except tk.TclError:
            pass

    def _check_rollover(self) -> None:
        today = schedule.today_str()
        if today == self.plan.date:
            return
        previous = self.plan
        pending = previous.unfinished()
        log.info("跨天：%s → %s", previous.date, today)
        self._save()
        self.plan = store.load_plan(today)
        self.title_label.configure(text=f"今天是 {schedule.pretty_date(today)}")
        self._refresh_candidates()
        self._refresh_items()
        if pending and self.state() == "normal":
            choice = ChoiceDialog.ask(
                self,
                title="新的一天",
                message=(
                    f"已经进入 {schedule.pretty_date(today)}。\n"
                    f"把昨天没完成的 {len(pending)} 项带到今天吗？"
                ),
                options=[("carry", "带到今天", "primary"), ("leave", "留在昨天", "secondary")],
                default="carry",
            )
            if choice == "carry":
                added = carryover.carry_over(self.plan, previous.date, pending)
                self._save()
                self._refresh_items()
                self._refresh_candidates()
                log.info("跨天带入 %d 条", added)
        self._save()

    def _check_snooze(self) -> None:
        if self.state() != "withdrawn" or not self.plan.snooze_until:
            return
        if schedule.snooze_remaining(self.plan):
            return
        log.info("稍后提醒到点")
        self._show()

    def _check_idle(self) -> None:
        if self.state() != "normal":
            return
        if time.time() - self._last_activity > max(1, self.cfg.idle_autoclose_minutes) * 60:
            log.info("无操作自动收起")
            self._hide()

    def _check_hidden_timeout(self) -> None:
        if self.state() != "withdrawn" or self._hidden_since is None:
            return
        if self.plan.snooze_until:
            return
        if time.time() - self._hidden_since > MAX_HIDDEN_HOURS * 3600:
            log.info("后台驻留超时，退出")
            self._quit()

    # -------------------------------------------------------------------- 杂项

    def _bind_activity(self) -> None:
        for widget in (self, self.entry):
            widget.bind("<Key>", self._on_activity, add="+")
            widget.bind("<Button>", self._on_activity, add="+")

    def _on_activity(self, _event: Optional[tk.Event] = None) -> None:
        self._touch()

    def _touch(self) -> None:
        self._last_activity = time.time()

    def _persist_geometry(self) -> None:
        try:
            self.cfg.window_width = self.winfo_width()
            if not self.cfg.auto_fit_height:
                self.cfg.window_height = self.winfo_height()
            self.cfg.window_x = self.winfo_x()
            self.cfg.window_y = self.winfo_y()
            appconfig.save(self.cfg)
        except Exception:
            log.exception("保存窗口位置失败")

    def _save(self) -> None:
        try:
            store.save_plan(self.plan)
        except Exception:
            log.exception("保存计划失败")
