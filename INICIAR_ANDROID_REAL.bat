@echo off
setlocal
cd /d "%~dp0"
set "MULTILOGIN_BROWSER_MODE=android-real"
title Nexora - Android conectado (localhost)
echo.
echo ================================================
echo     NEXORA - ANDROID CONECTADO VIA USB
echo ================================================
echo Esse modo usa o navegador do seu Android, SEM Playwright.
echo Instale adb (Android Platform Tools) e scrcpy no PATH.
echo Ative depuracao USB no celular e aceite a autorizacao.
echo Um celular conectado nao cria multiplos Androids separados.
echo.
call "%~dp0INICIAR.bat"
