@echo off
setlocal
cd /d "%~dp0"
set "UV_CACHE_DIR=%~dp0.local\uv-cache"
where uv >nul 2>nul
if errorlevel 1 (
  echo Install uv from https://docs.astral.sh/uv/getting-started/installation/
  exit /b 1
)
uv sync --project api --python 3.12 --locked
if errorlevel 1 exit /b 1
if exist ".local\node\npm.cmd" set "PATH=%~dp0.local\node;%PATH%"
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 22 LTS, then rerun setup.cmd.
  exit /b 1
)
pushd ui
call npm.cmd ci
if errorlevel 1 (popd & exit /b 1)
call npm.cmd run build
if errorlevel 1 (popd & exit /b 1)
popd
echo Ready. Run start.cmd.
