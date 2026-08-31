# 发布到 GitHub 的步骤

> 说明：当前开发沙箱**无法直接访问 GitHub**（无 git、无外网到 github.com），因此已把仓库文件、截图、说明文档、发布包全部准备好；最后一步"推送并创建 Release"需要你在自己的电脑上执行（约 3 分钟）。

## 已准备好的内容

| 文件 | 用途 |
|---|---|
| `bili_monitor.py` | 主程序源码 |
| `README.md` | 应用介绍（含 6 张截图 + 详细使用说明） |
| `docs\images\*.png` | 界面截图 |
| `LICENSE` | MIT 开源协议 |
| `.gitignore` | 排除构建产物与个人配置 |
| `config.example.json` | 配置示例 |
| `_fetch_deps.py` / `build.ps1` | 下载依赖 / 重新打包脚本 |
| `installer.iss` / `build-installer.ps1` | Inno Setup 安装脚本 / 一键生成 Setup.exe |
| `assets\app.ico` | 应用图标 |
| `release\BiliLiveMonitor.exe` | 单文件可执行程序（约 20MB，免 Python） |
| `BiliLiveMonitor-v1.0.0.zip` | 便携压缩包（exe + 默认 config） |
| `installer\BiliLiveMonitor-Setup-v1.0.0.exe` | Windows 安装包（需在本机运行 build-installer.ps1 生成） |

---

## 方式一：命令行一键发布（推荐）

需要先安装两个工具并登录 GitHub：

1. 安装 **git**：https://git-scm.com
2. 安装 **GitHub CLI**：https://cli.github.com ，然后执行 `gh auth login` 登录。

然后在本文件夹打开 PowerShell，运行：

```powershell
.\publish.ps1 -RepoName BiliLiveMonitor -Visibility public -Version v1.0.0
```

脚本会自动：初始化 git 仓库 → 提交 → 在 GitHub 创建公开仓库 → 推送 → 创建 Release 并上传 `BiliLiveMonitor.exe` 和 `BiliLiveMonitor-v1.0.0.zip`。

---

## 方式二：GitHub 网页手动发布（无需命令行工具）

### A. 上传代码与说明

1. 登录 [github.com](https://github.com) → 右上角 **+** → **New repository**。
2. 仓库名填 `BiliLiveMonitor`，选择 **Public**，勾选初始化 README（可选）。
3. 进入仓库 → **Add file** → **Upload files**，把本文件夹里这些文件拖进去上传：
   - `bili_monitor.py`
   - `README.md`
   - `LICENSE`
   - `.gitignore`
   - `config.example.json`
   - `_fetch_deps.py`
   - `build.ps1`
   - `docs\` 整个文件夹（含截图）
4. 点 **Commit changes**。

> 说明：`libs\`、`data\`、`config.json`、`release\`、`*.exe`、`*.zip` 等构建产物与个人配置**不要上传**（已写在 `.gitignore` 里）。

### B. 上传可执行程序（Release）

1. 进入仓库 → 右侧 **Releases** → **Create a new release**。
2. **Tag version** 填 `v1.0.0`，标题写 `BiliLiveMonitor v1.0.0`。
3. 在 **Attach binaries** 里上传这些文件（安装包需先在本机运行 `.\build-installer.ps1` 生成）：
   - `release\BiliLiveMonitor.exe`
   - `BiliLiveMonitor-v1.0.0.zip`
   - `installer\BiliLiveMonitor-Setup-v1.0.0.exe`
4. 点 **Publish release**。

完成后，别人就可以在仓库的 Releases 页面下载 exe / 安装包直接使用了。

---

## 常见问题

- **别人下载后打不开 / 报毒？** 单文件 exe 由 PyInstaller 打包，偶发杀软误报，添加信任即可；README 已注明。
- **想更新版本？** 改代码后运行 `.\build.ps1` 重新打包、`.\build-installer.ps1` 重新生成安装包，再按上面步骤发布新的 Release（版本号递增）。
- **想在 README 里替换截图？** 直接替换 `docs\images\` 下的同名 PNG 即可。
