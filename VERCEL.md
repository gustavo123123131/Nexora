# Nexora — deploy na Vercel

## O que funciona nesta hospedagem

- Interface original em `public/`, pela URL HTTPS da Vercel, sem servidor local.
- Cadastro, edição e exclusão de sites, criação e exclusão de perfis.
- Persistência do **cadastro** em Postgres/Neon (não em disco temporário).
- Login administrativo por senha definida no painel da Vercel; sessão HTTP-only assinada.
- Importação opcional dos sites/perfis do antigo `data/settings.json` via tela de Sites.

**Não funciona apenas na Vercel:** abrir Chromium com janela interativa, gerenciar processos persistentes,
executar Android real, guardar cookies/armazenamento de sites e logar nos sites usando esses perfis.
A API devolve HTTP 501 para iniciar/encerrar navegadores; a interface mostra a indisponibilidade
em vez de inventar uma sessão ativa. Para recuperar essas funções na nuvem, será necessário um
**executor remoto de navegadores** persistente com armazenamento próprio e uma interface de acesso
remoto segura (streaming da janela / navegador remoto). Esse componente não foi implementado.

## Configuração na Vercel — uma vez

1. Faça backup do `data/` **no seu computador**; ele contém dados privados e não deve ser enviado.
2. Vercel > **Add New > Project** > importar `gustavo123123131/Nexora`, branch `main`.
3. **Framework Preset: Flask** (o arquivo `app.py` é a entrada da função); Root Directory: `./`.
   Deixe o build command padrão. A pasta `public/` é entregue pela CDN da Vercel.
4. No projeto, acesse **Storage** > adicione **Neon Postgres** (ou outro PostgreSQL externo).
   Associe ao projeto para criar a variável `DATABASE_URL`.
5. Em **Settings > Environment Variables**, crie:
   - `NEXORA_ACCESS_PASSWORD`: senha forte privada com **12 ou mais caracteres**.
   - `NEXORA_SESSION_SECRET`: string aleatória privada com **32 ou mais caracteres**;
     pode gerar via um gerenciador de senhas. Não reutilize a senha de acesso.
   - `DATABASE_URL`: normalmente criada automaticamente pela integração Neon.
6. Se configurar as variáveis após o primeiro deploy, use **Redeploy**.
7. Acesse sua URL HTTPS, faça login e cadastre sites e perfis. O esquema das duas tabelas
   (`nexora_sites` e `nexora_profiles`) é inicializado automaticamente no primeiro acesso ao banco.

### Importar a configuração antiga, sem copiar cookies

Após logar: **Sites cadastrados > Importar settings.json**. Escolha um backup do arquivo
`data/settings.json` do PC. O sistema importa apenas nomes, URLs e IDs de perfis/sites, de
maneira transacional, sem sobrescrever entradas com IDs existentes. Não envia nem salva pastas
`data/profiles`, cookies ou dados de login. Os logins locais **não migram** para a Vercel.

O arquivo `data/settings.json` já havia sido enviado ao histórico GitHub antes desta alteração.
Ele NÃO é usado como banco remoto e foi excluído do bundle da Vercel via `.vercelignore`.
**Não removemos esse arquivo rastreado neste commit** para não arriscar apagar uma cópia local
existente durante um `git pull`. Depois de fazer backup, remova-o do controle de versão
com `git rm --cached data/settings.json` e faça commit, entendendo que clones antigos devem
preservar seus próprios dados antes de sincronizar. Histórico público anterior pode persistir.
Recomenda-se tornar o repositório privado.

## Execução anterior no Windows (opcional)

`INICIAR.bat` e `server.py` permanecem apenas para compatibilidade com a versão local antiga;
eles usam `requirements-local.txt` e **não são necessários para acessar a Vercel**. A cópia
local não sincroniza automaticamente com o cadastro no Postgres.

## Testes e limites

- `python -m unittest discover -s tests -p test_cloud.py -v`: autenticação/rotas usando store de teste, sem DB externo.
- Validação do GitHub/Vercel em produção requer deploy com variáveis e banco reais.
- Um teste completo de Postgres/Neon e do frontend hospedado só pode ser realizado depois de
  conectar a conta na Vercel. Nunca deixe um deploy público sem configurar a senha.
- Não existe executor de navegador, browser streaming, backup dos cookies ou conversão real
  Android. APIs futuras deverão exigir autenticação e autorização adequadas.
