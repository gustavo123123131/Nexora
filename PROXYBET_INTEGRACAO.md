# Nexora: integração independente inspirada no ProxyBet 2.5.10

## Fonte e alcance

Foi estudado o pacote fornecido pelo usuário
(`_proxybet_research(5).zip`, 491 MB compactados, coleção de pesquisa de 2026).
O inventário extraído identifica 203 exposições de métodos JavaScript em
preloads, 160 nomes únicos e 150 canais IPC distintos. A maioria dos demais
arquivos consiste em dependências e dumps de memória.

**O núcleo do ProxyBet não está disponível em fonte legível**: os handlers
principais estão em `.jsc` bytecode e conteúdo criptografado. A observação
dos contratos de IPC e de bibliotecas distribuídas **não comprova** todas as
regras internas. Nenhum dump de memória, JWT, cookie, credencial, binário
protegido ou script específico de automatização/captcha foi importado ao Nexora.

Os seguintes arquivos de referência foram estudados no pacote fornecido:

- `asar_extracted_20260824/dist/launcher/preload.js`
- `asar_extracted_20260824/dist/app/preload.js`
- `proxybet_extension_snapshot_20260824/manifest.json`
- `proxybet_extension_snapshot_20260824/background.js`
- `proxybet_extension_snapshot_20260824/content.js`
- Bibliotecas instaladas `fingerprint-generator` / `fingerprint-injector`
  (pacotes de terceiros versão 2.1.82 no material).
- Inventário de contratos, relatórios de testes isolados e arquivos
  de empacotamento da coleta.

## Correspondência das interfaces

| ProxyBet (interface exposta) | Nexora | Resultado |
|---|---|---|
| `launcher:list/create/start/stop` | `storage.Store` + `BrowserManager` | Perfis individuais já existiam; não são instâncias Electron |
| `session:start(plan)` | `POST /api/sessions/start-selected` | **Novo**: abrir uma seleção de perfis existentes |
| `session:stop` | `POST /api/sessions/stop-selected` | **Novo**: encerrar somente perfis selecionados |
| `session:get` | `GET /api/sessions` | Existente: estado do Chromium aberto |
| `screens:getMonitors` / `screens:openCustomPositions` | `POST /api/windows/arrange-selected` | **Novo**: distribuir janelas em grade na tela principal do Windows, não é editor completo de layouts |
| `openBrowser` | `BrowserManager.start` | Existente: `launch_persistent_context` Playwright |
| Dados por navegador | `data/profiles/<id>` | Existente: Chromium persistente por perfil |
| `fingerprint-generator` / `fingerprint-injector` | `FingerprintManager` | Não copiado: Nexora usa presets oficiais Playwright; não altera hardware |
| Extensão MV3, WebSocket | não importados | Não necessários ao controle de janelas Playwright |
| Proxies por conta, espelho, operações de sites | não implementados | Não é seguro declarar suporte sem núcleo/contratos verificáveis |

## O que foi implementado

Novo módulo `multilogin_controller.py` utiliza **o mesmo** `BrowserManager`
local do Nexora, preservando dados e fingerprints Android já existentes.

- Selecionar entre 1 e 12 perfis distintos no painel local.
- Abrir os selecionados, sem fechar os que já estiverem abertos.
- Encerrar os selecionados pela rotina existente (que salva cookies).
- Um erro de abertura não fecha as outras sessões.
- A regra original `MULTILOGIN_MAX_OPEN` continua definindo a quantidade
  máxima de navegadores simultâneos (padrão: 6).
- Organizar janelas Chromium realmente abertas em grade (Windows,
  monitor principal); não alterar a configuração de tela ou o viewport
  emulado Android, não copiar dados entre perfis.
- Controles novos aparecem **somente no localhost**, mantendo a interface
  da Vercel e executor remoto sem alterações de execução.

O endpoint de organização usa Chrome DevTools Protocol somente para alterar
posição/tamanho de janela já administrada pelo Playwright. Não injeta
JavaScript, não modifica rede, não fabrica fingerprints, não oculta
automação e não realiza comandos em sites.

## Como usar

1. Faça backup privado da pasta `data/` antes de atualizar.
2. Encerre perfis abertos normalmente.
3. Atualize: `git pull`.
4. Inicie com `INICIAR.bat` (inalterado).
5. Acesse `http://127.0.0.1:3000`.
6. Na lista de perfis, marque as caixas **Selecionar**.
7. Clique **Abrir selecionados**, **Organizar janelas** ou
   **Encerrar selecionados**.

Se um perfil não abrir, consulte o status da sessão e o terminal. O
comando de organizar janelas exige Windows e janelas visíveis (não headless).
Ele atua somente nos perfis escolhidos e já abertos.

## Limites de testes e da emulação

- Testes automatizados verificam seleção, IDs, isolamento lógico,
  persistência dos snapshots, interrupção independente e comandos CDP
  gerados para posicionamento.
- Testes de integração existentes verificam a abertura real e isolamento
  de perfis Chromium/Playwright.
- A organização da janela física no Windows do usuário requer validação
  manual no monitor real.
- **Não foi implementado nenhum sistema de contorno de Bot Detection,
  tampering, captcha ou outros mecanismos antifraude**. O navegador ainda
  é um Chromium Playwright e pode reportar `navigator.webdriver = true`.
  O Suspect Score do Fingerprint.com não foi medido nem garantido.
- A presença de bibliotecas de fingerprint no ProxyBet não significa que
  copiá-las corrigiria um score do Nexora. O backend Python não consome
  diretamente os pacotes JavaScript, e os métodos internos do ProxyBet
  estão protegidos.

A implementação é original e incremental: não é uma cópia 1:1 do ProxyBet.
