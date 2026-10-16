@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure_napcat.ps1"
if errorlevel 1 (
    pause
    exit /b 1
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launcher.py"
    exit /b
)
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw "%~dp0launcher.py"
    exit /b
)
where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw -3 "%~dp0launcher.py"
    exit /b
)
where python >nul 2>&1
if not errorlevel 1 (
    python "%~dp0launcher.py"
    exit /b
)
echo 未找到 Python。请安装 Python 3.9 或更新版本，并勾选 Add Python to PATH。
echo 安装后先运行“初始化环境.bat”，再双击本文件。
pause

