# Nexora MultiLogin: núcleo local e limites técnicos

Atualizado para execução local com `INICIAR.bat` em `http://127.0.0.1:3000`.
O projeto existente usa Python, servidor HTTP local e Playwright Chromium;
não foi refeito em Electron. Não há dependência do código protegido do ProxyBet.

## Fluxo real

1. `DeviceProfileManager` valida um cadastro, cria ID UUID hexadecimal,
   associa o site e chama `Store`. Novos IDs criam diretórios próprios.
2. `FingerprintManager.generate` guarda um **snapshot versionado de
   emulação Playwright** (nome e descritor oficial) em `data/settings.json`.
   Isso não é identidade física única; perfis diferentes podem selecionar o
   mesmo modelo e a emulação pode mostrar propriedades do Windows.
3. `BrowserManager.start` lê o snapshot, compara com o Playwright instalado,
   aplica as opções do contexto **antes de navegar** e abre
   `data/profiles/<id>` com `launch_persistent_context`. Não injeta código
   para disfarçar automação.
4. `SessionManager` acompanha abertura, encerramento e falhas. O limite
   `MULTILOGIN_MAX_OPEN` (padrão 6, mínimo 1, máximo 12) restringe apenas
   janelas simultâneas; não restringe cadastros.
5. Ao parar o perfil pelo painel, o navegador fecha e o backup local de cookies
   de sessão é salvo por perfil. Dados como IndexedDB e localStorage pertencem
   ao user data dir do Chromium. A recuperação depois de travamento abrupto
   depende também das regras do site, encerramento e do Chromium.

## Interface e APIs locais

- **Criar perfil / Editar**: seleciona um dos presets oficiais Android
  documentados no Playwright, incluindo orientações de tela.
- **Iniciar / Encerrar**: janela real independente do Chromium.
- **Duplicar**: copia apenas preferências, gerando novo ID; não copia cookies,
  senhas, localStorage, arquivos ou login.
- **Diagnóstico**: quando aberto, mede propriedades observáveis numa página
  local descartável e informa divergências. Quando parado, mostra somente a
  configuração. Não fornece classificação de antifraude.
- **Recriar preset**: requer confirmação e janela fechada. Regrava o descritor
  oficial do mesmo modelo. **Não cria hardware/fingerprint físico diferente**.
- `GET /api/sessions`: estados observados e limite de concorrência.
- `GET /api/profiles/inspect/<id>`: snapshot e inspeção observada.
- `GET /api/profiles/export/<id>`: configurações, nunca cookies.
- `POST /api/profiles/import-config`: importa somente configuração e gera
  uma identidade nova com armazenamento vazio.
- `POST /api/profiles/duplicate` e `POST /api/profiles/regenerate`.

As APIs locais são restritas à interface loopback; não devem ser publicadas
diretamente para a Internet. Não substituem autenticação multiusuário.

## Ainda não implementado

- Fingerprint Generator/Injector da Apify; **nenhum spoof de GPU, WebGL,
  Canvas, fontes, WebRTC, Client Hints ou navigator.webdriver**.
- Catálogos desktop Windows/Linux, Android físico ou iPhone real.
- Proxies individuais, cofres de senhas de proxy, teste de IP/DNS/WebRTC,
  bloqueio e validação de conexão por proxy.
- Layouts por monitor, seleção múltipla/espelho, gerenciamento de instâncias
  independentes e IPC de uma extensão.
- Migração automática dos arquivos guardados em `runner/data/profiles`
  pelo executor remoto. O painel localhost mantém `data/profiles`.
- Testes de carga reais com meses de 200 novos registros por dia, teste manual
  de janelas nativas Windows e verificações online de sites de fingerprint.
- O executor remoto Cloudflare ainda usa seu fluxo anterior de perfil/cookie
  independente e não as novas APIs do FingerprintManager local.

**Não envie `data/` nem `runner/data/` ao GitHub**, pois contêm dados privados.
Os arquivos estão excluídos pelo `.gitignore` do projeto.

## Testes

O CI usa Python 3.12, Node.js e Chromium Playwright 1.57; inclui testes
de criação, duplicação, snapshot, migração, HTTP, isolamento de cookies,
localStorage, seleção de modelos, reabertura e leitura real de propriedades.
A matriz contém teste de Chromium headless, modo headed sob Xvfb e validação
dos descritores no Windows. A abertura gráfica real no PC do usuário ainda
exige conferência local.

Para usar após os testes, execute:
```powershell
cd "$HOME\Nexora-GitHub"
git pull
.\INICIAR.bat
```
