@echo off
cd /d "%~dp0"
echo.
echo   QQ群消息监控 - Web版
echo   正在启动...
echo.
start http://127.0.0.1:5000
python app.py
pause
