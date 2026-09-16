"""集中管理项目内所有路径，避免各模块互相引用造成循环依赖。"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 可用环境变量 TODAYTODO_DATA 指向别处，便于试用/测试而不动正式数据
DATA_DIR = Path(os.environ.get("TODAYTODO_DATA") or (ROOT / "data"))
PLANS_DIR = DATA_DIR / "plans"
MD_DIR = DATA_DIR / "md"
LOGS_DIR = ROOT / "logs"

CONFIG_PATH = DATA_DIR / "config.json"
# 第二个实例想唤出已有窗口时写这个文件，主实例轮询到后弹窗
SHOW_REQUEST = DATA_DIR / "show.request"


def ensure_dirs() -> None:
    for d in (DATA_DIR, PLANS_DIR, MD_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    """先写临时文件再原子替换，避免断电/强杀时留下半个文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
