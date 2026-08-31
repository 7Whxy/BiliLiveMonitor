# 从源码重新打包单文件 exe
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$env:PYTHONPATH = "$here\libs"
if (-not (Test-Path "$here\libs\PyInstaller")) {
    Write-Host "缺少 libs 依赖，正在下载..." -ForegroundColor Yellow
    python _fetch_deps.py
}

python -m PyInstaller --noconfirm --clean --onefile --windowed --name BiliLiveMonitor `
    --paths "$here\libs" --collect-submodules pystray --hidden-import pystray._win32 bili_monitor.py

Write-Host "完成：$here\dist\BiliLiveMonitor.exe" -ForegroundColor Green
