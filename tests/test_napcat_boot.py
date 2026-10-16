import json
from pathlib import Path
import tempfile
import unittest


class NapCatBootTests(unittest.TestCase):
    def test_native_loader_uses_bundled_four_argument_entry(self):
        from napcat_boot import prepare_native_napcat
        with tempfile.TemporaryDirectory() as tmp:
            shell = Path(tmp)
            for name in ('napimain.exe', 'napiloader.dll', 'nativeLoader.cjs', 'napcat.mjs', 'QQ.exe'):
                (shell / name).touch()
            command, env = prepare_native_napcat(shell)
            self.assertEqual(command, ['napimain.exe', str(shell / 'QQ.exe'), str(shell / 'napiloader.dll'), str(shell / 'nativeLoader.cjs')])
            self.assertEqual(env['NAPCAT_LAUNCHER_PATH'], str(shell / 'napimain.exe'))
            self.assertNotIn('NAPCAT_PATCH_PACKAGE', env)

    def test_explicit_qq_hook_and_loader_environment(self):
        from napcat_boot import prepare_napcat
        with tempfile.TemporaryDirectory(prefix='napcat space ') as tmp:
            root = Path(tmp)
            shell = root / '程序'
            shell.mkdir()
            for name in ('NapCatWinBootMain.exe', 'NapCatWinBootHook.dll', 'napcat.mjs', 'QQ.exe'):
                (shell / name).touch()
            (shell / 'qqnt.json').write_text('{"main":"./loadNapCat.js"}')
            command, env = prepare_napcat(shell, root / 'runtime')
            self.assertEqual(command, ['NapCatWinBootMain.exe', '.\\QQ.exe', '.\\NapCatWinBootHook.dll'])
            self.assertEqual(env['NAPCAT_PATCH_PACKAGE'], str(shell / 'qqnt.json'))
            self.assertEqual(env['NAPCAT_MAIN_PATH'], (shell / 'napcat.mjs').as_posix())
            loader = Path(env['NAPCAT_LOAD_PATH']).read_text(encoding='utf-8')
            self.assertIn(json.dumps((shell / 'napcat.mjs').as_uri()), loader)
            self.assertFalse((shell / 'loadNapCat.js').exists())

    def test_missing_hook_fails_before_launch(self):
        from napcat_boot import prepare_napcat
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'NapCatWinBootHook.dll'):
                prepare_napcat(Path(tmp), Path(tmp) / 'runtime')


if __name__ == '__main__':
    unittest.main()
