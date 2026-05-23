@echo off
title QQ-Monitor Web
cd /d "E:\程序"

set PYCMD=
if exist "E:\Anaconda\python.exe" set PYCMD=E:\Anaconda\python.exe
if "%PYCMD%"=="" where python >nul 2>&1 && set PYCMD=python
if "%PYCMD%"=="" where py >nul 2>&1 && set PYCMD=py
if "%PYCMD%"=="" (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

echo.
echo   QQ-Monitor Web Server
echo   http://127.0.0.1:5000
echo   Close this window to stop
echo.
echo Python: %PYCMD%
echo.

start http://127.0.0.1:5000
"%PYCMD%" app.py
pause
