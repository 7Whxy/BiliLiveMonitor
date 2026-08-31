# 一键生成 Windows 安装包（需要 Inno Setup 6）
# 用法：.\build-installer.ps1   （首次会自动尝试安装 Inno Setup）
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# 1. 定位 Inno Setup 编译器 ISCC.exe
$candidates = @(
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe',
    'C:\Program Files (x86)\Inno Setup 5\ISCC.exe'
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

# 2. 若未安装，尝试自动安装
if (-not $iscc) {
    Write-Host '未找到 Inno Setup，尝试安装...' -ForegroundColor Yellow
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install innosetup -y --no-progress
    } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements
    } else {
        throw '未找到 choco / winget。请手动安装 Inno Setup 6：https://jrsoftware.org/isinfo.php'
    }
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) {
        throw 'Inno Setup 安装后仍未找到 ISCC.exe，请手动运行 ISCC 编译 installer.iss'
    }
}

# 3. 确认 exe 已打包
if (-not (Test-Path "$here\release\BiliLiveMonitor.exe")) {
    throw '缺少 release\BiliLiveMonitor.exe，请先运行 .\build.ps1 打包'
}

# 4. 编译安装包
Write-Host "使用 $iscc 编译 installer.iss ..." -ForegroundColor Cyan
& $iscc "$here\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC 编译失败，退出码 $LASTEXITCODE" }

Write-Host "完成：$here\installer\BiliLiveMonitor-Setup-v1.0.0.exe" -ForegroundColor Green
