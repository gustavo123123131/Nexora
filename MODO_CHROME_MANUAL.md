# Chrome manual no localhost

Este modo opcional abre **o Google Chrome instalado**, sem Playwright,
controle remoto, CDP, JavaScript injetado, alterações de fingerprint ou
emulação Android. O usuário navega manualmente. Não foi projetado para
contornar sistemas antifraude e não garante nenhum Suspect Score.

## Uso (Windows)

1. Instale Google Chrome normalmente.
2. Atualize o repositório com `git pull`.
3. Inicie **INICIAR_CHROME_MANUAL.bat** e acesse
   `http://127.0.0.1:3000`.
4. Selecione um perfil e clique **Abrir Chrome manual**.
5. Feche a janela do Chrome manualmente para encerrar. A interface
   passa a identificar a saída do processo na atualização de estado.

O arquivo `INICIAR.bat` continua abrindo o **modo Playwright original**
sem nenhuma alteração.

## Dados e limitações

- Os perfis manuais usam `data/profiles/<id>/chrome-manual`, pasta separada
  das sessões Playwright `data/profiles/<id>`. Seus cookies e logins não são
  migrados automaticamente entre modos.
- Cada perfil é aberto com `--user-data-dir` próprio para isolar dados.
- O seletor de modelo Android continua disponível nos metadados antigos,
  mas **não é aplicado no Chrome manual**.
- Não há inspeção por JavaScript, controles automatizados de página, captura
  de tela ou botão de encerramento forçado. Fechar pelo Chrome protege
  melhor os dados persistentes.
- Depois de fechar o painel localhost, janelas manuais podem permanecer
  abertas até o usuário fechá-las.
- O Nexora identifica o processo que iniciou; se Chrome transferir uma
  janela a outro processo ou se o servidor reiniciar, o status pode não
  representar perfeitamente todas as janelas pré-existentes.
- Este modo usa Chrome **desktop**, não Android real, proxy individual nem
  um navegador automatizado. Não promete que serviços antifraude deixem de
  apontar sinais relacionados à rede, ao sistema ou à navegação.
- Se Chrome estiver em instalação fora do local convencional, defina a
  variável `MULTILOGIN_CHROME_PATH` apontando para o `chrome.exe`.
- Para não perder sessões, mantenha `data/` fora de sincronizações públicas.

## Diagnóstico

O endpoint `/api/profiles/inspect/<id>` informa modo manual,
caminho do armazenamento e limitações, sem fingir que mediu propriedades
via código injetado.
