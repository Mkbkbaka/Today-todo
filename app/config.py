"""用户配置：读写 data/config.json，字段缺失或损坏时回落到默认值。"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field

from app import paths

DEFAULT_TEMPLATES = ["晨会", "写日报", "运动"]


@dataclass
class Config:
    # 登录后延迟多少秒才弹窗（等桌面与输入法就绪）
    delay_seconds: int = 8
    # 窗口无操作多久后自动收起（分钟）
    idle_autoclose_minutes: int = 10
    # 回车提交一条 / Shift+回车换行
    enter_submits: bool = True
    # “稍后提醒”的可选分钟数
    snooze_options: list[int] = field(default_factory=lambda: [15, 30, 60])
    # 常用模板，点一下直接加一条
    templates: list[str] = field(default_factory=lambda: list(DEFAULT_TEMPLATES))
    window_width: int = 430
    window_height: int = 560
    # 启动时按内容自动定高（内容多则滚动）；手动调过大小后可关掉
    auto_fit_height: bool = True
    window_x: int | None = None
    window_y: int | None = None
    keep_on_top: bool = True
    # True = 当天已有记录就完全不打扰；False = 只显示清单
    hide_when_recorded: bool = False


def load() -> Config:
    paths.ensure_dirs()
    if not paths.CONFIG_PATH.exists():
        cfg = Config()
        save(cfg)
        return cfg
    try:
        raw = json.loads(paths.CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return Config()
    if not isinstance(raw, dict):
        return Config()
    known = {f.name for f in dataclasses.fields(Config)}
    return Config(**{k: v for k, v in raw.items() if k in known})


def save(cfg: Config) -> None:
    paths.atomic_write_text(
        paths.CONFIG_PATH,
        json.dumps(dataclasses.asdict(cfg), ensure_ascii=False, indent=2) + "\n",
    )
