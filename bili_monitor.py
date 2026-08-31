#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B站开播监控器 —— 纯本地桌面应用（tkinter）。

依赖（可选，缺省时自动降级）：
- Pillow  ：背景图拉伸/模糊/磨砂、托盘图标
- pystray ：关闭窗口后最小化到系统托盘后台运行

运行：python bili_monitor.py  （或打包后的 exe）
"""

import os
import re
import sys
import json
import time
import copy
import queue
import base64
import datetime
import threading
import urllib.request
import urllib.parse
import webbrowser
import winsound
import winreg
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageTk, ImageFilter, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pystray
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
BATCH_URL = 'https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo'
SINGLE_URL = 'https://api.live.bilibili.com/room/v1/Room/get_info'
DAY_NAMES = ['', '一', '二', '三', '四', '五', '六', '日']
LIVE_LABEL = {-1: '不存在/失败', 0: '未开播', 1: '直播中', 2: '轮播中'}

ACCENT = '#fb7299'
ACCENT_DARK = '#e85b83'
BG_PANEL = '#f4f6f9'
BG_CARD = '#ffffff'
HINT_FG = '#8a94a6'

DEFAULT_CONFIG = {
    'intervalSeconds': 60,
    'notifyOnStartup': False,
    'notifyOnRound': True,
    'rooms': [],
    'schedule': {'enabled': False, 'rules': []},
    'reminder': {'repeatCount': 1, 'repeatIntervalSeconds': 300},
    'appearance': {'background': '', 'blur': 10, 'frost': 30},
    'notify': {
        'sound': True,
        'soundPath': '',
        'serverChan': {'enabled': False, 'sendKey': ''},
        'pushPlus': {'enabled': False, 'token': ''},
        'wxPusher': {'enabled': False, 'appToken': '', 'uids': []},
        'phoneCall': {'enabled': False, 'provider': 'twilio', 'accountSid': '', 'authToken': '', 'from': '', 'to': ''},
    },
}


def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(app_dir(), 'config.json')


def data_dir():
    d = os.path.join(app_dir(), 'data')
    os.makedirs(d, exist_ok=True)
    return d


# ---------- 配置 ----------

def _deep_merge(base, override):
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                _deep_merge(cfg, json.load(f))
        except Exception:
            pass
    cfg.pop('port', None)
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------- B站查询 ----------

def fetch_json(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def query_batch(room_ids):
    params = [('req_biz', 'web_room_componet')]
    for i in room_ids:
        params.append(('room_ids', str(i)))
    url = BATCH_URL + '?' + urllib.parse.urlencode(params)
    j = fetch_json(url, headers={'User-Agent': UA, 'Referer': 'https://live.bilibili.com/'})
    by = (j.get('data') or {}).get('by_room_ids') or {}
    out = []
    for info in by.values():
        out.append({
            'room_id': info.get('room_id'), 'short_id': info.get('short_id', 0),
            'uname': info.get('uname', ''), 'title': info.get('title', ''),
            'live_url': info.get('live_url', ''), 'area_name': info.get('area_name', ''),
            'live_status': info.get('live_status'),
        })
    return out


def query_each(room_ids):
    out = []
    for rid in room_ids:
        try:
            j = fetch_json(SINGLE_URL + '?room_id=' + urllib.parse.quote(str(rid)),
                           headers={'User-Agent': UA, 'Referer': 'https://live.bilibili.com/'})
            d = j.get('data') or {}
            if j.get('code') == 0 and 'live_status' in d:
                out.append({'room_id': d.get('room_id'), 'short_id': d.get('short_id', 0), 'uname': '',
                            'title': d.get('title', ''), 'live_url': 'https://live.bilibili.com/%s' % (d.get('short_id') or d.get('room_id')),
                            'area_name': d.get('area_name', ''), 'live_status': d.get('live_status')})
            else:
                out.append({'room_id': rid, 'short_id': 0, 'uname': '', 'title': '', 'live_url': '', 'area_name': '', 'live_status': -1})
        except Exception:
            out.append({'room_id': rid, 'short_id': 0, 'uname': '', 'title': '', 'live_url': '', 'area_name': '', 'live_status': -1})
    return out


def query_all_rooms(room_ids, log=None):
    try:
        return query_batch(room_ids)
    except Exception as e:
        if log:
            log('批量接口失败，回退到逐房间查询: %s' % e)
        return query_each(room_ids)


def find_info(infos, room_id):
    rid = int(room_id)
    for i in infos:
        if i.get('room_id') == rid or (i.get('short_id') and i.get('short_id') == rid):
            return i
    return None


# ---------- 时段 ----------

def hhmm_to_minutes(s):
    try:
        h, m = str(s).split(':')
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def is_within_schedule(dt, schedule):
    if not (schedule and schedule.get('enabled')):
        return True
    rules = schedule.get('rules') or []
    if not rules:
        return False
    js_day = dt.weekday()
    now_min = dt.hour * 60 + dt.minute
    for rule in rules:
        days = [((int(d) - 1) % 7) for d in (rule.get('days') or [])]
        start = hhmm_to_minutes(rule.get('start'))
        end = hhmm_to_minutes(rule.get('end'))
        if start < end:
            if js_day in days and start <= now_min < end:
                return True
        elif start > end:
            prev = (js_day - 1) % 7
            if (js_day in days and now_min >= start) or (prev in days and now_min < end):
                return True
        else:
            if js_day in days:
                return True
    return False


# ---------- 通知 ----------

def play_sound(cfg):
    n = cfg.get('notify', {})
    if n.get('sound') is False:
        return
    sp = n.get('soundPath')
    if sp and os.path.exists(sp):
        winsound.PlaySound(sp, winsound.SND_FILENAME | winsound.SND_ASYNC)
    else:
        winsound.MessageBeep()


def _post(url, data_bytes, headers):
    req = urllib.request.Request(url, data=data_bytes, headers=headers)
    urllib.request.urlopen(req, timeout=10)


def push_wechat(cfg, title, body, log):
    n = cfg.get('notify', {})
    sc = n.get('serverChan', {})
    if sc.get('enabled') and sc.get('sendKey'):
        try:
            _post('https://sctapi.ftqq.com/%s.send' % sc['sendKey'],
                  urllib.parse.urlencode({'title': title, 'desp': body}).encode(),
                  {'Content-Type': 'application/x-www-form-urlencoded'})
            log('Server酱推送成功')
        except Exception as e:
            log('Server酱推送失败: %s' % e)
    pp = n.get('pushPlus', {})
    if pp.get('enabled') and pp.get('token'):
        try:
            _post('https://www.pushplus.plus/send',
                  json.dumps({'token': pp['token'], 'title': title, 'content': body, 'template': 'txt'}).encode(),
                  {'Content-Type': 'application/json'})
            log('PushPlus推送成功')
        except Exception as e:
            log('PushPlus推送失败: %s' % e)
    wx = n.get('wxPusher', {})
    if wx.get('enabled') and wx.get('appToken') and wx.get('uids'):
        try:
            _post('https://wxpusher.zjiecode.com/api/send/message',
                  json.dumps({'appToken': wx['appToken'], 'content': body, 'summary': title, 'contentType': 1, 'uids': wx['uids']}).encode(),
                  {'Content-Type': 'application/json'})
            log('WxPusher推送成功')
        except Exception as e:
            log('WxPusher推送失败: %s' % e)


def phone_call(cfg, text, log):
    pc = cfg.get('notify', {}).get('phoneCall', {})
    if not pc.get('enabled'):
        return
    sid, tok, frm, to = pc.get('accountSid'), pc.get('authToken'), pc.get('from'), pc.get('to')
    if not (sid and tok and frm and to):
        log('电话提醒: 配置不完整，已跳过')
        return
    auth = base64.b64encode(('%s:%s' % (sid, tok)).encode()).decode()
    twiml = '<Response><Say language="zh-CN">%s</Say></Response>' % text
    try:
        _post('https://api.twilio.com/2010-04-01/Accounts/%s/Calls.json' % sid,
              urllib.parse.urlencode({'To': to, 'From': frm, 'Twiml': twiml}).encode(),
              {'Authorization': 'Basic ' + auth, 'Content-Type': 'application/x-www-form-urlencoded'})
        log('电话提醒: 已发起呼叫')
    except Exception as e:
        log('电话提醒失败: %s' % e)


def fire_notify(cfg, view, label, log):
    display = view.get('displayName', '')
    title = '【开播提醒】%s' % display
    body = '标题：%s\n分区：%s\n链接：%s' % (view.get('title') or '（无）', view.get('area_name') or '（未知）', view.get('live_url') or '（未知）')
    play_sound(cfg)
    push_wechat(cfg, title, body, log)
    phone_call(cfg, '您关注的 %s 开播了' % display, log)


# ---------- 开机自启 ----------

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_VALUE = 'BiliLiveMonitor'


def autostart_command():
    if getattr(sys, 'frozen', False):
        return '"%s"' % sys.executable
    return '"%s" "%s"' % (sys.executable, os.path.abspath(__file__))


def autostart_enabled():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
        winreg.QueryValueEx(k, RUN_VALUE)
        winreg.CloseKey(k)
        return True
    except FileNotFoundError:
        return False


def set_autostart(enable):
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    if enable:
        winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
    else:
        try:
            winreg.DeleteValue(k, RUN_VALUE)
        except FileNotFoundError:
            pass
    winreg.CloseKey(k)


# ---------- 监控引擎（后台线程） ----------

class Monitor:
    def __init__(self, config_getter, event_queue, log):
        self.config_getter = config_getter
        self.queue = event_queue
        self.log = log
        self.state = {}
        self.reminders = {}
        self.running = False
        self.stop_event = threading.Event()
        self.thread = None

    def _cfg(self):
        return self.config_getter()

    def start(self):
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.stop_event.set()
        self._cancel_all()

    def _loop(self):
        while self.running and not self.stop_event.is_set():
            t0 = time.time()
            try:
                self._poll_once()
            except Exception as e:
                self.log('检查出错: %s' % e)
            interval = max(10, int(self._cfg().get('intervalSeconds', 60)))
            while self.running and not self.stop_event.is_set() and (time.time() - t0) < interval:
                time.sleep(0.2)

    def _poll_once(self):
        cfg = self._cfg()
        if not is_within_schedule(datetime.datetime.now(), cfg.get('schedule', {})):
            self.log('当前不在启用时段内，跳过本次检查')
            return
        rooms = cfg.get('rooms') or []
        if not rooms:
            self.log('尚未添加任何房间')
            return
        infos = query_all_rooms([r.get('roomId') for r in rooms], self.log)
        parts = []
        for r in rooms:
            key = str(r.get('roomId'))
            info = find_info(infos, r.get('roomId'))
            status = info['live_status'] if info else -1
            is_round = status == 2
            is_live = status == 1 or (is_round and cfg.get('notifyOnRound') is not False)
            display = r.get('name') or (info and info.get('uname')) or ('直播间%s' % r.get('roomId'))
            prev = self.state.get(key)
            prev_live = prev['live'] if prev else None
            if status == -1:
                parts.append('❌ %s' % display)
                self.state[key] = {'live': False, 'status': -1, 'info': None, 'display': display}
                self._cancel(key)
                continue
            sym = '🔴' if status == 1 else ('🟡' if is_round else '⚪')
            parts.append('%s %s' % (sym, display))
            nxt = {'live': is_live, 'status': status, 'info': info, 'display': display}
            if prev_live is None:
                if is_live and cfg.get('notifyOnStartup'):
                    self._on_live(r, info, display, is_round, key)
            elif not prev_live and is_live:
                self._on_live(r, info, display, is_round, key)
            elif prev_live and not is_live:
                self.log('📴 %s 下播了' % display)
                self._cancel(key)
            self.state[key] = nxt
        self.log('检查 %d 个房间: %s' % (len(rooms), '  '.join(parts)))
        self.queue.put(('status', self._snapshot()))

    def _snapshot(self):
        cfg = self._cfg()
        out = []
        for r in cfg.get('rooms') or []:
            s = self.state.get(str(r.get('roomId')))
            out.append({
                'roomId': r.get('roomId'), 'name': r.get('name') or '',
                'display': (s or {}).get('display') or r.get('name') or ('直播间%s' % r.get('roomId')),
                'status': (s or {}).get('status'),
                'label': LIVE_LABEL.get((s or {}).get('status'), '未检查'),
                'title': ((s or {}).get('info') or {}).get('title') or '',
                'live_url': ((s or {}).get('info') or {}).get('live_url') or '',
            })
        return out

    def _build_view(self, r, info, display):
        return {'displayName': display, 'roomId': r.get('roomId'), 'title': (info or {}).get('title', ''),
                'live_url': (info or {}).get('live_url', ''), 'area_name': (info or {}).get('area_name', '')}

    def _on_live(self, r, info, display, is_round, key):
        label = '开始轮播' if is_round else '开播'
        view = self._build_view(r, info, display)
        self.log('===== %s: %s =====' % (label, display))
        self.queue.put(('live', {'display': display, 'label': label, 'title': view['title'], 'live_url': view['live_url'], 'area_name': view['area_name']}))
        fire_notify(self._cfg(), view, label, self.log)
        self._schedule_repeats(key, view, label)

    def _schedule_repeats(self, key, view, label):
        count = max(1, int(self._cfg().get('reminder', {}).get('repeatCount', 1)))
        if count <= 1:
            return
        gap = max(10, int(self._cfg().get('reminder', {}).get('repeatIntervalSeconds', 300)))
        self._cancel(key)
        timers = []
        for i in range(1, count):
            t = threading.Timer(gap * i, self._repeat_fire, args=(key, view, label, i + 1, count))
            t.daemon = True
            t.start()
            timers.append(t)
        self.reminders[key] = timers

    def _repeat_fire(self, key, view, label, idx, count):
        s = self.state.get(key)
        if s and s.get('live') and is_within_schedule(datetime.datetime.now(), self._cfg().get('schedule', {})):
            self.log('🔁 %s 第 %d/%d 次提醒' % (view['displayName'], idx, count))
            self.queue.put(('live', {'display': view['displayName'], 'label': '%s（第 %d/%d 次提醒）' % (label, idx, count), 'title': view['title'], 'live_url': view['live_url'], 'area_name': view['area_name']}))
            fire_notify(self._cfg(), view, '%s（第 %d/%d 次提醒）' % (label, idx, count), self.log)

    def _cancel(self, key):
        for t in self.reminders.pop(key, []):
            t.cancel()

    def _cancel_all(self):
        for key in list(self.reminders.keys()):
            self._cancel(key)


# ---------- 界面 ----------

class App:
    def __init__(self, auto_start=True):
        self.config = load_config()
        self.queue = queue.Queue()
        self._bg_pil = None
        self._bg_photo = None
        self._tray_notified = False
        self.tray_icon = None

        self.root = tk.Tk()
        self.root.title('B站开播监控器')
        self.root.geometry('900x720')
        self.root.minsize(840, 640)
        self._setup_style()

        self.status_var = tk.StringVar(value='已停止')
        self.active_var = tk.StringVar(value='—')
        self.blur_var = tk.IntVar(value=int(self.config.get('appearance', {}).get('blur', 10)))
        self.frost_var = tk.IntVar(value=int(self.config.get('appearance', {}).get('frost', 30)))

        # 背景画布（单窗口，置于内容之后，承载磨砂背景图）
        self.bg_canvas = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=BG_PANEL)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self.monitor = Monitor(lambda: self.config, self.queue, self._log)

        self._build_ui()
        self._load_widgets()
        self.root.bind('<Configure>', self._on_resize)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.after(100, self._process_queue)

        if auto_start:
            self.monitor.start()
            self._log('监控已自动启动')
            self._refresh_status()

        self._setup_tray()
        self.root.after(50, self._draw_bg)

    # ---------- 样式 ----------
    def _setup_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        font = ('Microsoft YaHei UI', 10)
        style.configure('.', font=font)
        style.configure('TFrame', background=BG_PANEL)
        style.configure('TLabel', background=BG_PANEL)
        style.configure('TCheckbutton', background=BG_PANEL)
        style.configure('TLabelframe', background=BG_PANEL)
        style.configure('TLabelframe.Label', background=BG_PANEL)
        style.configure('TNotebook', background=BG_PANEL, borderwidth=0, tabmargins=(8, 6, 8, 0))
        style.configure('TNotebook.Tab', padding=(16, 8), font=font)
        style.map('TNotebook.Tab', background=[('selected', BG_CARD)], foreground=[('selected', ACCENT_DARK)])
        style.configure('TButton', padding=(12, 6), font=font)
        style.configure('Accent.TButton', background=ACCENT, foreground='#ffffff', borderwidth=0, padding=(14, 6))
        style.map('Accent.TButton', background=[('active', ACCENT_DARK), ('disabled', '#eab8c7')])
        style.configure('Treeview', rowheight=30, font=font)
        style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 10, 'bold'))
        style.configure('TEntry', padding=4)

    # ---------- 日志 ----------
    def _log(self, line):
        self.queue.put(('log', str(line)))

    def _log_now(self, line):
        self.log_text.config(state='normal')
        self.log_text.insert('end', '[%s] %s\n' % (datetime.datetime.now().strftime('%H:%M:%S'), line))
        self.log_text.see('end')
        self.log_text.config(state='disabled')

    # ---------- UI ----------
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(side='top', fill='x')
        ttk.Label(top, text='状态').pack(side='left')
        ttk.Label(top, textvariable=self.status_var, foreground='#16a34a').pack(side='left', padx=(4, 14))
        ttk.Label(top, text='时段').pack(side='left')
        ttk.Label(top, textvariable=self.active_var).pack(side='left', padx=(4, 14))
        ttk.Button(top, text='停止', command=self._stop).pack(side='right')
        ttk.Button(top, text='启动', command=self._start).pack(side='right', padx=(0, 6))
        ttk.Button(top, text='测试通知', command=self._test_notify).pack(side='right', padx=(0, 6))
        ttk.Button(top, text='保存配置', style='Accent.TButton', command=self._save_all).pack(side='right', padx=(0, 6))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        self._build_tab_rooms()
        self._build_tab_schedule()
        self._build_tab_check()
        self._build_tab_notify()
        self._build_tab_appearance()
        self._build_tab_log()

    def _build_tab_rooms(self):
        f = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(f, text=' 监控房间 ')
        ttk.Label(f, text='添加房间号时自动识别主播名作为初始命名；房间号支持短号或长号。').grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 8))
        self.room_tree = ttk.Treeview(f, columns=('id', 'name', 'status'), show='headings', height=11)
        self.room_tree.heading('id', text='房间号')
        self.room_tree.heading('name', text='名称')
        self.room_tree.heading('status', text='状态')
        self.room_tree.column('id', width=150)
        self.room_tree.column('name', width=220)
        self.room_tree.column('status', width=140)
        self.room_tree.grid(row=1, column=0, columnspan=3, sticky='nsew')
        self.room_id_var = tk.StringVar()
        self.room_name_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.room_id_var).grid(row=2, column=0, sticky='ew', pady=(10, 0))
        ttk.Entry(f, textvariable=self.room_name_var).grid(row=2, column=1, sticky='ew', padx=8, pady=(10, 0))
        btns = ttk.Frame(f)
        btns.grid(row=2, column=2, sticky='e', pady=(10, 0))
        ttk.Button(btns, text='添加房间', style='Accent.TButton', command=self._add_room).pack(side='left', padx=(0, 8))
        ttk.Button(btns, text='删除选中', command=self._del_room).pack(side='left')
        f.columnconfigure(1, weight=1)
        f.rowconfigure(1, weight=1)

    def _build_tab_schedule(self):
        f = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(f, text=' 监视时段 ')
        self.schedule_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(f, text='启用每周时段限制（时段外不请求、不提醒）', variable=self.schedule_enabled_var).grid(row=0, column=0, columnspan=2, sticky='w')
        self.rule_tree = ttk.Treeview(f, columns=('days', 'start', 'end'), show='headings', height=11)
        self.rule_tree.heading('days', text='星期')
        self.rule_tree.heading('start', text='开始')
        self.rule_tree.heading('end', text='结束')
        self.rule_tree.column('days', width=200)
        self.rule_tree.column('start', width=100)
        self.rule_tree.column('end', width=100)
        self.rule_tree.grid(row=1, column=0, columnspan=2, sticky='nsew', pady=(8, 10))
        btns = ttk.Frame(f)
        btns.grid(row=2, column=0, columnspan=2, sticky='w')
        ttk.Button(btns, text='＋ 添加时段', style='Accent.TButton', command=self._add_rule).pack(side='left', padx=(0, 8))
        ttk.Button(btns, text='删除选中', command=self._del_rule).pack(side='left')
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)

    def _build_tab_check(self):
        f = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(f, text=' 检查与提醒 ')
        self.interval_var = tk.StringVar()
        self.repeat_count_var = tk.StringVar()
        self.repeat_interval_var = tk.StringVar()
        self.notify_startup_var = tk.BooleanVar()
        self.notify_round_var = tk.BooleanVar()
        g = ttk.Frame(f)
        g.pack(fill='x')
        ttk.Label(g, text='检查间隔（秒）').grid(row=0, column=0, sticky='w', padx=(0, 6))
        ttk.Entry(g, textvariable=self.interval_var, width=8).grid(row=0, column=1, sticky='w', padx=(0, 26))
        ttk.Label(g, text='重复提醒次数（含首次）').grid(row=0, column=2, sticky='w', padx=(0, 6))
        ttk.Entry(g, textvariable=self.repeat_count_var, width=8).grid(row=0, column=3, sticky='w', padx=(0, 26))
        ttk.Label(g, text='重复提醒间隔（秒）').grid(row=0, column=4, sticky='w', padx=(0, 6))
        ttk.Entry(g, textvariable=self.repeat_interval_var, width=8).grid(row=0, column=5, sticky='w')
        ttk.Label(f, text='重复提醒仅在主播仍开播且处于启用时段内时继续；下播自动停止。').pack(anchor='w', pady=(12, 10))
        ttk.Checkbutton(f, text='启动时若已在播也提醒一次', variable=self.notify_startup_var).pack(anchor='w', pady=2)
        ttk.Checkbutton(f, text='轮播（状态2）也当作开播提醒', variable=self.notify_round_var).pack(anchor='w', pady=2)

    def _build_tab_notify(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=' 提醒方式 ')
        # 可滚动容器：内容可能超过窗口高度
        self.notify_canvas = tk.Canvas(tab, highlightthickness=0, bd=0, bg=BG_PANEL)
        self.notify_vsb = ttk.Scrollbar(tab, orient='vertical', command=self.notify_canvas.yview)
        self.notify_canvas.configure(yscrollcommand=self.notify_vsb.set)
        self.notify_vsb.pack(side='right', fill='y')
        self.notify_canvas.pack(side='left', fill='both', expand=True)
        f = ttk.Frame(self.notify_canvas, padding=12)
        self._notify_win = self.notify_canvas.create_window((0, 0), window=f, anchor='nw')
        f.bind('<Configure>', lambda e: self.notify_canvas.configure(scrollregion=self.notify_canvas.bbox('all')))
        self.notify_canvas.bind('<Configure>', lambda e: self.notify_canvas.itemconfigure(self._notify_win, width=e.width))

        self.sound_var = tk.BooleanVar()
        self.sound_path_var = tk.StringVar()
        self.sc_enabled_var = tk.BooleanVar(); self.sc_key_var = tk.StringVar()
        self.pp_enabled_var = tk.BooleanVar(); self.pp_token_var = tk.StringVar()
        self.wx_enabled_var = tk.BooleanVar(); self.wx_token_var = tk.StringVar(); self.wx_uids_var = tk.StringVar()
        self.pc_enabled_var = tk.BooleanVar(); self.pc_sid_var = tk.StringVar(); self.pc_auth_var = tk.StringVar()
        self.pc_from_var = tk.StringVar(); self.pc_to_var = tk.StringVar()

        ttk.Label(f, text='开播时本应用会弹出置顶提醒窗口；离开电脑请配置微信推送。').pack(anchor='w', pady=(0, 10))
        ttk.Checkbutton(f, text='提示音', variable=self.sound_var).pack(anchor='w')
        row = ttk.Frame(f); row.pack(fill='x', pady=(0, 12))
        ttk.Label(row, text='自定义提示音(.wav)').pack(side='left')
        ttk.Entry(row, textvariable=self.sound_path_var).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(row, text='浏览', command=self._browse_sound).pack(side='left')

        ttk.Separator(f, orient='horizontal').pack(fill='x', pady=8)
        ttk.Label(f, text='微信推送', font=('Microsoft YaHei UI', 10, 'bold')).pack(anchor='w')

        self._push_row(f, 'Server酱（方糖）', self.sc_enabled_var, 'SendKey', self.sc_key_var,
                       '粘贴 sct.ftqq.com 的 SendKey：用微信扫码登录 https://sct.ftqq.com 后，页面「SendKey」一栏以 SCT 开头的那串密钥。')
        self._push_row(f, 'PushPlus', self.pp_enabled_var, 'token', self.pp_token_var,
                       '粘贴 pushplus.plus 的 token：登录 https://www.pushplus.plus 后，「一对一推送」页面显示的 32 位字符串。')
        self._push_row(f, 'WxPusher', self.wx_enabled_var, 'appToken', self.wx_token_var,
                       '粘贴 appToken：登录 https://wxpusher.zjiecode.com 后台，在「应用管理」里创建或打开应用后复制其 appToken。')
        r = ttk.Frame(f); r.pack(fill='x', pady=(2, 0))
        ttk.Label(r, text='接收者 uid', width=16, anchor='w').pack(side='left')
        ttk.Entry(r, textvariable=self.wx_uids_var).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Label(f, text='填写要接收提醒的 UID，多个用英文逗号分隔：微信关注该应用后，在 WxPusher 后台「用户管理」或微信端「我的信息」里查看 UID。',
                  foreground=HINT_FG, wraplength=760, justify='left').pack(anchor='w', pady=(2, 10))

        ttk.Separator(f, orient='horizontal').pack(fill='x', pady=8)
        ttk.Label(f, text='电话提醒（Twilio 付费，可选）', font=('Microsoft YaHei UI', 10, 'bold')).pack(anchor='w')
        ttk.Checkbutton(f, text='启用电话提醒', variable=self.pc_enabled_var).pack(anchor='w', pady=(0, 4))
        self._field_row(f, 'Account SID', self.pc_sid_var,
                        '粘贴 Twilio 控制台首页的 Account SID，以 AC 开头，地址 https://console.twilio.com。')
        self._field_row(f, 'Auth Token', self.pc_auth_var,
                        '粘贴 Twilio 控制台的 Auth Token（与 Account SID 同页，点「显示」后复制）。')
        self._field_row(f, '主叫号码 From', self.pc_from_var,
                        '粘贴 Twilio 分配给你的号码，E.164 格式（带 + 号和国家码），例如 +12345678901。')
        self._field_row(f, '接收手机号 To', self.pc_to_var,
                        '粘贴要接收提醒电话的手机号，E.164 格式，例如 +8613800138000。')
        self._bind_mousewheel(self.notify_canvas, f)

    def _bind_mousewheel(self, canvas, widget):
        def _scroll(event):
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        canvas.bind('<MouseWheel>', _scroll)
        widget.bind('<MouseWheel>', _scroll)
        for child in widget.winfo_children():
            self._bind_mousewheel(canvas, child)

    def _push_row(self, parent, title, enabled_var, label, var, hint):
        r = ttk.Frame(parent); r.pack(fill='x', pady=(6, 0))
        ttk.Checkbutton(r, text=title, variable=enabled_var).pack(side='left')
        r2 = ttk.Frame(parent); r2.pack(fill='x', pady=(2, 0))
        ttk.Label(r2, text=label, width=16, anchor='w').pack(side='left')
        ttk.Entry(r2, textvariable=var).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Label(parent, text=hint, foreground=HINT_FG, wraplength=760, justify='left').pack(anchor='w', pady=(2, 8))

    def _field_row(self, parent, label, var, hint):
        r = ttk.Frame(parent); r.pack(fill='x', pady=(2, 0))
        ttk.Label(r, text=label, width=16, anchor='w').pack(side='left')
        ttk.Entry(r, textvariable=var).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Label(parent, text=hint, foreground=HINT_FG, wraplength=760, justify='left').pack(anchor='w', pady=(2, 8))

    def _build_tab_appearance(self):
        f = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(f, text=' 外观与设置 ')
        self.autostart_var = tk.BooleanVar()
        self.bg_info_var = tk.StringVar(value='未设置背景图')

        # 开机自启放最顶部，保证始终可见
        ttk.Checkbutton(f, text='开机自启动（登录 Windows 时自动运行本程序）', variable=self.autostart_var, command=self._toggle_autostart).pack(anchor='w', pady=(0, 8))
        ttk.Separator(f, orient='horizontal').pack(fill='x', pady=8)

        ttk.Label(f, text='背景图', font=('Microsoft YaHei UI', 10, 'bold')).pack(anchor='w')
        ttk.Label(f, textvariable=self.bg_info_var).pack(anchor='w', pady=(3, 8))
        r = ttk.Frame(f); r.pack(fill='x', pady=(0, 4))
        ttk.Button(r, text='选择背景图片…', style='Accent.TButton', command=self._choose_bg).pack(side='left', padx=(0, 8))
        ttk.Button(r, text='清除背景', command=self._clear_bg).pack(side='left')

        ttk.Separator(f, orient='horizontal').pack(fill='x', pady=12)
        ttk.Label(f, text='背景模糊：%d' % self.blur_var.get()).pack(anchor='w')
        self.blur_label = ttk.Label(f)
        self.blur_label.pack(anchor='w')
        self.blur_scale = ttk.Scale(f, from_=0, to=30, variable=self.blur_var, command=self._on_blur_change)
        self.blur_scale.pack(fill='x', pady=(2, 10))

        ttk.Label(f, text='磨砂程度：%d%%' % self.frost_var.get()).pack(anchor='w')
        self.frost_label = ttk.Label(f)
        self.frost_label.pack(anchor='w')
        self.frost_scale = ttk.Scale(f, from_=0, to=100, variable=self.frost_var, command=self._on_frost_change)
        self.frost_scale.pack(fill='x', pady=(2, 4))
        ttk.Label(f, text='数值越大，背景图越白越朦胧（磨砂）。', foreground='#888').pack(anchor='w')

    def _build_tab_log(self):
        f = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(f, text=' 日志 ')
        self.log_text = tk.Text(f, height=20, bg='#141a26', fg='#d7dce5', insertbackground='#fff',
                                font=('Consolas', 9), relief='flat', padx=10, pady=8)
        self.log_text.pack(fill='both', expand=True)
        self.log_text.config(state='disabled')

    # ---------- 背景 ----------
    def _on_resize(self, event):
        if event.widget is self.root:
            if hasattr(self, '_resize_job'):
                self.root.after_cancel(self._resize_job)
            self._resize_job = self.root.after(220, self._draw_bg)

    def _on_blur_change(self, _v):
        self.blur_label.config(text='背景模糊：%d' % self.blur_var.get())
        self.config['appearance']['blur'] = self.blur_var.get()
        self._draw_bg()

    def _on_frost_change(self, _v):
        self.frost_label.config(text='磨砂程度：%d%%' % self.frost_var.get())
        self.config['appearance']['frost'] = self.frost_var.get()
        self._draw_bg()

    def _draw_bg(self):
        if not hasattr(self, 'bg_canvas'):
            return
        w = max(1, self.root.winfo_width())
        h = max(1, self.root.winfo_height())
        self.bg_canvas.delete('bg')
        fname = self.config.get('appearance', {}).get('background') or ''
        path = os.path.join(data_dir(), fname) if fname else None
        if not (path and os.path.exists(path)) or not HAS_PIL:
            self.bg_canvas.config(bg=BG_PANEL)
            return
        try:
            if self._bg_pil is None:
                self._bg_pil = Image.open(path).convert('RGB')
            img = self._bg_pil.resize((w, h), Image.LANCZOS)
            blur = self.blur_var.get()
            if blur > 0:
                img = img.filter(ImageFilter.GaussianBlur(blur))
            frost = self.frost_var.get()
            if frost > 0:
                white = Image.new('RGB', img.size, (255, 255, 255))
                img = Image.blend(img, white, frost / 100.0)
            self._bg_photo = ImageTk.PhotoImage(img)
            self.bg_canvas.create_image(0, 0, image=self._bg_photo, anchor='nw', tags='bg')
        except Exception as e:
            self.bg_canvas.config(bg=BG_PANEL)
            self._log('背景加载失败: %s' % e)

    def _refresh_bg_info(self):
        bg = self.config.get('appearance', {}).get('background') or ''
        self.bg_info_var.set('已设置：%s' % bg if bg else '未设置背景图')

    def _choose_bg(self):
        ft = [('图片', '*.png *.gif *.jpg *.jpeg *.bmp'), ('所有文件', '*.*')]
        path = filedialog.askopenfilename(parent=self.root, title='选择背景图片', filetypes=ft)
        if not path:
            return
        if not HAS_PIL and os.path.splitext(path)[1].lower() not in ('.png', '.gif'):
            messagebox.showwarning('提示', '未安装 Pillow，仅支持 PNG/GIF', parent=self.root)
            return
        ext = os.path.splitext(path)[1].lower() or '.png'
        fname = 'background' + ext
        try:
            with open(path, 'rb') as src, open(os.path.join(data_dir(), fname), 'wb') as dst:
                dst.write(src.read())
        except Exception as e:
            messagebox.showerror('错误', '保存背景失败: %s' % e, parent=self.root)
            return
        old = self.config.get('appearance', {}).get('background') or ''
        if old and old != fname:
            try:
                os.remove(os.path.join(data_dir(), old))
            except Exception:
                pass
        self.config['appearance']['background'] = fname
        self._bg_pil = None
        save_config(self.config)
        self._draw_bg()
        self._refresh_bg_info()

    def _clear_bg(self):
        old = self.config.get('appearance', {}).get('background') or ''
        if old:
            try:
                os.remove(os.path.join(data_dir(), old))
            except Exception:
                pass
        self.config['appearance']['background'] = ''
        self._bg_pil = None
        save_config(self.config)
        self._draw_bg()
        self._refresh_bg_info()

    # ---------- 数据加载/保存 ----------
    def _load_widgets(self):
        c = self.config
        self.interval_var.set(str(c.get('intervalSeconds', 60)))
        self.repeat_count_var.set(str(c.get('reminder', {}).get('repeatCount', 1)))
        self.repeat_interval_var.set(str(c.get('reminder', {}).get('repeatIntervalSeconds', 300)))
        self.notify_startup_var.set(bool(c.get('notifyOnStartup')))
        self.notify_round_var.set(c.get('notifyOnRound') is not False)
        self.schedule_enabled_var.set(bool(c.get('schedule', {}).get('enabled')))
        n = c.get('notify', {})
        self.sound_var.set(n.get('sound') is not False)
        self.sound_path_var.set(n.get('soundPath') or '')
        self.sc_enabled_var.set(bool(n.get('serverChan', {}).get('enabled')))
        self.sc_key_var.set(n.get('serverChan', {}).get('sendKey') or '')
        self.pp_enabled_var.set(bool(n.get('pushPlus', {}).get('enabled')))
        self.pp_token_var.set(n.get('pushPlus', {}).get('token') or '')
        self.wx_enabled_var.set(bool(n.get('wxPusher', {}).get('enabled')))
        self.wx_token_var.set(n.get('wxPusher', {}).get('appToken') or '')
        self.wx_uids_var.set(','.join(n.get('wxPusher', {}).get('uids') or []))
        pc = n.get('phoneCall', {})
        self.pc_enabled_var.set(bool(pc.get('enabled')))
        self.pc_sid_var.set(pc.get('accountSid') or '')
        self.pc_auth_var.set(pc.get('authToken') or '')
        self.pc_from_var.set(pc.get('from') or '')
        self.pc_to_var.set(pc.get('to') or '')
        try:
            self.autostart_var.set(autostart_enabled())
        except Exception:
            pass
        self._refresh_rooms()
        self._refresh_rules()
        self._refresh_bg_info()

    def _read_widgets(self):
        c = self.config
        c['intervalSeconds'] = self._int(self.interval_var.get(), 60, 10, 86400)
        c['notifyOnStartup'] = self.notify_startup_var.get()
        c['notifyOnRound'] = self.notify_round_var.get()
        c['reminder']['repeatCount'] = self._int(self.repeat_count_var.get(), 1, 1, 100)
        c['reminder']['repeatIntervalSeconds'] = self._int(self.repeat_interval_var.get(), 300, 10, 86400)
        c['schedule']['enabled'] = self.schedule_enabled_var.get()
        c['appearance']['blur'] = self.blur_var.get()
        c['appearance']['frost'] = self.frost_var.get()
        n = c['notify']
        n['sound'] = self.sound_var.get()
        n['soundPath'] = self.sound_path_var.get().strip()
        n['serverChan']['enabled'] = self.sc_enabled_var.get()
        n['serverChan']['sendKey'] = self.sc_key_var.get().strip()
        n['pushPlus']['enabled'] = self.pp_enabled_var.get()
        n['pushPlus']['token'] = self.pp_token_var.get().strip()
        n['wxPusher']['enabled'] = self.wx_enabled_var.get()
        n['wxPusher']['appToken'] = self.wx_token_var.get().strip()
        n['wxPusher']['uids'] = [x.strip() for x in self.wx_uids_var.get().split(',') if x.strip()]
        pc = n['phoneCall']
        pc['enabled'] = self.pc_enabled_var.get()
        pc['accountSid'] = self.pc_sid_var.get().strip()
        pc['authToken'] = self.pc_auth_var.get().strip()
        pc['from'] = self.pc_from_var.get().strip()
        pc['to'] = self.pc_to_var.get().strip()

    @staticmethod
    def _int(s, default, lo, hi):
        try:
            v = int(str(s))
        except Exception:
            return default
        return max(lo, min(hi, v))

    def _save_all(self):
        self._read_widgets()
        save_config(self.config)
        self._log('配置已保存')

    # ---------- 房间 ----------
    def _refresh_rooms(self):
        self.room_tree.delete(*self.room_tree.get_children())
        for r in self.config.get('rooms') or []:
            self.room_tree.insert('', 'end', iid=str(r.get('roomId')), values=(r.get('roomId'), r.get('name') or '', ''))

    def _add_room(self):
        rid = self.room_id_var.get().strip()
        name = self.room_name_var.get().strip()
        if not rid:
            messagebox.showwarning('提示', '请填写房间号', parent=self.root)
            return
        if any(str(r.get('roomId')) == rid for r in self.config.get('rooms') or []):
            messagebox.showwarning('提示', '该房间已存在', parent=self.root)
            return
        if name:
            self._insert_room(rid, name)
        else:
            self._log('正在识别主播名…')
            threading.Thread(target=self._resolve_and_add, args=(rid,), daemon=True).start()

    def _resolve_and_add(self, rid):
        try:
            infos = query_all_rooms([rid], self._log)
            info = find_info(infos, rid)
            name = (info or {}).get('uname') or ''
        except Exception:
            name = ''
        self.queue.put(('resolved', (rid, name)))

    def _insert_room(self, rid, name):
        self.config.setdefault('rooms', []).append({'roomId': rid, 'name': name})
        save_config(self.config)
        self._refresh_rooms()
        self.room_id_var.set('')
        self.room_name_var.set('')
        self._log('已添加房间 %s%s' % (rid, ('（%s）' % name) if name else ''))

    def _del_room(self):
        sel = self.room_tree.selection()
        if not sel:
            messagebox.showwarning('提示', '请先选中要删除的房间', parent=self.root)
            return
        rid = sel[0]
        self.config['rooms'] = [r for r in self.config.get('rooms') or [] if str(r.get('roomId')) != rid]
        save_config(self.config)
        self._refresh_rooms()
        self._log('已移除房间 %s' % rid)

    # ---------- 时段 ----------
    def _refresh_rules(self):
        self.rule_tree.delete(*self.rule_tree.get_children())
        for i, r in enumerate(self.config.get('schedule', {}).get('rules') or []):
            days = ''.join(DAY_NAMES[d] for d in (r.get('days') or []) if 1 <= d <= 7)
            self.rule_tree.insert('', 'end', iid=str(i), values=(days, r.get('start'), r.get('end')))

    def _add_rule(self):
        dlg = tk.Toplevel(self.root)
        dlg.title('添加时段')
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.configure(bg=BG_PANEL)
        dlg.geometry('+%d+%d' % (self.root.winfo_rootx() + 70, self.root.winfo_rooty() + 90))
        ttk.Label(dlg, text='选择星期：').grid(row=0, column=0, sticky='w', padx=10, pady=(10, 4))
        day_vars = {}
        box = ttk.Frame(dlg)
        box.grid(row=1, column=0, columnspan=2, sticky='w', padx=10)
        for i in range(1, 8):
            day_vars[i] = tk.BooleanVar(value=True)
            ttk.Checkbutton(box, text=DAY_NAMES[i], variable=day_vars[i]).pack(side='left', padx=4)
        start_var = tk.StringVar(value='19:00')
        end_var = tk.StringVar(value='23:00')
        ttk.Label(dlg, text='开始 (HH:MM)').grid(row=2, column=0, sticky='w', padx=10, pady=(10, 2))
        ttk.Entry(dlg, textvariable=start_var, width=12).grid(row=3, column=0, sticky='w', padx=10)
        ttk.Label(dlg, text='结束 (HH:MM)').grid(row=2, column=1, sticky='w', padx=10, pady=(10, 2))
        ttk.Entry(dlg, textvariable=end_var, width=12).grid(row=3, column=1, sticky='w', padx=10)

        def ok():
            days = [i for i in range(1, 8) if day_vars[i].get()]
            if not days or not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', start_var.get()) or not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', end_var.get()):
                messagebox.showwarning('提示', '请填写正确的星期与时间(HH:MM)', parent=dlg)
                return
            self.config['schedule']['rules'].append({'days': days, 'start': start_var.get(), 'end': end_var.get()})
            save_config(self.config)
            self._refresh_rules()
            dlg.destroy()

        row = ttk.Frame(dlg)
        row.grid(row=4, column=0, columnspan=2, pady=12)
        ttk.Button(row, text='确定', style='Accent.TButton', command=ok).pack(side='left', padx=(0, 8))
        ttk.Button(row, text='取消', command=dlg.destroy).pack(side='left')

    def _del_rule(self):
        sel = self.rule_tree.selection()
        if not sel:
            messagebox.showwarning('提示', '请先选中要删除的时段', parent=self.root)
            return
        idx = int(sel[0])
        rules = self.config.get('schedule', {}).get('rules') or []
        if 0 <= idx < len(rules):
            rules.pop(idx)
            save_config(self.config)
            self._refresh_rules()

    # ---------- 其它 ----------
    def _browse_sound(self):
        path = filedialog.askopenfilename(parent=self.root, title='选择提示音', filetypes=[('WAV 音频', '*.wav')])
        if path:
            self.sound_path_var.set(path)

    def _start(self):
        self.monitor.start()
        self._log('监控已启动')
        self._refresh_status()

    def _stop(self):
        self.monitor.stop()
        self._log('监控已停止')
        self._refresh_status()

    def _refresh_status(self):
        self.status_var.set('运行中' if self.monitor.running else '已停止')
        self.active_var.set('时段内' if is_within_schedule(datetime.datetime.now(), self.config.get('schedule', {})) else '时段外')

    def _toggle_autostart(self):
        try:
            set_autostart(self.autostart_var.get())
            self._log('已%s开机自启' % ('开启' if self.autostart_var.get() else '关闭'))
        except Exception as e:
            self.autostart_var.set(not self.autostart_var.get())
            messagebox.showerror('错误', '设置开机自启失败: %s' % e, parent=self.root)

    def _test_notify(self):
        view = {'displayName': '测试主播', 'title': '这是一条测试通知', 'live_url': 'https://live.bilibili.com/', 'area_name': '测试分区'}
        fire_notify(self.config, view, '测试', self._log)
        self._show_popup({'display': '测试主播', 'label': '测试', 'title': '这是一条测试通知', 'live_url': 'https://live.bilibili.com/', 'area_name': '测试分区'})
        self._log('测试通知已触发')

    def _show_popup(self, ev):
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes('-topmost', True)
        top.config(bg=ACCENT)
        sw = self.root.winfo_screenwidth()
        w = 380
        x = sw - w - 20
        y = 20
        top.geometry('%dx170+%d+%d' % (w, x, y))

        outer = tk.Frame(top, bg=ACCENT, padx=3, pady=3)
        outer.pack(fill='both', expand=True)
        inner = tk.Frame(outer, bg=BG_CARD)
        inner.pack(fill='both', expand=True)

        tk.Label(inner, text='🎉 %s：%s' % (ev.get('label', '开播提醒'), ev.get('display', '')), bg=BG_CARD, fg=ACCENT_DARK,
                 font=('Microsoft YaHei UI', 13, 'bold'), anchor='w').pack(fill='x', padx=16, pady=(14, 2))
        tk.Label(inner, text=ev.get('title', ''), bg=BG_CARD, fg='#333', font=('Microsoft YaHei UI', 10), anchor='w', wraplength=340).pack(fill='x', padx=16)
        row = tk.Frame(inner, bg=BG_CARD)
        row.pack(anchor='w', padx=16, pady=(10, 0))
        if ev.get('live_url'):
            b = tk.Button(row, text='打开直播间', bg=ACCENT, fg='#ffffff', relief='flat', padx=14, pady=4,
                          activebackground=ACCENT_DARK, activeforeground='#fff', font=('Microsoft YaHei UI', 10),
                          command=lambda: webbrowser.open(ev['live_url']))
            b.pack(side='left', padx=(0, 10))
        b2 = tk.Button(row, text='关闭', bg='#e8ebf0', fg='#333', relief='flat', padx=14, pady=4,
                       font=('Microsoft YaHei UI', 10), command=top.destroy)
        b2.pack(side='left')
        top.lift()
        try:
            top.focus_force()
        except Exception:
            pass
        top.after(20000, top.destroy)

    def _process_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == 'log':
                    self._log_now(item[1])
                elif kind == 'live':
                    self._show_popup(item[1])
                    self._log_now('🎉 %s: %s' % (item[1].get('label'), item[1].get('display')))
                elif kind == 'status':
                    self._apply_snapshot(item[1])
                elif kind == 'resolved':
                    rid, name = item[1]
                    self._insert_room(rid, name)
                    self._log('已添加房间 %s%s' % (rid, ('，自动识别主播名：%s' % name) if name else '（未识别到主播名）'))
        except queue.Empty:
            pass
        self._refresh_status()
        self.root.after(100, self._process_queue)

    def _apply_snapshot(self, snap):
        status_map = {s['roomId']: s for s in snap}
        for item in self.room_tree.get_children():
            s = status_map.get(item)
            if s is not None:
                self.room_tree.set(item, 'status', s.get('label', ''))
                self.room_tree.set(item, 'name', s.get('display') or s.get('name') or '')

    # ---------- 托盘 ----------
    @staticmethod
    def _make_tray_image():
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((6, 6, 58, 58), fill=ACCENT)
        d.polygon([(26, 20), (26, 44), (44, 32)], fill='#ffffff')
        return img

    def _setup_tray(self):
        if not (HAS_TRAY and HAS_PIL):
            return
        menu = pystray.Menu(
            pystray.MenuItem('显示主界面', self._tray_show, default=True),
            pystray.MenuItem('退出', self._tray_quit),
        )
        self.tray_icon = pystray.Icon('bili_live_monitor', self._make_tray_image(), 'B站开播监控器', menu)
        try:
            self.tray_icon.run_detached()
        except Exception:
            self.tray_icon = None

    def _tray_show(self, icon, item):
        self.root.after(0, self._show)

    def _tray_quit(self, icon, item):
        self.root.after(0, self._really_quit)

    def _show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(250, lambda: self.root.attributes('-topmost', False))

    def _on_close(self):
        if self.tray_icon is not None:
            self.root.withdraw()
            if not self._tray_notified:
                self._tray_notified = True
                try:
                    self.tray_icon.notify('程序仍在后台运行，点击托盘图标可恢复或退出。', 'B站开播监控器')
                except Exception:
                    pass
        else:
            self._really_quit()

    def _really_quit(self):
        self.monitor.stop()
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    App(auto_start=True).run()


if __name__ == '__main__':
    main()
