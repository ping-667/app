"""Small, standard-library-only helpers shared by the web app and launcher."""
import json
import os
from pathlib import Path
import secrets
import urllib.request


def data_dir():
    return Path(os.environ.get('APPDATA', str(Path.home()))) / 'QQMonitor'


def load_secret(directory=None):
    configured = os.environ.get('QQ_MONITOR_SECRET')
    if configured:
        return configured
    directory = Path(directory) if directory is not None else data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'session.key'
    try:
        with path.open('x', encoding='ascii') as out:
            out.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    value = path.read_text(encoding='ascii').strip()
    if len(value) < 48:
        raise ValueError('session.key 无效，请恢复备份或删除该文件后重新启动。')
    return value


class InstanceLock:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else data_dir()
        self.file = None

    def acquire(self):
        import msvcrt
        self.directory.mkdir(parents=True, exist_ok=True)
        handle = (self.directory / 'launcher.lock').open('a+b')
        if handle.seek(0, 2) == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return False
        self.file = handle
        return True

    def close(self):
        if self.file is not None:
            import msvcrt
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            self.file.close()
            self.file = None


def is_our_server(url):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + '/api/health', timeout=1) as response:
            return json.load(response).get('service') == 'qqmonitor'
    except (OSError, ValueError):
        return False
