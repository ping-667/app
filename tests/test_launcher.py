import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock


class LauncherTests(unittest.TestCase):
    def test_windows_entry_scripts_use_crlf(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('启动.bat', '初始化环境.bat'):
            data = (root / name).read_bytes()
            self.assertIn(b'\r\n', data)
            self.assertNotIn(b'\n', data.replace(b'\r\n', b''))

    def test_failed_napcat_spawn_releases_job_for_retry(self):
        import launcher
        import queue
        import threading
        obj = launcher.Launcher.__new__(launcher.Launcher)
        with tempfile.TemporaryDirectory() as tmp:
            obj.napcat = Path(tmp)
            (obj.napcat / 'napcat.mjs').touch()
            (obj.napcat / 'NapCatWinBootMain.exe').touch()
            obj.ready, obj.job, obj.log_handle = True, None, None
            obj.loader_mode = 'legacy'
            obj.events, obj.stop_event = queue.Queue(), threading.Event()
            job = Mock()
            job.start.side_effect = OSError('test spawn failed')
            with patch.object(obj, 'existing_napcat', return_value=False), \
                 patch.object(launcher, 'ROOT', Path(tmp)), \
                 patch('napcat_boot.prepare_napcat', return_value=(['fake.exe', 'QQ.exe', 'hook.dll'], {'NAPCAT_LAUNCHER_PATH': 'fake.exe'})), \
                 patch.object(launcher, 'data_dir', return_value=Path(tmp)), \
                 patch('windows_job.ProcessJob', return_value=job):
                with self.assertLogs(level='ERROR'):
                    obj.boot()
            job.close.assert_called_once()
            self.assertIsNone(obj.job)
            self.assertIsNone(obj.log_handle)

    def test_unrelated_port_is_reported_as_conflict(self):
        import launcher
        obj = launcher.Launcher.__new__(launcher.Launcher)
        obj.napcat = Path('nonexistent')
        with patch.object(launcher, 'port_open', return_value=True), \
             patch.object(launcher, 'is_napcat_webui', return_value=False), \
             patch.object(launcher, 'is_onebot', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '占用'):
                obj.existing_napcat()

    def test_job_kills_grandchild_after_parent_exits(self):
        from windows_job import ProcessJob
        import ctypes
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / 'pid.txt'
            code = ("import subprocess,sys,pathlib; "
                    "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); "
                    "pathlib.Path(sys.argv[1]).write_text(str(p.pid))")
            with ProcessJob() as job:
                parent = job.start([sys.executable, '-c', code, str(pid_file)])
                parent.wait(timeout=5)
                pid = int(pid_file.read_text())
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
                kernel.OpenProcess.restype = ctypes.c_void_p
                kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                handle = kernel.OpenProcess(0x100000, False, pid)
                self.assertTrue(handle)
            try:
                self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
            finally:
                kernel.CloseHandle(handle)

    def test_launcher_window_starts_web_and_shuts_down(self):
        import tkinter as tk
        import launcher
        # Real Tk + real HTTP server; only third-party QQ launch/browser are mocked.
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            Path(tmp, 'launcher.json').write_text('{"port": %d}' % port)
            with patch.dict(os.environ, {'APPDATA': tmp}), \
                 patch.object(launcher, 'data_dir', return_value=Path(tmp)), \
                 patch.object(launcher.Launcher, 'existing_napcat', return_value=True), \
                 patch.object(launcher.webbrowser, 'open'):
                root = tk.Tk()
                root.withdraw()
                window = launcher.Launcher(root)
                deadline = time.monotonic() + 8
                while not window.ready and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.02)
                self.assertTrue(window.ready)
                self.assertTrue(launcher.is_our_server(window.url))
                window.close()
                while time.monotonic() < deadline:
                    try:
                        if not root.winfo_exists():
                            break
                        root.update()
                    except tk.TclError:
                        break
                    time.sleep(0.02)
                self.assertFalse(launcher.is_our_server(window.url))
                import logging
                logging.shutdown()
                for handler in logging.root.handlers[:]:
                    logging.root.removeHandler(handler)

    def test_napcat_discovery_uses_complete_shell(self):
        from launcher import discover_napcat
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shell = root / 'NapCatQQ' / 'NapCat.test.Shell'
            shell.mkdir(parents=True)
            self.assertIsNone(discover_napcat(root))
            (shell / 'NapCatWinBootMain.exe').touch()
            (shell / 'napcat.mjs').touch()
            self.assertEqual(discover_napcat(root), shell)

    def test_web_server_port_conflict_does_not_exit_process(self):
        from launcher import create_server
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            with self.assertRaises(RuntimeError):
                create_server(lambda e, s: [], sock.getsockname()[1])

    @unittest.skipUnless(os.name == 'nt', 'Windows job object')
    def test_job_stops_owned_child_but_not_other_process(self):
        from windows_job import ProcessJob
        outside = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with ProcessJob() as job:
                child = job.start([sys.executable, '-c', 'import time; time.sleep(60)'])
                self.assertIsNone(child.poll())
                self.assertTrue(job.active())
            self.assertIsNotNone(child.wait(timeout=5))
            self.assertFalse(job.active())
            self.assertIsNone(outside.poll())
        finally:
            outside.terminate()
            outside.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
