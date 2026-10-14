# Android conectado ao Nexora no localhost

O arquivo `INICIAR_ANDROID_REAL.bat` inicia um terceiro modo **opcional**
do Nexora. Ele usa o navegador real do seu celular Android e mostra a tela
em uma janela scrcpy no Windows. Não usa Playwright no navegador do
celular, não aplica UA falso, não altera JS e não promete score antifraude.

## Requisitos

1. Um **celular Android real** de sua propriedade e cabo USB.
2. [Android SDK Platform Tools (adb)](https://developer.android.com/studio/releases/platform-tools).
3. [scrcpy para Windows](https://github.com/Genymobile/scrcpy/blob/master/doc/windows.md).
4. Depuração USB ativada no próprio telefone. Aceite a solicitação de
   autorização de conexão com este computador.

Instale adb e scrcpy no PATH do Windows, ou configure
`NEXORA_ADB_PATH` e `NEXORA_SCRCPY_PATH` para seus executáveis.

No PowerShell, confirme o acesso:

```powershell
adb devices
scrcpy --version
```

O Android precisa aparecer como `device`, não `unauthorized` ou
`offline`. Use apenas aparelhos sob seu controle.

## Iniciar

1. No Windows, feche a sessão anterior do localhost antes de trocar de modo.
2. Execute `INICIAR_ANDROID_REAL.bat` na pasta atualizada do Nexora.
3. Abra `http://127.0.0.1:3000` e cadastre o site e o perfil como antes.
4. Clique **Abrir no Android**. Com vários aparelhos, escolha qual usar.
5. O Nexora solicita ao Android para abrir o link no navegador padrão
   e inicia uma janela de espelhamento scrcpy. Você usa mouse/teclado
   manualmente na tela do Android ou toca diretamente no celular.
6. Clique **Fechar espelho** para sair do espelhamento. Chrome e cookies
   continuam dentro do Android até você fechá-lo ou limpar seus dados.

## Limitações que importam

- Cada Android conectado pode estar associado a **um perfil Nexora aberto
  por vez**. O Nexora não cria múltiplos dispositivos fictícios nem contas
  Android separadas dentro do mesmo telefone.
- A seleção de preset Pixel/Galaxy armazenada para Playwright **não é
  aplicada** nesse modo; a identidade observável pertence ao aparelho real.
- O dispositivo pode escolher seu navegador padrão. Para usar Chrome,
  configure Chrome como navegador padrão no Android.
- Não existe sincronização, backup, importação nem exportação de cookies
  do celular pelo Nexora.
- O painel não tenta verificar/alterar fingerprints do aparelho.
- A conexão via ADB e a disponibilidade de scrcpy dependem de configuração
  real do seu Windows e telefone. O GitHub CI não tem um aparelho físico
  e só valida a integração com simulações de ADB/scrcpy.
- A operação pode ser afetada por permissão de depuração, drivers USB e
  configurações de segurança do aparelho. ADB deve ser usado apenas em
  dispositivos autorizados.
- Um emulador Android no PC continua sendo um ambiente virtualizado;
  não é equivalente a telefone físico.
- Nada garante que serviços antifraude classifiquem a sessão como confiável.
  O Nexora não contorna verificações de segurança de sites.

## Preservação do modo antigo

`INICIAR.bat` continua iniciando **Playwright Chromium mobile**.
`INICIAR_CHROME_MANUAL.bat` continua iniciando **Chrome desktop normal**.

O Android conectado é um terceiro modo separado. Alterações feitas no
Android não sobrescrevem dados do Chromium local em `data/profiles`.
