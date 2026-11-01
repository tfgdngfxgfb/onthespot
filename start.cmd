@echo off
setlocal
cd /d "%~dp0"
set "ONTHESPOTDIR=%~dp0.local\config"
set "ONTHESPOTCACHEDIR=%~dp0.local\cache"
set "ONTHESPOT_PORT=6767"
set "PYTHONPATH=%~dp0api\src"
set "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python"
if not exist "api\.venv\Scripts\python.exe" (
  echo Run setup.cmd first.
  exit /b 1
)
if not exist "ui\dist\index.html" (
  echo Build the frontend with setup.cmd first.
  exit /b 1
)
echo Open http://127.0.0.1:6767
"api\.venv\Scripts\python.exe" -m onthespot.main
