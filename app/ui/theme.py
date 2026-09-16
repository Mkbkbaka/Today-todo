"""深蓝主题的配色与立体控件。

立体感来自三点：底部一条更暗的“厚度”边、顶面一圈更亮的高光描边、
按下时顶面下沉 3 像素。这样不依赖任何图片资源，纯 Tk 也能做出实体按键的手感。
"""

from __future__ import annotations

import ctypes
import logging
import tkinter as tk
from ctypes import wintypes
from typing import Callable, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- 配色

BG = "#0d1f33"          # 窗口底色，深蓝
CARD = "#14304a"        # 卡片
INSET = "#0b1a2b"       # 输入框等凹陷区域
BORDER = "#274b6d"      # 卡片描边
FG = "#e9f0f8"          # 主文字
MUTED = "#90a8c0"       # 次要文字
ACCENT = "#2f7cf6"      # 主色
DANGER = "#ff6b5e"

FONT = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_TITLE = ("Microsoft YaHei UI", 13, "bold")
FONT_ITEM_DONE = ("Microsoft YaHei UI", 10, "overstrike")

# 优先级配色：第一优先级最扎眼（红），往下依次减弱，超出就循环
PRIORITY_COLORS = ["#e5484d", "#f76808", "#ffb224", "#30a46c", "#0091ff", "#8e4ec6"]


def priority_color(rank: Optional[int]) -> str:
    if not rank or rank < 1:
        return BORDER
    return PRIORITY_COLORS[(rank - 1) % len(PRIORITY_COLORS)]


def lighten(hex_color: str, amount: float = 0.35) -> str:
    """把颜色朝白色混一点，用来给彩色圆标做高光。"""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
    except (ValueError, IndexError):
        return hex_color
    mix = lambda c: int(c + (255 - c) * amount)  # noqa: E731
    return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"


# 每种按钮：face=顶面, edge=厚度边(暗), top=高光描边(亮), hover=悬停顶面
BUTTON_STYLES: dict[str, dict[str, str]] = {
    "primary": {
        "face": "#2f7cf6",
        "edge": "#123a70",
        "top": "#6aa8ff",
        "fg": "#ffffff",
        "hover": "#4a8ef7",
        "hover_top": "#86bbff",
    },
    "secondary": {
        "face": "#1c4266",
        "edge": "#081726",
        "top": "#33678f",
        "fg": "#dbe8f6",
        "hover": "#24527d",
        "hover_top": "#4987b5",
    },
    "chip": {
        "face": "#1a3d5c",
        "edge": "#081726",
        "top": "#2c5d80",
        "fg": "#cfe1f2",
        "hover": "#235377",  # 悬停稍亮
        "hover_top": "#3d7ba3",
    },
    "ghost": {
        "face": BG,
        "edge": BG,
        "top": BG,
        "fg": MUTED,
        "hover": BG,
        "hover_top": BG,
        "hover_fg": "#ffb0a6",
    },
    "link": {
        "face": BG,
        "edge": BG,
        "top": BG,
        "fg": "#6fa8ff",
        "hover": BG,
        "hover_top": BG,
        "hover_fg": "#a6ccff",
    },
    "danger": {
        "face": "#a8443a",
        "edge": "#57201a",
        "top": "#d4705f",
        "fg": "#fff1ef",
        "hover": "#c2503f",
        "hover_top": "#e28879",
    },
}


class Solid3DButton(tk.Frame):
    """带厚度与高光的实体按钮。"""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Optional[Callable[[], None]] = None,
        *,
        kind: str = "secondary",
        font: tuple = FONT,
        padx: int = 14,
        pady: int = 5,
        thickness: int = 3,
        flat_bg: Optional[str] = None,
    ) -> None:
        style = dict(BUTTON_STYLES.get(kind, BUTTON_STYLES["secondary"]))
        if flat_bg:
            # 扁平变体：贴在卡片上的文字按钮，只要悬停变色，不要厚度
            for key in ("face", "edge", "top", "hover", "hover_top"):
                style[key] = flat_bg
            thickness = 0
        super().__init__(master, bg=style["edge"], bd=0, highlightthickness=0)
        self._style = style
        self._command = command
        self._thickness = thickness
        self._inside = False
        self._pressed = False

        self.face = tk.Frame(
            self,
            bg=style["face"],
            bd=0,
            highlightthickness=1,
            highlightbackground=style["top"],
            highlightcolor=style["top"],
        )
        self.face.pack(fill="both", expand=True, pady=(0, thickness))

        self.label = tk.Label(
            self.face,
            text=text,
            bg=style["face"],
            fg=style["fg"],
            font=font,
            padx=padx,
            pady=pady,
            cursor="hand2",
        )
        self.label.pack(fill="both", expand=True)

        for widget in (self, self.face, self.label):
            widget.configure(cursor="hand2")
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<ButtonPress-1>", self._on_press)
            widget.bind("<ButtonRelease-1>", self._on_release)

    # ---- 外观 ----

    def _paint(self, face: str, top: str, fg: Optional[str] = None) -> None:
        self.face.configure(bg=face, highlightbackground=top, highlightcolor=top)
        self.label.configure(bg=face)
        if fg:
            self.label.configure(fg=fg)

    def _on_enter(self, _event: tk.Event) -> None:
        self._inside = True
        if "hover_fg" in self._style:
            self._paint(self._style["hover"], self._style["hover_top"], self._style["hover_fg"])
        else:
            self._paint(self._style["hover"], self._style["hover_top"])

    def _on_leave(self, _event: tk.Event) -> None:
        self._inside = False
        if self._pressed:
            self._pressed = False
            self.face.pack_configure(pady=(0, self._thickness))
        self._paint(self._style["face"], self._style["top"], self._style["fg"])

    def _on_press(self, _event: tk.Event) -> None:
        self._pressed = True
        # 顶面下沉：厚度边挪到上方
        self.face.pack_configure(pady=(self._thickness, 0))

    def _on_release(self, _event: tk.Event) -> None:
        if not self._pressed:
            return
        self._pressed = False
        self.face.pack_configure(pady=(0, self._thickness))
        if self._inside and self._command:
            self._command()

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)


class Check3D(tk.Canvas):
    """凹陷的方形复选框，选中时填成主色并画出对勾。"""

    SIZE = 18

    def __init__(
        self,
        master: tk.Misc,
        checked: bool = False,
        command: Optional[Callable[[], None]] = None,
        bg: str = CARD,
    ) -> None:
        super().__init__(
            master,
            width=self.SIZE,
            height=self.SIZE,
            bg=bg,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.checked = checked
        self._command = command
        self._hover = False
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        s = self.SIZE
        if self.checked:
            fill = "#4a8ef7" if self._hover else ACCENT
            self.create_rectangle(2, 2, s - 2, s - 2, fill=fill, outline="#7db4ff", width=1)
            self.create_line(5, 9, 8, 12, fill="white", width=2, capstyle="round")
            self.create_line(8, 12, 13, 6, fill="white", width=2, capstyle="round")
        else:
            fill = "#16304a" if self._hover else INSET
            self.create_rectangle(2, 2, s - 2, s - 2, fill=fill, outline="#2b4f72", width=1)
            # 右下加深、左上提亮，做出凹槽感
            self.create_line(3, s - 3, s - 3, s - 3, fill="#06121f")
            self.create_line(s - 3, 3, s - 3, s - 3, fill="#06121f")
            self.create_line(3, 3, s - 3, 3, fill="#3a6488")
            self.create_line(3, 3, 3, s - 3, fill="#3a6488")

    def _click(self, _event: tk.Event) -> None:
        self.checked = not self.checked
        self._draw()
        if self._command:
            self._command()

    def _enter(self, _event: tk.Event) -> None:
        self._hover = True
        self._draw()

    def _leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._draw()

    def set_checked(self, value: bool) -> None:
        self.checked = value
        self._draw()


class PriorityBadge(tk.Canvas):
    """优先级圆标：已排优先级显示彩色数字，未排时悬停提示可点。"""

    SIZE = 19

    def __init__(
        self,
        master: tk.Misc,
        rank: Optional[int] = None,
        command: Optional[Callable[[], None]] = None,
        bg: str = CARD,
    ) -> None:
        super().__init__(
            master,
            width=self.SIZE,
            height=self.SIZE,
            bg=bg,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.rank = rank
        self._command = command
        self._hover = False
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        s = self.SIZE
        center = s / 2
        if self.rank:
            color = priority_color(self.rank)
            if self._hover:
                color = lighten(color, 0.18)
            self.create_oval(1, 1, s - 1, s - 1, fill=color, outline=lighten(color, 0.45), width=1)
            self.create_text(
                center,
                center + 0.5,
                text=str(self.rank),
                fill="#ffffff",
                font=("Microsoft YaHei UI", 8, "bold"),
            )
        else:
            # 未排优先级时保持很淡，避免和左边的复选框抢注意力
            self.create_oval(
                2,
                2,
                s - 2,
                s - 2,
                fill="#16304a" if self._hover else CARD,
                outline=ACCENT if self._hover else "#31536f",
                width=1,
            )
            if self._hover:
                self.create_text(center, center, text="+", fill="#8fbcff", font=("Microsoft YaHei UI", 9))

    def _click(self, _event: tk.Event) -> None:
        if self._command:
            self._command()

    def _enter(self, _event: tk.Event) -> None:
        self._hover = True
        self._draw()

    def _leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._draw()

    def set_rank(self, rank: Optional[int]) -> None:
        self.rank = rank
        self._draw()


def _bgr(hex_color: str) -> int:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (b << 16) | (g << 8) | r


def _window_handles(window: tk.Misc) -> list[int]:
    """Tk 顶层窗口有两层句柄：真正带标题栏的是外层 TkTopLevel。"""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetParent.argtypes = (wintypes.HWND,)
    user32.GetParent.restype = wintypes.HWND
    user32.GetAncestor.argtypes = (wintypes.HWND, ctypes.c_uint)
    user32.GetAncestor.restype = wintypes.HWND
    inner = int(window.winfo_id())
    handles: list[int] = []
    for handle in (user32.GetParent(inner), user32.GetAncestor(inner, 4), inner):
        if handle and handle not in handles:
            handles.append(handle)
    return handles


def apply_dark_titlebar(window: tk.Misc, retries: int = 3) -> bool:
    """把 Windows 标题栏也刷成深蓝，避免顶部留一条白条。

    窗口刚 deiconify 时外层句柄可能还没就绪，所以失败会自动重试几次。
    """
    try:
        window.update_idletasks()
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = (
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        dark = ctypes.c_int(1)
        caption = ctypes.c_int(_bgr(BG))
        text = ctypes.c_int(_bgr(FG))
        applied = False
        for hwnd in _window_handles(window):
            if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4) != 0:
                continue
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
            dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), 4)
            applied = True
        if applied:
            return True
    except Exception:
        log.debug("设置深色标题栏失败", exc_info=True)
    if retries > 0:
        try:
            window.after(250, lambda: apply_dark_titlebar(window, retries - 1))
        except tk.TclError:
            pass
    return False
