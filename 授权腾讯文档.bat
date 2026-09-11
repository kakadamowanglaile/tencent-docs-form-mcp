@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -File ".\install-windows.ps1"
  if errorlevel 1 (
    echo 安装失败，请检查上方提示。
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" ".\openapi_setup.py"
if errorlevel 1 pause
