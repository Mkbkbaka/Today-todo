# 删除“启动”文件夹里的快捷方式，彻底停用开机自启。数据目录不受影响。

$ErrorActionPreference = 'Stop'

$Startup = [Environment]::GetFolderPath('Startup')
$LnkPath = Join-Path $Startup '今日待办.lnk'

if (Test-Path $LnkPath) {
    Remove-Item -LiteralPath $LnkPath -Force
    Write-Host "已删除：$LnkPath"
} else {
    Write-Host "没有找到开机自启快捷方式，无需处理。"
}
