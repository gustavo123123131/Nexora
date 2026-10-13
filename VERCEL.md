# Nexora — modo gratuito Windows + Cloudflare Tunnel

**Agora existe a alternativa sem Railway, sem servidor pago e sem domínio comprado.**
O Nexora continua aberto pela Vercel, e o Chromium com sessões independentes roda
no computador Windows do usuário, conectado por **Cloudflare Quick Tunnel**.

1. Sincronize o repositório no GitHub Desktop (Fetch/Pull origin).
2. Instale `cloudflared` no Windows, por exemplo com `winget install -e --id Cloudflare.cloudflared`.
3. Na pasta do projeto, clique duas vezes em `INICIAR_EXECUTOR_WINDOWS.bat`.
4. Aguarde a instalação de Flask, Playwright e Chromium na primeira execução.
5. Copie da janela preta a URL temporária `https://...trycloudflare.com`.
6. Acesse https://nexora-ebon-eight.vercel.app, clique **Conectar navegador**,
   cole a URL e a chave privada gerada no Windows. A Vercel **não exige
   NEXORA_RUNNER_URL nem redeploy** para esse fluxo.
7. Clique em **Abrir** para iniciar Chromium isolado no perfil e
   **Ver navegador** para retomar a janela. **Encerrar** salva os cookies no PC.

Segurança: nunca envie a chave da janela preta a ninguém.
Ela fica salva em `runner/private/runner-key.txt` e os perfis em
`runner/data/profiles/`; ambas as pastas são excluídas pelo `.gitignore`.
Seus dados antigos do modo localhost permanecem intocados.
O servidor escuta apenas `127.0.0.1:8765`, e o Cloudflare publica
um endereço HTTPS temporário autenticado por chave. O navegador na Vercel
envia as chamadas ao túnel usando CORS restrito à origem do Nexora.

**Limitação do modo gratuito:** o Windows e a janela do executor devem
permanecer ligados. Quando o Quick Tunnel reinicia, a URL muda;
é preciso reconectá-la pelo botão, sem alterar o GitHub/Vercel.
Quick Tunnels não são serviço de produção com SLA.
O sistema emula Pixel 7 com Chromium; não é Android real.
Leia `runner/README.md` para detalhes.

---

# Nexora — Vercel: uso sem senha (versão de teste)

## Como funciona por padrão

Abra o endereço HTTPS do projeto na Vercel. **Não é necessário configurar DATABASE_URL,
NEXORA_ACCESS_PASSWORD nem NEXORA_SESSION_SECRET para usar o modo padrão.**

O Nexora permite:
- Cadastrar, editar e excluir sites.
- Cadastrar e excluir perfis.
- Importar `settings.json` da versão antiga (somente nomes/URLs/IDs).
- Visitar o site de um perfil em uma aba comum, com aviso claro de que **NÃO existe isolamento**.

Os cadastros ficam no `localStorage` **do navegador e da origem HTTPS usada**.
Eles NÃO são salvos na Vercel nem sincronizados entre computadores ou outros
navegadores. Alterar o domínio, limpar os dados do site ou navegar em modo
anônimo pode fazer os cadastros desaparecerem. Faça backup dos seus dados.
Não são armazenados cookies nem senhas de sites no Nexora.

Para acessar esse modo, use a URL normal da implantação, sem parâmetros.
O formulário de senha NÃO aparece neste modo.

**ATENÇÃO: ISTO NÃO É MULTI-LOGIN FUNCIONAL.** Uma aba comum compartilha cookies com
as demais abas do mesmo perfil de Chrome. Para abrir duas contas no mesmo site
com autenticação realmente separada, será preciso um executor externo de
navegadores persistentes com isolamento e streaming das sessões. A Vercel
serverless, sozinha, não é esse executor. Nenhum teste real de isolamento
remoto pode ser considerado aprovado neste estágio.

## Modo legado opcional: PostgreSQL e senha

O backend antigo continua disponível sem perder os cadastros existentes.
Para usá-lo explicitamente, acesse a URL com `?storage=cloud` e configure na Vercel:
- `DATABASE_URL` (ou `POSTGRES_URL`): PostgreSQL externo (por exemplo Neon).
- `NEXORA_ACCESS_PASSWORD`: senha com ao menos 12 caracteres.
- `NEXORA_SESSION_SECRET`: segredo aleatório com ao menos 32 caracteres.

Esse modo continua protegido por senha. Não remova sua autenticação e
NÃO publique o banco de dados sem proteção. Dados dos modos
"neste navegador" e "PostgreSQL" são separados, sem sincronização automática.

## Implantação

1. Vercel > Add New > Project > importe `gustavo123123131/Nexora` (branch `main`).
2. Preset: Flask; Root Directory `./`. Arquivos estáticos em `public/`.
3. Implante ou, se o projeto já estiver vinculado ao GitHub, aguarde o deploy automático.
4. Abra a URL HTTPS da Vercel. O painel deve abrir no modo sem senha.
5. Na aba Sites, o botão "Importar settings.json" pode carregar os cadastros
   do projeto anterior para este navegador. Não transfere cookies/sessões.
6. Se aparecer uma versão antiga, confirme o sucesso do último deploy,
   faça uma atualização forçada (Ctrl+F5) e verifique o endereço.

Arquivos de `data/`, `data/profiles/`, `.venv/` e cookies locais não devem ser
enviados ao GitHub. O repositório está público: recomenda-se torná-lo privado,
principalmente porque há um `data/settings.json` antigo no histórico.
Nenhum dado do banco remoto anterior ou da pasta local foi apagado por esta mudança.

## Verificações e limitações

- Sintaxe JavaScript das duas partes validada em ambiente V8.
- Testes de lógica do armazenamento simulando o navegador: criação,
  persistência, importação, validação e exclusão.
- Navegação real, integração Vercel em produção e sessões Chromium remotas:
  **não testadas**; as sessões remotas ainda não estão implementadas.
- O modo local antigo do Windows permanece nos arquivos `server.py`,
  `browser_manager.py` e `INICIAR.bat` para não remover funcionalidades existentes.


## Abrir perfis reais: executor remoto persistente

O painel da Vercel agora possui **Conectar navegador**, **Abrir**, **Ver navegador**
e **Encerrar**. Esses botões só passam a controlar sessões reais depois de
hospedar o serviço em `runner/` e conectá-lo à Vercel.

A **Vercel sozinha não é suficiente** para executar um navegador interativo
persistente e salvar cookies de vários perfis. Cada perfil do executor
usa `/data/profiles/<id>` e um contexto Chromium separado. A visualização
é feita por capturas JPEG sequenciais e ações enviadas pelo painel;
isso não é Android nativo nem streaming de vídeo perfeito.

Implantação manual (sem plugins):
1. Use um serviço que suporte Docker, execução persistente e volume.
   Exemplo: Railway > New Project > Deploy from GitHub `Nexora`,
   Root Directory `/runner` (detectará `runner/Dockerfile`).
2. Monte volume persistente em `/data` e mantenha
   `NEXORA_PROFILE_DIR=/data/profiles`.
3. Configure `NEXORA_RUNNER_KEY` como segredo aleatório de no mínimo
   32 caracteres (exemplo de geração local: `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
   Não escreva a chave no repositório, nem mande para conversas públicas.
4. Gere um domínio público HTTPS para o executor.
5. Na Vercel, Environment Variables: `NEXORA_RUNNER_URL=https://DOMINIO-DO-EXECUTOR`
   sem barra final. Faça Redeploy.
6. Abra a URL Nexora, clique **Conectar navegador**, digite a chave privada
   e clique em **Abrir** em um perfil.
7. **Ver navegador** mostra a janela mobile para clicar, digitar, Tab,
   Enter, scroll e voltar. **Encerrar** fecha o processo preservando
   cookies no volume. Uma reinicialização do executor fecha navegadores
   ativos, mas não deve perder os perfis se o volume permanecer.

**Segurança:** mantenha a chave privada. O executor não fica exposto
sem autenticação, embora o endereço da interface seja público.
A versão atual do Docker usa Chromium sem sandbox em um contêiner;
evite navegar em sites não confiáveis. Para produção, devemos isolar melhor
o executor e definir limites de acesso e recursos.

**Custo e validação:** serviço persistente com armazenamento pode exigir
pagamento; nenhum preço ou gratuidade é garantido. Os testes do GitHub
podem validar a lógica do Chromium; ainda é necessário testar a implantação
e o login com suas contas reais. Dados do modo local no Windows
não migram automaticamente ao executor remoto.
