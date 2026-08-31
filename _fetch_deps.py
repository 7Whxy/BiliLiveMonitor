import urllib.request
import zipfile
import io
import json
import os

TARGET = 'libs'
WHEELS = {
    'pillow': '12.3.0',
    'pystray': '0.19.5',
    'six': '1.17.0',
    'pyinstaller': '6.22.2',
    'pyinstaller-hooks-contrib': '2026.7',
    'altgraph': '0.17.5',
    'packaging': '26.3',
    'pefile': '2024.8.26',
    'pywin32-ctypes': '0.2.3',
    'setuptools': '84.0.0',
}


def best_wheel(urls):
    def score(u):
        fn = u['filename']
        if 'cp314' in fn and 'win_amd64' in fn:
            return 0
        if 'py3-none-any' in fn:
            return 1
        if 'py2.py3-none-any' in fn:
            return 2
        if 'win_amd64' in fn and 'py3-none' in fn:
            return 3
        return 9
    return sorted(urls, key=score)[0]


os.makedirs(TARGET, exist_ok=True)
for name, ver in WHEELS.items():
    try:
        info = json.load(urllib.request.urlopen('https://pypi.org/pypi/%s/%s/json' % (name, ver), timeout=60))
        u = best_wheel(info['urls'])
        print('fetch', name, '->', u['filename'])
        data = urllib.request.urlopen(u['url'], timeout=180).read()
        z = zipfile.ZipFile(io.BytesIO(data))
        z.extractall(TARGET)
        print('   extracted', len(z.namelist()), 'files')
    except Exception as e:
        print('FAIL', name, repr(e))

print('--- 检查 ---')
for name in ['PIL', 'pystray', 'PyInstaller', 'six', 'altgraph']:
    p = os.path.join(TARGET, name)
    n = len(os.listdir(p)) if os.path.isdir(p) else 0
    print('%s: isdir=%s files=%d' % (name, os.path.isdir(p), n))
