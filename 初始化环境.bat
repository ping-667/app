@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "QQM_PY="
set "QQM_ARGS="
where py >nul 2>&1
if not errorlevel 1 (
    set "QQM_PY=py"
    set "QQM_ARGS=-3"
)
if not defined QQM_PY (
    where python >nul 2>&1
    if not errorlevel 1 set "QQM_PY=python"
)
if not defined QQM_PY (
    echo 未找到 Python。请先安装 Python 3.9 或更新版本，并添加到 PATH。
    pause
    exit /b 1
)
"%QQM_PY%" %QQM_ARGS% -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)"
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" (
    "%QQM_PY%" %QQM_ARGS% -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo 初始化完成。以后只需双击“启动.bat”。
pause
exit /b 0
:failed
echo 初始化失败。请检查 Python 版本、网络和上方错误信息，修复后重新运行。
pause
exit /b 1
