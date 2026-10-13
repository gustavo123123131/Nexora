@echo off
setlocal
cd /d "%~dp0"
title Nexora - MultiLogin Windows + Cloudflare Gratis
echo.
echo ==================================================
echo   NEXORA - EXECUTOR DE NAVEGADORES NO WINDOWS
echo ==================================================
echo.

set "RUNNER_PY=runner\.venv-windows\Scripts\python.exe"
if exist "%RUNNER_PY%" goto setup

where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m venv "runner\.venv-windows"
) else (
  where python >nul 2>&1
  if errorlevel 1 goto missing_python
  python -m venv "runner\.venv-windows"
)
if errorlevel 1 goto error

:setup
echo Preparando Python (instalacao inicial pode demorar)...
"%RUNNER_PY%" -m pip install --disable-pip-version-check -r runner\requirements-windows.txt
if errorlevel 1 goto error
echo Conferindo Chromium...
"%RUNNER_PY%" -m playwright install chromium
if errorlevel 1 goto error

echo.
"%RUNNER_PY%" runner\start_windows.py
if errorlevel 1 goto error
echo.
echo Executor encerrado.
pause
exit /b 0

:missing_python
echo Python 3 nao encontrado. Instale pelo https://www.python.org/downloads/
echo Depois execute este arquivo novamente.
pause
exit /b 1

:error
echo.
echo Nao foi possivel iniciar. Veja o erro acima e runner\private\worker.log
pause
exit /b 1
