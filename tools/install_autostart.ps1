# 在“启动”文件夹里创建指向 pythonw.exe 的快捷方式，实现登录后自动运行。
# 不需要管理员权限；想停用就运行 uninstall_autostart.ps1 或在任务管理器里禁用。

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent $PSScriptRoot
$Script   = Join-Path $Root 'app\main.py'
$Startup  = [Environment]::GetFolderPath('Startup')
$LnkPath  = Join-Path $Startup '今日待办.lnk'

if (-not (Test-Path $Script)) {
    throw "找不到入口脚本：$Script"
}

$Pythonw = Join-Path (Split-Path -Parent (Get-Command python -ErrorAction SilentlyContinue).Source) 'pythonw.exe'
if (-not (Test-Path $Pythonw)) {
    # 回退：直接问 Python 自己
    $Pythonw = (python -c "import sys,pathlib;print(pathlib.Path(sys.executable).with_name('pythonw.exe'))").Trim()
}
if (-not (Test-Path $Pythonw)) {
    throw "找不到 pythonw.exe，请确认 Python 安装正确"
}

$Shell = New-Object -ComObject WScript.Shell
$Lnk = $Shell.CreateShortcut($LnkPath)
$Lnk.TargetPath       = $Pythonw
$Lnk.Arguments        = '"' + $Script + '" --autostart'
$Lnk.WorkingDirectory = $Root
$Lnk.WindowStyle      = 7
$Lnk.Description      = '登录后询问今日待办'
$Lnk.Save()

Write-Host "已创建：$LnkPath"
Write-Host "目标  ：$Pythonw"
Write-Host "参数  ：`"$Script`" --autostart"
Write-Host ""
Write-Host "验证：任务管理器 → 启动应用 里应能看到“今日待办”。"
