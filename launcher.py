"""Windows one-click launcher. Importing this module never starts QQ."""
import json
import logging
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import urllib.parse
import urllib.request
import webbrowser

from runtime_support import InstanceLock, data_dir, is_our_server

ROOT = Path(__file__).resolve().parent


def discover_napcat(root=ROOT):
    for parent in ('NapCatQQ', 'NapCatQQ_OneKey'):
        for path in sorted((Path(root) / parent).glob('NapCat*.Shell')):
            if (path / 'NapCatWinBootMain.exe').is_file() and (path / 'napcat.mjs').is_file():
                return path
    return None


def create_server(app, port):
    from werkzeug.serving import make_server
    try:
        return make_server('127.0.0.1', port, app, threaded=True)
    except (OSError, SystemExit) as exc:
        raise RuntimeError(f'端口 {port} 被占用，或本机禁止监听。请关闭占用程序，或修改启动器端口。') from exc


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.3):
            return True
    except OSError:
        return False


def is_napcat_webui(port):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/webui/', timeout=1) as response:
            return b'<title>NapCat WebUI</title>' in response.read(16384)
    except (OSError, ValueError):
        return False


def is_onebot(port, token=''):
    import websocket
    ws = None
    try:
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        ws = websocket.create_connection(f'ws://127.0.0.1:{port}', timeout=1, header=headers,
                                         http_no_proxy=['127.0.0.1'])
        ws.send(json.dumps({'action': 'get_version_info', 'echo': 'launcher-probe'}))
        for _ in range(3):
            value = json.loads(ws.recv())
            if isinstance(value, dict) and value.get('echo') == 'launcher-probe':
                return value.get('status') == 'ok' and bool(value.get('data', {}).get('app_name'))
    except Exception:
        return False
    finally:
        if ws:
            ws.close()
    return False


class Launcher:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.server = None
        self.module = None
        self.job = None
        self.log_handle = None
        self.ready = False
        self.closing = False
        self.settings_file = data_dir() / 'launcher.json'
        self.settings = {}
        try:
            self.settings = json.loads(self.settings_file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        if not isinstance(self.settings, dict):
            self.settings = {}
        configured = self.settings.get('napcat_path')
        self.napcat = Path(configured) if isinstance(configured, str) else ROOT
        if not (self.napcat / 'napcat.mjs').is_file():
            self.napcat = discover_napcat() or ROOT
        try:
            self.port = int(self.settings.get('port', 5000))
            if not 1024 <= self.port <= 65535:
                self.port = 5000
        except (TypeError, ValueError):
            self.port = 5000
        self.url = f'http://127.0.0.1:{self.port}'
        root.title('QQ群消息监控 · 统一启动器')
        root.geometry('690x480')
        root.minsize(620, 460)
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='QQ群消息监控', font=('Microsoft YaHei UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='启动服务后自动打开面板；首次使用需完成 QQ 登录。').pack(anchor='w', pady=(6, 16))
        self.status = tk.StringVar(value='正在准备…')
        ttk.Label(frame, textvariable=self.status, wraplength=630).pack(anchor='w', pady=6)
        self.monitor_status = tk.StringVar(value='监控状态：等待后台启动')
        ttk.Label(frame, textvariable=self.monitor_status, wraplength=630).pack(anchor='w', pady=6)
        self.detail = tk.StringVar(value=str(self.napcat))
        ttk.Label(frame, textvariable=self.detail, wraplength=630, foreground='#666666').pack(anchor='w', pady=6)
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=14)
        self.open_button = ttk.Button(buttons, text='打开管理面板', command=lambda: webbrowser.open(self.url), state='disabled')
        self.open_button.pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='QQ 登录 / NapCat', command=self.open_napcat).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='查看日志', command=self.open_logs).pack(side='left')
        options = ttk.Frame(frame)
        options.pack(fill='x', pady=4)
        self.path_button = ttk.Button(options, text='选择 NapCat 目录', command=self.choose_path)
        self.path_button.pack(side='left', padx=(0, 8))
        ttk.Label(options, text='Web 端口').pack(side='left')
        self.port_value = tk.StringVar(value=str(self.port))
        self.port_entry = ttk.Entry(options, textvariable=self.port_value, width=7)
        self.port_entry.pack(side='left', padx=6)
        self.retry_button = ttk.Button(options, text='保存并重试', command=self.retry)
        self.retry_button.pack(side='left')
        loader_row = ttk.Frame(frame)
        loader_row.pack(fill='x', pady=6)
        ttk.Label(loader_row, text='NapCat 加载方式').pack(side='left', padx=(0, 8))
        self.loader_mode = self.settings.get('napcat_loader', 'native')
        self.loader_choice = tk.StringVar(value='旧版加载' if self.loader_mode == 'legacy' else '原生加载')
        self.loader_combo = ttk.Combobox(loader_row, textvariable=self.loader_choice,
                                        values=('原生加载', '旧版加载'), state='readonly', width=14)
        self.loader_combo.pack(side='left')
        ttk.Label(frame, text='关闭浏览器不会停止监控。\n“退出全部”仅关闭本启动器启动的服务及 NapCat；外部已有进程保留。',
                  wraplength=630).pack(anchor='w', pady=(15, 8))
        ttk.Button(frame, text='退出全部', command=self.close).pack(anchor='e')
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        root.after(200, self.start)

    def save_settings(self):
        self.settings.update(napcat_path=str(self.napcat), port=self.port, napcat_loader=self.loader_mode)
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.settings_file.with_suffix('.tmp')
        temp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.settings_file)

    def choose_path(self):
        path = filedialog.askdirectory(title='选择包含 napcat.mjs 和 NapCatWinBootMain.exe 的目录')
        if path:
            self.napcat = Path(path)
            self.detail.set(path)

    def retry(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            port = int(self.port_value.get())
            if not 1024 <= port <= 65535:
                raise ValueError()
            if self.ready and port != self.port:
                messagebox.showinfo('修改端口', '后台已启动。请先退出，再重新打开启动器修改端口。')
                return
            self.port = port
            self.url = f'http://127.0.0.1:{port}'
            mode = 'legacy' if self.loader_choice.get() == '旧版加载' else 'native'
            if self.job is not None and mode != self.loader_mode and self.job.active():
                messagebox.showinfo('切换加载方式', '请先退出全部，再重新启动；避免同时加载两套 NapCat。')
                return
            self.loader_mode = mode
            self.save_settings()
        except (ValueError, OSError) as exc:
            messagebox.showerror('配置未保存', '端口须为 1024–65535，且配置目录必须可写。\n' + str(exc))
            return
        self.start()

    def start(self):
        self.loader_combo.configure(state='disabled')
        for widget in (self.retry_button, self.path_button, self.port_entry):
            widget.configure(state='disabled')
        self.worker = threading.Thread(target=self.boot, daemon=True)
        self.worker.start()

    def boot(self):
        try:
            self.events.put(('status', '检查 Python 依赖…'))
            import flask, bcrypt, websocket  # noqa: F401
            if self.stop_event.is_set():
                return
            if not self.ready:
                if is_our_server(self.url):
                    self.events.put(('status', '已复用现有后台；关闭本窗口不会终止该后台。'))
                else:
                    import app as module
                    self.module = module
                    self.server = create_server(module.app, self.port)
                    threading.Thread(target=self.server.serve_forever, daemon=True).start()
                    for _ in range(30):
                        if is_our_server(self.url):
                            break
                        if self.stop_event.wait(0.2):
                            return
                    else:
                        raise RuntimeError('后台启动超时，请查看日志。')
                self.ready = True
                self.events.put(('ready', self.url))
            if self.stop_event.is_set():
                return
            # Reuse external NapCat when either its configured WebUI or OneBot
            # is listening; never terminate or replace an existing QQ process.
            if self.existing_napcat():
                self.events.put(('status', '已识别并复用 NapCat / OneBot 服务。请在面板确认连接，必要时打开 QQ 登录。'))
                return
            if self.job is not None:
                if self.job.active():
                    self.events.put(('status', 'NapCat 进程仍在运行，请查看日志或打开 QQ 登录。'))
                    return
                self.job.close()
                self.job = None
                if self.log_handle:
                    self.log_handle.close()
                    self.log_handle = None
            executable = self.napcat / 'NapCatWinBootMain.exe'
            if not executable.is_file() or not (self.napcat / 'napcat.mjs').is_file():
                raise RuntimeError('未找到完整 NapCat Shell。请选择包含 napcat.mjs 和 NapCatWinBootMain.exe 的目录，然后重试。')
            from windows_job import ProcessJob
            from napcat_boot import prepare_napcat, prepare_native_napcat
            if getattr(self, 'loader_mode', 'native') == 'native':
                command, environment = prepare_native_napcat(self.napcat)
            else:
                command, environment = prepare_napcat(self.napcat, data_dir() / 'napcat-runtime')
            logs = ROOT / 'logs'
            logs.mkdir(parents=True, exist_ok=True)
            self.log_handle = (logs / 'napcat-launcher.log').open('ab', buffering=0)
            header = '\n\n=== 启动诊断 ' + time.strftime('%Y-%m-%d %H:%M:%S') + ' ===\n'
            header += '目录: ' + str(self.napcat) + '\n参数: ' + json.dumps(command, ensure_ascii=False) + '\n'
            self.log_handle.write(header.encode('utf-8'))
            job = None
            try:
                job = ProcessJob()
                job.start(command, executable=environment['NAPCAT_LAUNCHER_PATH'], cwd=str(self.napcat), env=environment,
                          stdout=self.log_handle, stderr=self.log_handle,
                          stdin=subprocess.DEVNULL)
                self.job = job
            except Exception:
                if job:
                    job.close()
                self.log_handle.close()
                self.log_handle = None
                raise
            self.events.put(('status', 'NapCat 已启动，等待 QQ 登录。首次使用请点击“QQ 登录 / NapCat”。'))
            # A short, cancellable wait; never block GUI while the user scans.
            for _ in range(40):
                if self.stop_event.wait(0.5):
                    return
                if not self.job.active():
                    raise RuntimeError('NapCat 进程已退出，请查看日志、检查 QQ 安装，然后点击“保存并重试”。')
                if is_napcat_webui(self.webui_port()):
                    self.events.put(('status', 'NapCat 登录页已就绪。请点击“QQ 登录 / NapCat”，完成后在管理面板自动连接。'))
                    return
            self.events.put(('status', 'NapCat 登录页尚未就绪，请查看 napcat-launcher.log；后台面板仍可使用。'))
        except ImportError as exc:
            self.events.put(('status', f'缺少依赖：{exc.name}。请双击“初始化环境.bat”完成安装，再重新启动。'))
        except Exception as exc:
            logging.exception('启动失败')
            self.events.put(('status', str(exc)))
        finally:
            self.events.put(('idle', None))

    def webui_config(self):
        try:
            return json.loads((self.napcat / 'config' / 'webui.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def webui_port(self):
        return int(self.webui_config().get('port', 6099))

    def existing_napcat(self):
        web_port = self.webui_port()
        occupied = []
        if port_open(web_port):
            if is_napcat_webui(web_port):
                return True
            occupied.append(web_port)
        endpoints = {3001: ''}
        for path in (self.napcat / 'config').glob('onebot11_*.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                for server in data.get('network', {}).get('webSocketServers', []):
                    if server.get('enable'):
                        endpoints[int(server['port'])] = server.get('token', '')
            except (OSError, ValueError, KeyError, TypeError):
                continue
        for port, token in endpoints.items():
            if port_open(port):
                if is_onebot(port, token):
                    return True
                occupied.append(port)
        if occupied:
            raise RuntimeError(f'端口 {occupied} 已占用，但无法确认是 NapCat / OneBot。请检查占用程序和鉴权配置后重试。')
        return False

    def open_napcat(self):
        config = self.webui_config()
        port = int(config.get('port', 6099))
        if not is_napcat_webui(port):
            messagebox.showinfo('QQ 登录', 'NapCat 登录页尚未启动。请稍候；若持续无响应，请查看日志。')
            return
        token = config.get('token', '')
        url = f'http://127.0.0.1:{port}/webui'
        if token:
            url += '?' + urllib.parse.urlencode({'token': token})
        webbrowser.open(url)

    def open_logs(self):
        path = ROOT / 'logs'
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def poll(self):
        if self.closing:
            return
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'ready':
                self.open_button.configure(state='normal')
                webbrowser.open(value)
            elif kind == 'status':
                self.status.set(value)
            elif kind == 'idle':
                self.loader_combo.configure(state='readonly')
                for widget in (self.retry_button, self.path_button, self.port_entry):
                    widget.configure(state='normal')
        if self.module:
            with self.module.monitor_lock:
                states = [m.get_status() for m in self.module.monitors.values() if m.running]
            if any(s['connected'] and s['online'] for s in states):
                text = 'QQ 已在线 · 正在监控'
            elif any(s['connected'] for s in states):
                text = 'OneBot 已连接 · 等待 QQ 在线状态'
            elif states:
                text = '正在连接 NapCat · 请确认 QQ 已登录、WebSocket 已启用'
            else:
                text = '请登录管理面板；开启自动监控后会自动连接'
            self.monitor_status.set(text)
        elif self.ready:
            self.monitor_status.set('正在复用外部后台，监控状态请查看管理面板')
        self.root.after(500, self.poll)

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.stop_event.set()
        self.status.set('正在关闭本启动器管理的服务…')
        def cleanup():
            if self.worker:
                self.worker.join()
            if self.module:
                with self.module.monitor_lock:
                    monitors = list(self.module.monitors.values())
                for monitor in monitors:
                    monitor.stop()
            if self.server:
                self.server.shutdown()
                self.server.server_close()
            if self.job:
                self.job.close()
            if self.log_handle:
                self.log_handle.close()
            self.events.put(('closed', None))
        threading.Thread(target=cleanup, daemon=True).start()
        def wait_closed():
            try:
                while True:
                    kind, _ = self.events.get_nowait()
                    if kind == 'closed':
                        self.root.destroy()
                        return
            except queue.Empty:
                self.root.after(100, wait_closed)
        wait_closed()


def main():
    root = tk.Tk()
    root.withdraw()
    lock = InstanceLock()
    if not lock.acquire():
        try:
            config = json.loads((data_dir() / 'launcher.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            config = {}
        url = f"http://127.0.0.1:{config.get('port', 5000)}"
        if is_our_server(url):
            webbrowser.open(url)
        else:
            messagebox.showinfo('已在运行', '启动器已在运行，请查看原启动窗口。')
        root.destroy()
        return
    try:
        from utils import setup_logging
        setup_logging('launcher')
        Launcher(root)
        root.deiconify()
        root.mainloop()
    except Exception as exc:
        logging.exception('启动器异常')
        messagebox.showerror('无法启动', str(exc))
    finally:
        lock.close()


if __name__ == '__main__':
    main()
