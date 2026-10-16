import importlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock


class StartupTests(unittest.TestCase):
    def test_persistent_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            from runtime_support import load_secret
            first = load_secret(Path(tmp))
            self.assertEqual(first, load_secret(Path(tmp)))
            self.assertGreaterEqual(len(first), 48)

    def test_single_instance_lock_releases(self):
        from runtime_support import InstanceLock
        with tempfile.TemporaryDirectory() as tmp:
            one, two = InstanceLock(Path(tmp)), InstanceLock(Path(tmp))
            self.assertTrue(one.acquire())
            try:
                self.assertFalse(two.acquire())
            finally:
                one.close()
            self.assertTrue(two.acquire())
            two.close()

    def test_config_migration_preserves_user_settings(self):
        from database import Database
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'old.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE user_config (user_id INTEGER PRIMARY KEY, keywords TEXT, keyword_mode TEXT, interval_seconds INTEGER, notification_enabled INTEGER, group_name TEXT, ws_url TEXT)')
                conn.execute("INSERT INTO user_config VALUES (7, '作业', 'exact', 5, 1, '测试群', 'ws://localhost:3001')")
            conn.close()
            db = Database(path)
            cfg = db.get_user_config(7)
            self.assertTrue(cfg['auto_start'])
            self.assertEqual(cfg['keywords'], '作业')
            cfg['auto_start'] = False
            db.save_user_config(7, cfg)
            self.assertFalse(Database(path).get_user_config(7)['auto_start'])

    def test_monitor_reports_real_connection(self):
        from monitor import Monitor
        m = Monitor(None, None, None)
        self.assertFalse(m.get_status()['connected'])
        m._client = Mock(connected=True, online=False)
        self.assertFalse(m.get_status()['connected'])  # stopped monitor
        m._running.set()
        self.assertTrue(m.get_status()['connected'])
        self.assertFalse(m.get_status()['online'])

    def test_onebot_status_and_stop_clear_connection(self):
        from onebot_client import OneBotClient
        c = OneBotClient()
        c._parse_event({'echo': 'qqmonitor-status', 'status': 'ok', 'data': {'online': True}})
        self.assertTrue(c.online)
        c._connected.set()
        c.stop()
        self.assertFalse(c.connected)
        self.assertFalse(c.online)

    def test_empty_websocket_frame_disconnects_and_stop_interrupts_backoff(self):
        from onebot_client import OneBotClient
        import threading
        import time
        c = OneBotClient()
        ws = Mock()
        received = threading.Event()
        def closed_frame():
            received.set()
            return ''
        ws.recv.side_effect = closed_frame
        with patch('onebot_client.websocket.create_connection', return_value=ws):
            c.start()
            self.assertTrue(received.wait(2))
            deadline = time.monotonic() + 1
            while c.connected and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(c.connected)
            started = time.monotonic()
            c.stop()
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertFalse(c._thread.is_alive())


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = patch.dict(os.environ, {'APPDATA': cls.tmp.name})
        cls.env.start()
        cls.module = importlib.import_module('app')
        from database import Database
        cls.module.db = Database(Path(cls.tmp.name) / 'test.db')
        cls.module.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        import logging
        logging.shutdown()
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.client = self.module.app.test_client()

    def test_health_identifies_application(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['service'], 'qqmonitor')

    def test_auto_start_requires_login(self):
        self.assertEqual(self.client.post('/api/monitor/auto-start').status_code, 302)

    def test_auto_start_once_and_respects_opt_out(self):
        uid = self.module.db.create_user('test-auto', 'test-password')
        with self.client.session_transaction() as session:
            session['user_id'] = uid
        with patch.object(self.module.Monitor, 'start') as start:
            self.assertTrue(self.client.post('/api/monitor/auto-start').json['ok'])
            self.client.post('/api/monitor/auto-start')
            self.assertEqual(start.call_count, 1)
        self.module.monitors.pop(uid)
        cfg = self.module.db.get_user_config(uid)
        cfg['auto_start'] = False
        self.module.db.save_user_config(uid, cfg)
        with patch.object(self.module.Monitor, 'start') as start:
            self.client.post('/api/monitor/auto-start')
            start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
