# Auditoria de fingerprint — Nexora (13/10/2026)

Esta investigação usa o relato do usuário, o código existente e testes
reproduzíveis. Não tivemos acesso à sessão Windows nem a um evento bruto
do Fingerprint.com. Não foi gerado um novo Suspect Score.

## Resultado relatado
Bot, Browser Tampering, Virtual Machine, Developer Tools e Residential
Proxy: Detected. Suspect Score: 49. Incognito, VPN e Privacy Settings:
Not Detected.

## Arquitetura real
O executor runner/worker.py executa Chromium pelo Playwright em contexto
persistente exclusivo por ID (runner/data/profiles/ID). No Windows,
headless=False; cada perfil abre sua janela independente. O preset
Playwright Pixel 7 emula User-Agent, viewport, escala e touch; não troca
o Windows por um Android. O Chromium ainda é conectado ao Playwright
e pode revelar depuração e automação.

O Cloudflare Quick Tunnel transporta comandos autenticados da Vercel ao
executor Windows: NÃO encaminha automaticamente a navegação dos sites
visitados pelo Chromium. O código do launch não configura proxy. Um
sinal Residential Proxy deve ser investigado na rede, SO, roteador,
extensões e reputação do IP; não deve ser atribuído ao Chromium sem provas.

## Correções feitas
1. Idioma: deixou de ser sempre pt-BR. Em Windows, obtém o locale
   verdadeiro do usuário usando GetUserDefaultLocaleName; passa o valor
   ao Playwright para alinhar navigator.language e HTTP Accept-Language.
   Num host POSIX com locale C, usa o padrão en-US do Chromium.
2. Timezone: deixou de ser sempre America/Sao_Paulo; agora segue o
   fuso do sistema. Não há falsificação de geolocalização.
3. Janela: dimensão externa passou a ser calculada com margem acima do
   viewport emulado, em vez de tamanho menor que a área da página.
4. O lançador Windows antigo também recebeu ajustes de idioma, fuso
   e dimensão da janela. Cookies, sessões e isolamento foram preservados.
5. Nenhum stealth plugin, alteração de navigator.webdriver,
   spoofing de plataforma, injeção JavaScript ou manipulação do teste
   Fingerprint foi acrescentado.

## Antes/depois no mesmo Chromium do GitHub Actions (Linux)
Executar: python -m unittest discover -s tests -p test_browser_environment.py -v

O script abre dois contextos Playwright separados numa página HTTP local
com meta viewport e observa as propriedades e cabeçalhos.

Indicador | Antes | Depois
--- | --- | ---
Idioma JS / Accept-Language | pt-BR / pt-BR | en-US / en-US (runner)
Fuso JS | America/Sao_Paulo | UTC (runner)
UA | Android 14 / Pixel 7 / Chrome 143 | Sem alteração
Client Hints (platform/mobile) | Android / true | Sem alteração
navigator.platform | Linux x86_64 | Sem alteração
Viewport | 412 x 839 | Sem alteração
devicePixelRatio | 2.625 | Sem alteração
maxTouchPoints | 1 | Sem alteração
navigator.webdriver | true | true

Isso comprova alinhamento de idioma e fuso ao host sem alterar sinais
intrínsecos da automação, e confirma emulação mobile internamente
consistente nos valores acima. Não prova redução do score 49 nem da
detecção VM/Tampering: o detector usa heurísticas proprietárias e
sinais reais de hardware e rede.

## Verificações ainda necessárias no PC do usuário
- Executar no PowerShell:
  Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,HypervisorPresent
  Observação: HypervisorPresent não prova máquina virtual; pode ser Hyper-V.
- Conferir Configurações > Rede e Internet > Proxy e executar:
  netsh winhttp show proxy
  Isso só cobre WinHTTP; verificar também as configurações do navegador,
  proxy de sistema, antivírus, extensão, roteador, ISP e IP público no
  navegador normal versus Nexora. Não publicar IPs ou dados de contas.
- Verificar chrome://version no navegador real para observar argumentos
  de inicialização/depuração. Playwright pode acionar o alerta DevTools
  sem janela de DevTools aberta.
- Repetir o MESMO teste Fingerprint.com com o mesmo Windows/rede após
  atualizar o executor; comparar evento e Suspect Score. Sem o novo
  resultado, qualquer mudança nesses cinco sinais é desconhecida.

Os backups de cookies de sessão são arquivos locais sensíveis; não devem
ser compartilhados ou enviados ao GitHub. A chave de acesso também deve
ser mantida privada (e rotacionada se divulgada anteriormente).

## Documentação
- https://playwright.dev/python/docs/emulation
- https://playwright.dev/python/docs/api/class-browsertype
- https://fingerprint.com/products/smart-signals/
- https://fingerprint.com/blog/anti-detect-browser-detection/


## Auditoria adicional em Windows GitHub Actions
Pipeline: .github/workflows/nexora-smoke.yml, job windows-browser-audit,
executado com Playwright 1.57 / Chromium 143. O teste passou.

- UA antes/depois: Linux; Android 14; Pixel 7; Chrome/143.
- Client Hints antes/depois: plataforma Android, mobile true.
- navigator.platform antes/depois: **Win32**. É uma diferença real em
  relação ao UA Android; não foi mascarada.
- navigator.webdriver antes/depois: true.
- Viewport 412 x 839, DPR 2.625, touchPoints=1, sem alteração.
- locale/Accept-Language antes: pt-BR / pt-BR.
- locale/Accept-Language depois: en-US / en-US (idioma do Windows de CI).
- timezone antes: America/Sao_Paulo; depois: UTC (Windows de CI).

Esses números pertencem ao runner **Windows do GitHub**, não ao PC do usuário.
Num Windows em português do Brasil e com fuso de São Paulo, por exemplo,
ambos os valores podem permanecer pt-BR/Sao_Paulo após a correção; a
alteração elimina imposições quando o sistema realmente difere.

O Chromium via Playwright continua expondo sinais de automação e não é
equivalente a um aparelho Android real. Não foi observado nem prometido
qualquer novo Suspect Score no Fingerprint.com.
