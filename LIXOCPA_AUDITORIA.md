# Auditoria do arquivo LIXOCPA (2).zip e integração Nexora

## Identificação real do material

O arquivo enviado contém 13.133 entradas, aproximadamente 205,7 MB
compactados e 818,8 MB descompactados. Seu código executável principal é
`LIXOCPA/LIXOCPA/main.py`, com a classe `MainWindow` e o título
**Multi-Login Modular** (CustomTkinter). Portanto, não é o código legível
do núcleo protegido do aplicativo comercial ProxyBet 2.5.10.

Existem muitas pastas persistentes `__profiles/profile_*` do Chromium.
**Essas pastas são dados de sessões**, não código-fonte para integrar.
O pacote também contém cadastros, informações pessoais e arquivos de
extensões que podem incluir segredos. Nenhum desses dados deve ser publicado
no GitHub ou compartilhado como dependência do Nexora.

## Lógica verificada (arquivos do ZIP)

1. `Settings/Criar_Filha/settings/browser.py` (há cópia análoga na aba
   `Criar_Mae`): gera um `ModeConfig` por modo `desktop`, `celular` ou
   `app`. Usa listas de user-agents e GPUs locais, geralmente com escolha
   aleatória por nova inicialização. Define `viewport`,
   `device_scale_factor`, `is_mobile` e `has_touch`.
2. `Settings/Criar_Filha/settings/utils.py`: consulta os arquivos
   `__mobile_userAgent.json` / `__mobile_vendors.json`; seleciona
   características que procuram corresponder aos modelos Android.
3. `Settings/Criar_Filha/gui_tab.py`, `run_instance()`: chama
   `playwright.chromium.launch_persistent_context` com um diretório
   `__profiles/profile_<idx>`, opções de viewport, toque e escala;
   opcionalmente associa proxy e extensões.
4. O mesmo `gui_tab.py`, `run_all()`: cria uma thread por instância e
   inicia perfis com intervalo configurável.
5. O código mantém posições em
   `settings.json -> window_bounds_by_idx[idx]`; consulta posições
   reais das janelas via CDP (`Browser.getWindowForTarget`), salva bounds
   e viewport separadamente, e restaura a posição na próxima abertura.
6. Há um gateway de proxies Python separado,
   `Settings/local_proxy_gateway.py`, com roteamento por instância. Seu
   comportamento não prova privacidade/anônimato nem ausência de vazamentos.
7. Há scripts que alteram WebGL, propriedades do navegador, eventos de toque
   e comportamento de WebView; também há extensões relacionadas a CAPTCHA.
   Esses componentes são específicos, não um motor nativo Android e não há
   medição reproduzível demonstrando que não acionem antifraude.
8. O ZIP inclui também funções automatizadas relativas a contas, jogos,
   movimentações financeiras e informações pessoais. Esses módulos não
   integram o núcleo essencial de multilogin e não foram copiados.

## Diferenças importantes para o Nexora

| Aspecto | LIXOCPA | Nexora antes dessa integração |
|---|---|---|
| Controle de Chromium | Playwright Python | Playwright Python |
| Modo móvel | Configuração própria de UA/viewport/toque | Presets oficiais Playwright |
| Identidade persistente | Diretório por índice, UA pode mudar entre aberturas | Diretório por ID, preset salvo |
| Janela | Posição/bounds salvos por índice | Organização em grade, sem restauração persistente |
| GPU/canvas | Scripts de sobreposição de propriedades | Valores reais observados no diagnóstico |
| Execução | Threads independentes e funções próprias | Gerenciamento sequencial de sessões |
| Rede | Gateway proxy por índice | Não há integração com gateway do ZIP |
| Suporte ao Android real | Nenhuma prova; Chromium emulado | Chromium emulado |

**Conclusão técnica:** ambos rodam Chromium via Playwright. A existência de
scripts para modificar propriedades e de flags de inicialização no LIXOCPA
não demonstra que o navegador não seja detectado por serviços antifraude.
Da mesma forma, não é correto prometer que copiar esses scripts para o
Nexora deixaria um navegador automatizado equivalente a um Android físico.

## Portado nesta alteração

Foi implementado um módulo independente
`window_layout_manager.py`, inspirado no padrão de persistência
de janelas observado:

- `data/window-layouts.json` salva apenas `left,top,width,height`
  por ID, com escrita atômica e validação.
- O Nexora tenta restaurar os bounds do Chromium quando o perfil for
  reaberto no Windows; o processo de abertura continua funcionando mesmo
  que o gerenciador de janelas esteja indisponível.
- Botão **Salvar posição** por perfil aberto no localhost.
- Ao encerrar um perfil pelo painel, tenta salvar automaticamente
  sua posição antes de salvar cookies e fechar o navegador.
- Ao clicar **Organizar janelas**, registra as posições aplicadas.
- **Não altera** o viewport móvel nem o fingerprint Playwright salvo.
- Não transfere sessões ou dados do ZIP para o Nexora.
- `INICIAR.bat` e o endereço `http://127.0.0.1:3000` permanecem
  inalterados, assim como o frontend remoto.

## Validação e limitações

Os testes automatizados verificam persistência e isolamento dos layouts,
bounds válidos, comandos CDP simulados, proteção contra sobrescrever
arquivos danificados, contrato de API localhost e regressão do Chromium.

O reposicionamento de janelas nativas no monitor físico precisa também ser
testado manualmente no Windows do usuário. A alteração não remove a
conexão de automação Playwright nem garante score de risco específico no
Fingerprint.com.

Não adicionar o ZIP original, diretórios `__profiles`, registros de contas,
CPF/Pix ou chaves ao GitHub.
