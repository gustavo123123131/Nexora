@echo off
setlocal
cd /d "%~dp0"
title MultiLogin Mobile - Servidor Local

echo.
echo ================================================
echo       MULTILOGIN MOBILE - INSTALACAO
 echo ================================================
if exist ".venv\Scripts\python.exe" goto ready
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m venv .venv
) else (
  where python >nul 2>&1
  if errorlevel 1 goto missingPython
  python -m venv .venv
)
if errorlevel 1 goto failed

:ready
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto failed

echo.
echo Abrindo painel em http://127.0.0.1:3000
".venv\Scripts\python.exe" server.py
echo.
echo Servidor encerrado.
pause
exit /b 0

:missingPython
echo Python 3 nao encontrado. Instale Python do site https://www.python.org/downloads/
echo Marque a opcao "Add python.exe to PATH", depois execute este arquivo novamente.
pause
exit /b 1

:failed
echo.
echo Nao foi possivel preparar o ambiente. Veja a mensagem acima.
echo A primeira instalacao precisa de internet para baixar Playwright/Chromium.
pause
exit /b 1
