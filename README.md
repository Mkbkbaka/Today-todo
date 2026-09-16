# 今日待办

登录 Windows 后自动弹出一个小窗口问一句"今天要完成什么"，把答案按天存成 JSON，
第二天继续用。纯本地、不联网、不需要管理员权限、不依赖第三方库。

## 功能一览

- **深蓝立体界面**：整窗深蓝配色，标题栏一并染色；按钮带厚度边与高光，按下会真的"陷下去"。
- **登录后自动询问**：在系统"启动"文件夹放一个快捷方式，登录后延迟 8 秒弹出。
- **一天只主动打断一次**：当天已经问过就不再强弹录入窗口，只会显示清单。
- **回车即添加**：多行粘贴会自动拆成多条；`Shift+回车`换行；`双击条目`可改名。
- **昨日未完成可继承**：窗口顶部列出之前没做完的事项，勾选或一键"全部带入今天"。
- **优先级排序**：点待办左侧的圆标，**按点击先后**排定优先级，清单自动重排；
  圆标与左侧色条按优先级变色（红 → 橙 → 黄 → 绿 → 蓝 → 紫），再点一次取消并自动续号。
- **稍后提醒**：15/30/60 分钟后自动弹回来；也可以"今天不再提醒"或"今天先跳过"。
- **关窗前先问一句**：点右上角 ✕ 会弹出两个选项 —— **后台运行** 还是 **退出程序**，
  不用再去菜单里找退出。
- **窗口大小跟着内容走**：清单多长，窗口就多高，超过上限才出现滚动条。
- **跨天自动处理**：窗口开着过午夜会提示把未完成项带到新的一天。
- **Markdown 归档**：自动把当月待办汇总到 `data/md/YYYY-MM.md`，方便回顾与备份。

## 日常使用

| 想做的事 | 怎么做 |
| --- | --- |
| 添加待办 | 在输入框里打字，回车 |
| 一次加多条 | 粘贴多行文本，回车 |
| 改一条文字 | 双击那条 |
| 标记完成 | 点前面的复选框 |
| 设优先级 | 点待办左侧的圆标：第一个点的排第 1 位（红），依次往下；再点一次取消 |
| 删除 | 点右边的 ✕ |
| 收起窗口（继续后台运行） | 按 Esc，或在点 ✕ 后选"后台运行" |
| 彻底退出程序 | 点 ✕ 后选"退出程序" |
| 重新唤出 | 再双击一次启动方式（桌面/开始菜单/自启动快捷方式） |

## 管理开机自启

```powershell
# 安装（创建一个“启动”文件夹里的快捷方式，无需管理员）
D:\Learning\Anaconda3\python.exe app\main.py --install-autostart

# 移除
D:\Learning\Anaconda3\python.exe app\main.py --uninstall-autostart

# 查看当前状态（数据文件、今日条目数、自启是否装好）
D:\Learning\Anaconda3\python.exe app\main.py --status

# 立刻运行（不等待，用于调试）
D:\Learning\Anaconda3\python.exe app\main.py

# 自检：在临时目录里跑一遍数据层与界面层，不动正式数据
D:\Learning\Anaconda3\python.exe tools\selftest.py
```

也可以直接用 `tools\install_autostart.ps1` 和 `tools\uninstall_autostart.ps1`。
装好后可以在「任务管理器 → 启动应用」里看到"今日待办"，在那里也能临时禁用。

## 配置

配置文件在 `data/config.json`，首次运行会自动生成。改完保存，下次启动生效。

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `delay_seconds` | 8 | 登录后延迟多少秒弹窗，等桌面和输入法就绪 |
| `idle_autoclose_minutes` | 10 | 窗口无操作多久自动收起（不会丢内容） |
| `enter_submits` | true | 回车提交一条；改成 false 则只用 Ctrl+回车提交 |
| `snooze_options` | [15, 30, 60] | "稍后提醒"菜单里的分钟选项 |
| `templates` | ["晨会","写日报","运动"] | 输入框下方的常用按钮，点一下直接加一条 |
| `keep_on_top` | true | 弹出后置顶 1 分钟再放开 |
| `auto_fit_height` | true | 按内容自动定窗口高度；想固定高度就改成 false 再手动拖 |
| `hide_when_recorded` | false | 改成 true：当天已有记录时启动后完全不显示窗口 |
| `window_width/height/x/y` | 自动 | 窗口尺寸与位置，关闭时自动记住 |

## 数据与备份

```
data/
├─ config.json                 配置
├─ plans/2026-09-16.json       每天一份，人类可读，可直接手改（含 priority 字段）
├─ md/2026-09.md               当月归档
└─ plans/*.json.bad-*          万一文件损坏，原文件会被改名隔离在这里
logs/app.log                   运行日志（1MB 轮转，保留 5 份，不含待办正文）
```

- 整个 `data/` 目录复制走就是完整备份；想用 git 管理就删掉 `.gitignore` 里的 `data/`。
- 写入是"临时文件 + 原子替换"，断电或强杀进程不会留下半个损坏文件。
- 想换数据位置：设环境变量 `TODAYTODO_DATA` 指向别的目录即可（调试用）。

## 常见问题

**想把"一天只问一次"改成每次都问？**
每次启动都会显示清单；需要重新进入录入模式，删掉当天 JSON 里的 `asked_at` 字段即可。

**重装 Python 或换了 Anaconda 路径后不启动了？**
重新跑一次 `--install-autostart`。另外 `app/host/autostart.py` 会自动定位 `pythonw.exe`，
只要 `python` 在 PATH 里就能装对。

**想让启动更快、彻底摆脱 Anaconda？**
用 PyInstaller 打包成单个 exe：`pip install pyinstaller` 然后
`pyinstaller -F -w -n 今日待办 app/main.py`，再把自启动目标指向生成的 exe。

**输入法回车会不会被误当成提交？**
Win11 微软拼音下，选词回车不会传到窗口；如果遇到异常，把配置里的 `enter_submits`
改成 `false`，就只认 Ctrl+回车。

## 代码结构

```
app/
├─ main.py                入口：参数、日志、DPI、单实例、装配窗口
├─ paths.py               路径与原子写
├─ config.py              配置读写
├─ ui/theme.py            深蓝配色、立体按钮、立体复选框、深色标题栏
├─ core/
│  ├─ model.py            TodoItem / Plan 数据结构
│  ├─ store.py            按天 JSON 读写、损坏隔离、Markdown 归档
│  ├─ carryover.py        未完成项顺延与去重
│  └─ schedule.py         日期与提醒时间
├─ ui/todo_window.py      单窗口双模式界面 + 关闭确认弹窗
└─ host/
   ├─ singleinstance.py   命名互斥体 + 唤出信号
   └─ autostart.py        开机自启的安装/卸载/状态
tools/
├─ selftest.py            自检
├─ install_autostart.ps1
└─ uninstall_autostart.ps1
```
