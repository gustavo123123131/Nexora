# Importação de recursos Multi-Login do arquivo LIXOCPA (2)(1).zip

## Origem examinada

O ZIP fornecido pelo usuário contém 13.133 entradas, ~819 MB
descompactados. A aplicação original é **Multi-Login Modular**
(`LIXOCPA/LIXOCPA/main.py`), com as interfaces CustomTkinter
“Criar Mãe” e “Criar Filha”. O núcleo de abertura de navegador está
duplicado em:
- `Settings/Criar_Mae/gui_tab.py` e `Settings/Criar_Filha/gui_tab.py`
- `Settings/Criar_Mae/settings/browser.py` e equivalente Filha
- `Settings/Criar_Mae/settings/utils.py` e equivalente Filha

Outros arquivos relevantes ao multilogin:
- `Settings/local_proxy_gateway.py`: gateway de proxy local
- `Settings/mirror_easy.py`: difusão de eventos entre páginas
- `Settings/window_pos_controller.py`: coordenação de posições
- `Settings/speed_controller.py`: configuração de velocidade
- `Settings/Criar_*/settings/settings.json`: parâmetros de inicialização
- `Settings/Criar_*/__profiles/profile_*`: dados do Chromium (não código)

**Não é possível transplantar literalmente todo o arquivo para o Nexora sem
misturar interfaces incompatíveis, dados privados e automações de contas.**
O original usa duas interfaces GUI Python; o Nexora tem painel HTTP/JavaScript.
O original executa Chromium via Playwright; não há Android nativo no ZIP.

## Recursos multilogin já existentes no Nexora

- Diretório Chromium isolado por ID de perfil.
- Cookies persistentes e exclusão controlada.
- Vários modelos Android por catálogo Playwright.
- Abrir/encerrar individualmente.
- Abrir/encerrar vários perfis selecionados.
- Organizar várias janelas na tela.
- Salvar e restaurar posições no Windows.
- Status e limites de sessões locais.
- Fingerprint Inspector sem alterar propriedades da página.

## O que foi acrescentado a partir deste ZIP

### Importar um plano de instâncias

`lixocpa_import.py` implementa uma conversão original baseada no
contrato de configuração, **não copia o launcher original**:

- Importa somente `url`, `mode` e `count` do `settings.json`.
- Aceita os modos LIXOCPA `celular` e `app`.
- Para `app`, usa o Chromium mobile padrão do Nexora: **não emula
  WebView real**, e avisa isso antes de importar.
- Valida URL, modo e número de instâncias; prevê alterações antes de gravar.
- Confirma explicitamente a criação de novos perfis.
- Reaproveita cadastro de site com mesma URL sem apagar os já existentes.
- Perfis novos começam com diretórios e cookies vazios, com ID próprio.
- Não importa senhas, tokens, proxies, contas salvas, CPF, Pix,
  atalhos financeiros, extensões ou sessões persistidas.
- Erros na criação restauram os metadados anteriores.

### Controlar o intervalo de abertura

`MultiLoginController.start_selected` aceita intervalo de **0 a
750 milissegundos** para escalonar a criação dos navegadores e aliviar
picos de CPU/RAM. Não simula cliques, digitação ou uso humano.
Playwright continua na thread dona dos contextos, evitando a
incompatibilidade com threads de `run_all` do projeto original.

### Interface

No localhost `http://127.0.0.1:3000`:
1. Extraia do ZIP um dos arquivos
   `Settings/Criar_Mae/settings/settings.json` ou
   `Settings/Criar_Filha/settings/settings.json`.
2. Em **Perfis**, clique **Importar LIXOCPA** e selecione o JSON.
3. Confira a prévia e confirme quantos novos perfis serão criados.
4. Para abrir vários, marque perfis, defina o intervalo e clique
   **Abrir selecionados**.
5. O `INICIAR.bat` original e os perfis já existentes não mudam.

Importante: **não publique os JSONs de configuração do usuário**. Alguns
possuem informações privadas, credenciais de proxy e configurações
financeiras. O navegador local envia ao servidor apenas os três campos
necessários à importação.

## Componentes não copiados e motivo

| Componente original | Situação |
|---|---|
| Scripts de WebGL, Canvas, webdriver, plugins, fingerprint aleatório | Não copiados. Camuflagem para contornar sistemas antifraude; também introduzem inconsistências |
| Extensão de resolução de CAPTCHA | Não copiada |
| Automação de cadastro, jogos, depósitos/saques e movimentações | Não copiada |
| Registros de contas e perfis Chromium `__profiles` | Não copiados: contém sessões e dados pessoais |
| Gateway de proxy com autenticação e sessões rotativas | Não copiado; arquitetura exige desenho separado e proteção de credenciais |
| Espelhamento de ações entre contas e aceleração de jogos | Não copiados |
| GUI CustomTkinter inteira | Não copiada: Nexora usa frontend web |
| Modo WebView nativo Android | Não fornecido como engine Android real; modo `app` é Playwright Chromium |
| Núcleo comercial ProxyBet criptografado | Não consta em fonte legível no material ZIP |

**A integração não desabilita detecção de bots nem promete reduzir
Suspect Score.** O navegador do Nexora permanece Playwright Chromium
mobile emulado. Copiar scripts de disfarce não equivale a rodar um
dispositivo real nem corrige automaticamente incompatibilidades TLS,
GPU e Client Hints.

## Testes e rollback

`tests/test_lixocpa_import.py` valida prévia, modulação,
não propagação de campos privados, importação sem afetar perfis,
rollback de erro e controle de intervalo. `tests/test_http.py`
valida a confirmação e API localhost com servidor real. CI também
executa testes antigos de Chromium Windows e Linux.

Se precisar desfazer, reverta a pull request no GitHub. Os perfis já
existentes continuam independentes. Dados locais permanecem na
pasta `data/`; faça backup privado antes de atualizar.
