# Auditoria de User-Agents móveis enviados

Arquivo original: `reference/__mobile_userAgent.json`

## Resultado no Nexora

A lista enviada contém 180 strings, das quais 142 são únicas (38
repetições), 120 identificam Android/Chrome e 60 Safari de iPhone. As
versões de Chrome declaradas são 139, 140, 141, 142 e 143, com apenas
cinco builds completas.

| Chrome informado | Registros |
|---|---:|
| 139.0.7258.64 | 23 |
| 140.0.7339.41 | 30 |
| 141.0.7390.54 | 27 |
| 142.0.7443.85 | 18 |
| 143.0.7486.42 | 22 |

O preset **Pixel 7** salvo no Nexora, com Playwright 1.57.0,
declara Chrome **143.0.7499.4**. A lista não contém esse build completo.
O preset **Galaxy S24** também usa Chrome 143.0.7499.4, que não está
presente no arquivo.

## O que foi integrado

A lista original foi preservada como *referência*. O módulo
`mobile_ua_catalog.py` analisa e compara o arquivo com o User-Agent
persistido e com o navegador observado no momento de **Diagnóstico**.

Para usar, abra um perfil Chromium mobile em
`http://127.0.0.1:3000`, clique em **Diagnóstico** e consulte
`user_agent_reference_audit`. O relatório apresenta as contagens,
versões, presença ou ausência de correspondência exata e avisos sobre
as limitações dos dados fornecidos.

Nenhum User-Agent da lista é injetado automaticamente. O código não altera
`fingerprint_manager.generate`, o modelo móvel escolhido, a rede,
a criação de contexto Playwright, os cookies ou o `INICIAR.bat`.

## Por que não usar a lista automaticamente?

Um User-Agent é um texto declarativo: não altera o motor Chromium em
execução, o sistema operacional, GPU, `navigator.webdriver`,
Client Hints ou funcionalidades disponíveis. Escolher aleatoriamente
strings Safari/iPhone para Chromium, ou declarar um build de Chrome
incompatível, introduziria divergências verificáveis. As versões
declaradas também envelhecem.

A lista não traz provas de compatibilidade de hardware nem medições
de detectores externos. **Ela não resolve nem garante qualquer
alteração no Bot Detection ou Suspect Score do Fingerprint.com.**

## Validação

`tests/test_mobile_ua_catalog.py` verifica as contagens do arquivo
e que o resultado é estritamente descritivo. O teste do diagnóstico
real em Chromium verifica a nova seção sem modificar o perfil.

A instalação original do Nexora, o modo mobile, os perfis persistentes,
o armazenamento, os navegadores remotos e o localhost são preservados.
