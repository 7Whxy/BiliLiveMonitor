; ============================================================
; BiliLiveMonitor (B站开播监控器) — Inno Setup 安装脚本
; 用法：安装 Inno Setup 6 后，运行 build-installer.ps1（或直接 iscc installer.iss）
; ============================================================

#define MyAppName "B站开播监控器"
#define MyAppNameEn "BiliLiveMonitor"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "BiliLiveMonitor"
#define MyAppExeName "BiliLiveMonitor.exe"

[Setup]
; 固定的 AppId，保证升级时覆盖安装
AppId={{F6A2B9C1-3D4E-4F5A-8B6C-7D8E9F0A1B2C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; 发布后填 GitHub 地址（去掉下面两行行首分号即可）
;AppPublisherURL=https://github.com/你的用户名/BiliLiveMonitor
;AppSupportURL=https://github.com/你的用户名/BiliLiveMonitor
DefaultDirName={userpf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 按用户安装，无需管理员权限；安装到当前用户可写目录（程序会在旁边写 config.json 与 data\）
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename={#MyAppNameEn}-Setup-v{#MyAppVersion}
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Files]
Source: "release\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
