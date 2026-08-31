# SignPath 免费代码签名 · 申请与接入指南

> 目标：让 `BiliLiveMonitor.exe` 拥有**受信任的数字签名**，彻底消除 Windows「无法验证发布者 / 智能应用控制」拦截。
> SignPath Foundation 为**开源项目**提供免费的 Authenticode 代码签名（证书链公开受信任）。

---

## 一、申请（约 1–2 周）

1. 发邮件到 **oss-support@signpath.org**，正文写明：
   - 项目名称：BiliLiveMonitor（B站开播监控器）
   - 仓库链接：https://github.com/7Whxy/BiliLiveMonitor
   - 一句话简介：完全本地化、免安装的 Windows 桌面开播提醒工具（纯 Python/tkinter）。
2. 对方会回复一个 **Excel 申请表**，按要求填写。
   - 重点是「**Reputation（声誉）**」部分：提供能证明项目真实/可信的材料，例如 GitHub star/下载数、README 说明、使用截图等。
3. 审核通过后，会收到注册确认邮件（可能延迟几小时才能登录），登录地址 https://app.signpath.io 。

---

## 二、在 SignPath 后台配置

登录 https://app.signpath.io 后：

1. **记录 ID**：
   - 组织页上的 **Organization ID**（一串 UUID）。
   - 项目页上的 **Project slug**（默认即项目名）。
2. **创建 CI 用户并生成 API token**：
   - Users and Groups → 选择/创建 `CI builds` 用户 → 生成 token。
   - 复制 token，到 GitHub 仓库 **Settings → Secrets and variables → Actions** 新增 secret：`SIGNPATH_API_TOKEN`。
3. **添加 Artifact Configuration**：
   - 项目页 → Artifact Configurations → Add，名称填 `exe-zip`。
   - Artifact configuration 选择 **Zip archive + sign nested files**，粘贴下面的 XML：

```xml
<?xml version="1.0" encoding="utf-8" ?>
<artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
  <zip-file>
    <pe-file-set>
      <include path="*.exe" />
      <for-each>
        <authenticode-sign />
      </for-each>
    </pe-file-set>
  </zip-file>
</artifact-configuration>
```

4. **在 GitHub 仓库设置 Variables**（Settings → Secrets and variables → Actions → Variables）：
   - `SIGNPATH_ORG_ID` = 你的 Organization ID
   - `SIGNPATH_PROJECT_SLUG` = 你的 Project slug
   - `SIGNPATH_ARTIFACT_CONFIG` = `exe-zip`
   - `SIGNPATH_SIGNING_POLICY` = `test-signing`（先用测试证书）

---

## 三、先用测试证书跑通

1. GitHub 仓库 → **Actions** → 左侧 **build-and-sign** → **Run workflow**。
2. 测试证书是自签名的（不可信），仅用于验证流程是否打通。
3. 跑通后，SignPath 后台的 Signing Requests 里应能看到 `Completed` 的请求。

---

## 四、激活正式（受信任）证书

1. 测试流程跑通后，回复 SignPath 支持邮件，说明「已用测试证书跑通 CI，请激活 release 证书」。
2. 通过内部审计后，你会在 SignPath 后台看到 **release-signing** 证书可用（约数天到一周）。
3. 把 GitHub 的 `SIGNPATH_SIGNING_POLICY` 变量改为 **`release-signing`**。
4. 重新触发 workflow：release 证书的每次签名需要**手动批准**——构建会在 Signing 步骤等待，去 SignPath 后台的 Signing Requests 里对该请求点 **Approve**，构建才会继续。

---

## 五、发布带签名的 Release

- 推一个 `v*` 标签（例如 `v1.0.1`）即可自动：构建 → 签名 → 生成便携 zip → 创建 Release 并上传 `BiliLiveMonitor.exe` 与 `BiliLiveMonitor-v1.0.1.zip`。
- 也可在 Actions 页手动触发。

---

## 六、必须履行的署名要求

SignPath 要求项目页/README 上注明：

> Free code signing provided by SignPath.io, certificate by SignPath Foundation

（本仓库 README 已加入该声明。）

---

## 参考

- 官方文档：https://about.signpath.io/documentation/getting-started
- 开源项目免费签名介绍：https://about.signpath.io/product/open-source
- 使用的 GitHub Action：https://github.com/SignPath/github-action-submit-signing-request
