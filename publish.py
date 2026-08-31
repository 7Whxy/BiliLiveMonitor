#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 GitHub API 发布：创建仓库、上传源码、创建 Release、上传资产。

用法（token 优先从环境变量 GH_TOKEN 或本地 gh_token.txt 读取）：
    python publish.py [仓库名] [public|private]
"""
import os
import sys
import json
import base64
import urllib.request
import urllib.error

GITHUB_API = 'https://api.github.com'
UPLOAD_API = 'https://uploads.github.com'
VERSION = 'v1.0.0'
DESCRIPTION = 'B站开播监控器：完全本地化、免安装、低占用的 Windows 桌面开播提醒工具'

# 要上传到仓库的文件（相对路径，用 / 分隔）
REPO_FILES = [
    'bili_monitor.py',
    'README.md',
    'LICENSE',
    '.gitignore',
    'config.example.json',
    '_fetch_deps.py',
    'build.ps1',
    'build-installer.ps1',
    'installer.iss',
    'publish.ps1',
    'publish.py',
    'PUBLISH.md',
    'assets/app.ico',
    'docs/images/1-rooms.png',
    'docs/images/2-schedule.png',
    'docs/images/3-check.png',
    'docs/images/4-notify.png',
    'docs/images/5-appearance.png',
    'docs/images/6-log.png',
]

# Release 资产（二进制）
RELEASE_ASSETS = [
    'release/BiliLiveMonitor.exe',
    'BiliLiveMonitor-v1.0.0.zip',
]


def api(token, method, url, data=None):
    req = urllib.request.Request(url, method=method)
    req.add_header('Authorization', 'token ' + token)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'BiliLiveMonitor-Publisher')
    if data is not None:
        body = json.dumps(data).encode()
        req.data = body
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors='replace')


def upload_asset(token, url, name, data):
    req = urllib.request.Request(url + '?name=' + urllib.parse.quote(name), method='POST', data=data)
    req.add_header('Authorization', 'token ' + token)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('Content-Type', 'application/octet-stream')
    req.add_header('User-Agent', 'BiliLiveMonitor-Publisher')
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, 'ok'
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors='replace')[:300]


def main():
    token = os.environ.get('GH_TOKEN') or ''
    if not token and os.path.exists('gh_token.txt'):
        with open('gh_token.txt', encoding='utf-8') as f:
            token = f.read().strip()
    if not token:
        print('缺少 GitHub token：请设置环境变量 GH_TOKEN，或写入本地 gh_token.txt')
        sys.exit(1)

    repo = sys.argv[1] if len(sys.argv) > 1 else 'BiliLiveMonitor'
    visibility = sys.argv[2] if len(sys.argv) > 2 else 'public'

    # 1. 校验 token，取用户名
    st, me = api(token, 'GET', GITHUB_API + '/user')
    if st != 200:
        print('token 无效（%s）：%s' % (st, me))
        sys.exit(1)
    owner = me['login']
    print('账号：%s' % owner)

    # 2. 创建仓库
    st, r = api(token, 'POST', GITHUB_API + '/user/repos', {
        'name': repo,
        'private': visibility == 'private',
        'description': DESCRIPTION,
        'has_issues': True,
        'has_wiki': False,
    })
    print('仓库 %s：%s' % (repo, '已创建' if st == 201 else ('已存在' if st == 422 else '失败 %s %s' % (st, r))))
    if st not in (201, 422):
        sys.exit(1)

    # 3. 上传源码与文档
    ok = fail = 0
    for f in REPO_FILES:
        if not os.path.exists(f):
            print('  跳过缺失：%s' % f)
            continue
        with open(f, 'rb') as fh:
            content = base64.b64encode(fh.read()).decode()
        path = f.replace('\\', '/')
        st, r = api(token, 'PUT', '%s/repos/%s/%s/contents/%s' % (GITHUB_API, owner, repo, path),
                    {'message': 'add ' + path, 'content': content})
        if st in (200, 201):
            ok += 1
            print('  上传 %s' % path)
        else:
            fail += 1
            print('  失败 %s（%s）%s' % (path, st, (r or '')[:120]))
    print('文件：成功 %d，失败 %d' % (ok, fail))

    # 4. 创建 Release
    st, rel = api(token, 'POST', '%s/repos/%s/%s/releases' % (GITHUB_API, owner, repo), {
        'tag_name': VERSION,
        'name': 'BiliLiveMonitor ' + VERSION,
        'body': '完整介绍见仓库 README.md。\n\n- BiliLiveMonitor.exe：单文件，免 Python\n- BiliLiveMonitor-v1.0.0.zip：便携压缩包',
        'draft': False,
        'prerelease': False,
    })
    if st != 201:
        print('创建 Release 失败（%s）：%s' % (st, rel))
        sys.exit(1)
    rel_id = rel['id']
    print('Release：%s（id=%s）' % (VERSION, rel_id))

    # 5. 上传资产
    for asset in RELEASE_ASSETS:
        if not os.path.exists(asset):
            print('  跳过缺失资产：%s' % asset)
            continue
        name = os.path.basename(asset)
        with open(asset, 'rb') as fh:
            data = fh.read()
        url = '%s/repos/%s/%s/releases/%s/assets' % (UPLOAD_API, owner, repo, rel_id)
        st, msg = upload_asset(token, url, name, data)
        print('  资产 %s：%s' % (name, '成功' if st in (200, 201) else '失败 %s %s' % (st, msg)))

    print('完成：https://github.com/%s/%s' % (owner, repo))


if __name__ == '__main__':
    import urllib.parse
    main()
