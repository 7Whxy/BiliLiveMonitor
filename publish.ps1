# 一键发布到 GitHub（需在本机已安装 git 与 GitHub CLI 并登录）
# 依赖：git（https://git-scm.com）  gh（https://cli.github.com，先执行 gh auth login）
param(
    [string]$RepoName = 'BiliLiveMonitor',
    [ValidateSet('public', 'private')][string]$Visibility = 'public',
    [string]$Version = 'v1.0.0'
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw '未找到 git，请先安装 https://git-scm.com' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw '未找到 gh，请先安装 https://cli.github.com 并执行 gh auth login' }

# 1. 初始化并提交
if (-not (Test-Path '.git')) { git init }
git add -A
git commit -m "BiliLiveMonitor 初版" --allow-empty

# 2. 创建/关联远程仓库并推送
$owner = (gh api user --jq .login).Trim()
gh repo view "$owner/$RepoName" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    gh repo create $RepoName --$Visibility --source . --push
} else {
    git remote remove origin 2>$null
    git remote add origin "https://github.com/$owner/$RepoName.git"
    git push -u origin HEAD
}

# 3. 创建 Release 并上传可执行文件与压缩包
gh release create $Version "release\BiliLiveMonitor.exe" "BiliLiveMonitor-$Version.zip" `
    --title "BiliLiveMonitor $Version" `
    --notes "见仓库 README.md" `
    --repo "$owner/$RepoName"

Write-Host "发布完成：https://github.com/$owner/$RepoName/releases" -ForegroundColor Green
