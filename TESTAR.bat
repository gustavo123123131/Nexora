@echo off
setlocal
cd /d "%~dp0"
title MultiLogin Mobile - Testes
if not exist ".venv\Scripts\python.exe" (
  echo Execute INICIAR.bat ao menos uma vez antes de testar.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 (
  echo.
  echo Alguns testes falharam. Envie uma captura desta janela.
) else (
  echo.
  echo Testes concluidos. Verifique se houve testes ignorados ^(skipped^).
)
pause
