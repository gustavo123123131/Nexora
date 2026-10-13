# Janelas reais do Chromium no Windows — Nexora

**Novo comportamento (Windows):** **Iniciar perfil** abre uma janela nativa
visível do Chromium na sua área de trabalho. Não há iframe e não aparece a
visualização de screenshots dentro da Vercel. A janela pode ser arrastada,
minimizada, maximizada e redimensionada. Mouse, teclado, barra de endereços
e navegação funcionam diretamente no Chromium.

Cada perfil continua usando um diretório exclusivo em
`runner/data/profiles/<id>`, com Chromium persistente e cookies separados.
O preset Playwright **Pixel 7** configura user-agent Android, viewport,
escala e toque emulados (não é um Android real). Como se trata de uma
emulação mobile com viewport fixo, redimensionar a janela do sistema não
necessariamente muda o tamanho do viewport emulado.

## Atualizar e usar no PC em que o executor já está instalado

1. No Nexora, clique **Encerrar** nos perfis abertos; depois pressione
   **Ctrl+C** na janela preta do executor para parar o processo antigo.
2. Abra um **PowerShell** e execute:
   `cd "$HOME\Nexora-GitHub"`
   `git pull`
   `.\INICIAR_EXECUTOR_WINDOWS.bat`
3. O iniciador vai mostrar uma **NOVA** URL temporária Cloudflare.
   Mantenha a janela preta aberta.
4. Acesse https://nexora-ebon-eight.vercel.app e recarregue com **Ctrl+F5**.
   Clique **Conectar navegador**, cole a nova URL e a chave privada que
   já existe no seu Windows (não a envie em chats).
5. Clique **Iniciar perfil**. A janela real do Chromium aparecerá na
   área de trabalho do Windows. Para gerenciar o perfil, volte ao painel
   usando Alt+Tab ou a barra de tarefas; clique **Encerrar** para fechar
   e salvar a sessão. Abra perfis diferentes para ter janelas independentes.

**Importante:** a Vercel não abre janelas no Windows diretamente. O
`runner/worker.py` precisa estar rodando na sessão gráfica do Windows.
O Cloudflare Tunnel apenas encaminha os comandos autenticados. O PC
precisa estar ligado, e perfis abertos manualmente com as versões
anteriores precisam ser encerrados antes de iniciar o novo executor.
Se não aparecer a janela, verifique o firewall/antivírus, a barra de
tarefas e `runner/private/worker.log`. No Windows, não execute o
executor como Serviço do Windows ou tarefa sem usuário conectado,
pois nesse caso não existe desktop interativo para exibir a janela.

**Segurança:** o endereço Cloudflare é temporário e a chave dá acesso às
sessões. Troque qualquer chave já compartilhada publicamente antes de
entrar com contas reais; mantenha os dados de perfis fora do GitHub.

---

# Nexora Chromium Executor (Railway)

**This service is required for real multi-login on the Vercel dashboard.** It runs actual Chromium contexts in an always-on container, isolating profile folders under /data/profiles.

## Deploy once

1. Railway > New Project > Deploy from GitHub > Nexora. Set **Root Directory** to `/runner` so Railway uses runner/Dockerfile. Allocate enough memory (begin at 1–2 GB for a couple of browsers).
2. Add a **persistent Railway Volume** mounted at **`/data`**. Without the volume cookies and logins can be lost on redeploy.
3. Set `NEXORA_RUNNER_KEY` to a randomly generated secret of **32+ characters**. Store securely. Do NOT commit it to GitHub. Optional: `NEXORA_MAX_PROFILES=3`.
4. Settings > Networking > Generate Domain. Use the HTTPS domain, e.g. `https://example.up.railway.app`.
5. In Vercel's **Environment Variables**, set `NEXORA_RUNNER_URL` to this HTTPS domain **without a trailing slash**; redeploy Vercel.
6. Open the Nexora page, click **Conectar navegador**, enter the secret created in step 3. The secret lives only in this tab's sessionStorage; after closing the tab you may need to re-enter it.
7. Click **Abrir** on a profile; the site will render in the Nexora viewer. Use mouse clicks, send text, Tab, Enter, scroll; log in manually. Each profile uses its own Chromium directory.

**Important security:** this exposes interactive authenticated browsing. Only give NEXORA_RUNNER_KEY to trusted users. Railway worker requires it on every request and Vercel forwards it, without logging request bodies. Use HTTPS. No password is required to *view Nexora's metadata*, but controlling browser sessions ALWAYS requires the private key. Do not disable authentication.

**Limitations:** Streaming is screenshot polling rather than full noVNC video; some rich websites, popups, file uploads, anti-bot systems and apps needing native Android may not work. Mobile is Playwright Chromium emulation, not Android. Worker reboots close active browsers but persistent cookies are retained if volume survives. HTTP remote runner via Railway public domain is protected by key.

**No free hosting guarantee:** Railway resource usage and volumes can incur charges. The Vercel UI alone cannot run persistent browsers.

**Legacy:** Local Windows/browser manager remains unchanged. Existing *local* cookie profiles are NOT automatically imported to Railway.


## Windows + Cloudflare Quick Tunnel (sem hospedagem paga)

**Recomendado para testes gratuitos.** Use a versão atual do repositório Nexora no
seu Windows; a Vercel permanece apenas como painel HTTPS. Não é necessário
configurar NEXORA_RUNNER_URL na Vercel, contratar Railway ou comprar domínio.

1. Instale Python 3 no Windows se necessário (https://www.python.org/downloads/).
2. Instale cloudflared pelo winget: 
   \`winget install -e --id Cloudflare.cloudflared\`
   ou instale pelo guia oficial em https://developers.cloudflare.com/tunnel/.
   Feche e reabra o terminal após a instalação.
3. No GitHub Desktop, **Fetch origin → Pull origin** e abra a pasta do
   repositório. Execute **INICIAR_EXECUTOR_WINDOWS.bat** nessa pasta.
4. Na primeira vez, o .bat cria **runner/.venv-windows** e instala
   Playwright/Chromium; isso pode demorar. Não é necessário abrir
   o antigo INICIAR.bat nem o localhost:3000.
5. Após iniciar, aparece uma URL \`https://...trycloudflare.com\` e uma
   chave privada gerada automaticamente, salva em
   \`runner/private/runner-key.txt\`. **Nunca envie a chave no chat,
   em capturas de tela ou no GitHub.** Ela dá acesso às sessões dos perfis.
6. Acesse https://nexora-ebon-eight.vercel.app, recarregue com Ctrl+F5,
   clique **Conectar navegador** e cole primeiro a URL e depois a chave
   privada. Pode usar **Abrir**, **Ver navegador** e **Encerrar**.
7. Deixe a janela preta do executor e o PC ligados enquanto usa o Nexora.
   Ao reiniciar o túnel, **a URL muda**: cole a nova URL em Conectar navegador.
   A chave e os dados dos perfis continuam na pasta local.

### Dados, segurança e limitações

- Cada perfil usa a pasta \`runner/data/profiles/<id>\` e tem Chromium
  independente e cookies separados. O worker escuta **somente 127.0.0.1:8765**;
  apenas a Cloudflare faz a ponte para a internet.
- Cookies, localStorage, contas e a chave ficam no **computador**; não os
  adicione ao GitHub nem sincronize essas pastas.
- Os cadastros (nomes e endereços) no modo padrão da Vercel continuam
  no localStorage daquele navegador.
- A chave é exigida em TODA requisição ao executor; requisições de
  navegadores de outro site são bloqueadas pelo CORS/validação de Origin.
  Não existe autenticação de entrada no painel da Vercel: não compartilhe a
  chave. Mantenha os softwares atualizados.
- O Quick Tunnel é **temporário e indicado para desenvolvimento/teste**.
  A URL muda ao reiniciar, e a conexão ou o processo pode cair. Não há
  garantia de operação 24/7 sem manter o PC ligado.
- Se houver um arquivo \`~/.cloudflared/config.yaml\`, o Quick Tunnel
  pode exigir que você o mova temporariamente para outro nome.
- O Chromium usa **emulação mobile** (Pixel 7), não Android real.
  A visualização funciona com capturas periódicas da tela; não é vídeo fluido.
  Sites com antifraude ou login complexo podem não funcionar.
- As sessões antigas de \`data/profiles\` (do servidor localhost) NÃO são
  automaticamente transferidas. O launcher não as modifica; faça um novo
  login no executor se necessário.
- Não feche o terminal à força nem use a mesma pasta de perfil
  simultaneamente em dois navegadores. Feche cada perfil por Encerrar antes
  de interromper o executor. Ao encerrar o terminal de forma abrupta,
  cookies de sessão muito recentes podem não ter sido salvos.
