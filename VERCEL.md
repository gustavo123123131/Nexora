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
