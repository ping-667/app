"""Prepare the same QQ injection arguments used by launcher-user.bat."""
import json
import os
from pathlib import Path


def find_qq(shell):
    # The Shell bundle includes a QQ executable and its versioned resources.
    bundled = shell / 'QQ.exe'
    if bundled.is_file():
        return bundled
    candidates = []
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key_name in (r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ',
                             r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QQ'):
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        raw, _ = winreg.QueryValueEx(key, 'UninstallString')
                        raw = raw.strip()
                        uninstall = raw.split('"')[1] if raw.startswith('"') else raw
                        candidates.append(Path(uninstall).parent / 'QQ.exe')
                except OSError:
                    pass
    for variable in ('ProgramFiles', 'ProgramFiles(x86)'):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / 'Tencent' / 'QQNT' / 'QQ.exe')
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError('未找到 QQ.exe。请安装 QQ，或选择包含 QQ.exe 的完整 NapCat Shell 目录。')


def prepare_napcat(shell, runtime):
    shell = Path(shell).resolve()
    for name in ('NapCatWinBootHook.dll', 'NapCatWinBootMain.exe', 'napcat.mjs', 'qqnt.json'):
        if not (shell / name).is_file():
            raise RuntimeError(f'NapCat 目录缺少 {name}，请选择完整 Shell 目录。')
    qq = find_qq(shell)
    runtime = Path(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    loader = runtime / 'loadNapCat.js'
    loader.write_text('(async () => {await import(' + json.dumps((shell / 'napcat.mjs').as_uri()) + ')})()\n',
                      encoding='utf-8')
    env = os.environ.copy()
    env.update({
        'NAPCAT_PATCH_PACKAGE': str(shell / 'qqnt.json'),
        'NAPCAT_LOAD_PATH': str(loader.resolve()),
        'NAPCAT_INJECT_PATH': str(shell / 'NapCatWinBootHook.dll'),
        'NAPCAT_LAUNCHER_PATH': str(shell / 'NapCatWinBootMain.exe'),
        'NAPCAT_MAIN_PATH': (shell / 'napcat.mjs').as_posix(),
    })
    # This boot binary prints argv with std::wcout in the C locale. A Chinese
    # path sets failbit and suppresses all later stdout, including errors.
    # Keep argv ASCII for bundled QQ. Popen's executable= supplies the real
    # absolute binary path without exposing it as argv[0].
    qq_argument = '.\\QQ.exe' if qq.parent == shell else str(qq)
    return ['NapCatWinBootMain.exe', qq_argument, '.\\NapCatWinBootHook.dll'], env


def prepare_native_napcat(shell):
    """Mirror the bundle's napiLoader.bat, using its Unicode-aware launcher."""
    shell = Path(shell).resolve()
    for name in ('napimain.exe', 'napiloader.dll', 'nativeLoader.cjs', 'napcat.mjs'):
        if not (shell / name).is_file():
            raise RuntimeError(f'原生加载入口缺少 {name}。请补全安装包或选择旧版加载方式。')
    qq = find_qq(shell)
    env = {key: value for key, value in os.environ.items() if not key.startswith('NAPCAT_')}
    env.update({
        'NAPCAT_LAUNCHER_PATH': str(shell / 'napimain.exe'),
        'NAPCAT_INJECT_PATH': str(shell / 'napiloader.dll'),
        'NAPCAT_MAIN_PATH': (shell / 'nativeLoader.cjs').as_posix(),
        'NAPCAT_QQ_PATH': str(qq),
        'NAPCAT_DLL_PATH': str(shell / 'napiloader.dll'),
        'NAPCAT_EXTERNAL_SCRIPT_PATH': str(shell / 'nativeLoader.cjs'),
    })
    return ['napimain.exe', str(qq), str(shell / 'napiloader.dll'), str(shell / 'nativeLoader.cjs')], env
