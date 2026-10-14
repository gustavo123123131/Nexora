@echo off
setlocal
cd /d "%~dp0"
set "MULTILOGIN_BROWSER_MODE=chrome-manual"
echo.
echo MODO CHROME MANUAL (sem Playwright no navegador aberto)
echo Chrome instalado e necessario. Perfis manuais ficam em data\profiles\ID\chrome-manual.
echo Feche as janelas de Chrome manualmente para salvar os dados.
echo.
call "%~dp0INICIAR.bat"
