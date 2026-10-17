@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0release\ClipboardSync.exe" (
  start "" "%~dp0release\ClipboardSync.exe"
  exit /b 0
)
call "%~dp0build.bat" /s
if errorlevel 1 exit /b %errorlevel%
start "" "%~dp0release\ClipboardSync.exe"
