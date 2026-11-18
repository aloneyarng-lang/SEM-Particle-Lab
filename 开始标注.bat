@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 app\server.py
) else (
  where python >nul 2>&1
  if not errorlevel 1 (
    python app\server.py
  ) else (
    echo 未找到 Python 3。请安装 Python 3 后重新双击本文件。
  )
)
echo.
pause
