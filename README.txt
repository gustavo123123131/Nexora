MULTILOGIN MOBILE - MVP para Windows
=================================

PARA INICIAR
1. Extraia o ZIP completo para uma pasta (por exemplo, Area de Trabalho\MultiLogin Mobile).
2. Instale Python 3 (3.11, 3.12 ou 3.13) em https://www.python.org/downloads/ se ainda nao tiver.
   No instalador, marque "Add python.exe to PATH" se essa opcao aparecer.
3. Com internet no primeiro uso, clique duas vezes em INICIAR.bat.
   Aguarde: o programa instala o Playwright e baixa o Chromium. Isso pode levar alguns minutos.
4. O painel abre sozinho em http://127.0.0.1:3000.
   Se nao abrir sozinho, cole o endereco no Chrome.
5. Cadastre um site, crie um perfil e clique "Iniciar".
   Um Chromium separado abre no endereco do site com configuracoes mobile Android.
6. Faca seu login normalmente na janela. Feche o perfil pelo painel.
7. Para terminar, volte ao terminal preto do programa e use Ctrl+C.
   Nao feche a janela do terminal de maneira forcada se os perfis estiverem abertos.

IMPORTANTE
- O painel e o servidor funcionam somente neste computador (127.0.0.1).
- Cada perfil usa sua propria pasta dentro de data/profiles; cookies e dados do site ficam nessa pasta.
- A pasta data/ contem sessoes privadas. NAO envie, compartilhe nem sincronize essa pasta.
- Excluir um perfil apaga definitivamente sua pasta de sessao e o login salvo.
- A persistencia do login depende tambem das regras do site (expiracao, autenticacao, etc.).
- Os perfis simulam um Chrome mobile Android no Chromium para Windows. NAO e um Android real.
- Alguns sites identificam diferencias de plataforma e podem nao funcionar como no Android real.
- Nao altere manualmente os arquivos da pasta data/ enquanto o sistema estiver rodando.
- Portas: padrao 3000; se estiver em uso, encerre o outro programa antes de iniciar.
- No primeiro uso, o Playwright baixa o Chromium para o cache do usuario do Windows.

SEM AUTOMAÇÕES
Esta versao nao automatiza login nem operacoes no site. O login e manual.
Nao inclui proxies, extensoes de terceiros, Android real ou emulador de aplicativos.

TESTES
Para executar testes automaticos num computador preparado com Playwright/Chromium:
  .venv\Scripts\python.exe -m unittest discover -s tests -v
Um navegador sem interface e usado nos testes de isolamento e persistencia.

CODIGO
server.py: painel e API HTTP locais (biblioteca padrao do Python)
storage.py: cadastro de sites, perfis e persistencia atomica em JSON
browser_manager.py: navegador Chromium individual por perfil, via Playwright
public/: interface offline (HTML/CSS/JS sem bibliotecas externas)

Caso apareca erro de acesso ou inicio, envie uma foto do texto do terminal.

Para verificar o seu PC, execute TESTAR.bat apos a instalacao inicial.
Se ele indicar skipped para localStorage, a navegacao de teste estava indisponivel no ambiente.
