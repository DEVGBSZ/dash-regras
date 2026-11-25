# Dashboard de Demandas e Consultas Técnicas

Dashboard em Dash para acompanhamento gerencial de demandas e consultas técnicas do Jira.

## Funcionalidades

- visão geral com Kanban e filtros;
- resultados mensais e anuais;
- alocação por responsáveis e participantes;
- linha do tempo anual com campos recolhíveis;
- detalhes dos tickets e links para o Jira;
- modos claro e escuro;
- sincronização manual dos dados do Jira e da aba `Acompanhamento Cartas` do SharePoint.

## Configuração local

Crie um ambiente virtual, instale as dependências e configure as variáveis descritas em `.env.example` no ambiente do sistema.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\app.py
```

A aplicação fica disponível em `http://127.0.0.1:8060`.

## Dados e segurança

Credenciais, tokens, snapshots do Jira e cache de membros não são versionados. Configure as credenciais como variáveis de ambiente no servidor. Nunca envie esses valores ao repositório.

O snapshot local do Jira é criado por `sync_jira.py`. As cartas são lidas diretamente de
`Z:\GRPC\09.Administrativo\atualização de planilha de demandas GRPC.xlsm` (via o caminho UNC equivalente
`\\AGM\GEREG\GRPC\09.Administrativo\...`). O arquivo é processado em memória e nenhuma cópia local da planilha é criada. A aplicação
persiste somente os registros normalizados da aba `Acompanhamento Cartas`, para que a tela continue disponível
caso uma atualização posterior falhe.

O caminho pode ser alterado por `LETTERS_WORKBOOK_PATH`. Em servidores Linux, o link do OneDrive é usado
quando o compartilhamento de rede não está acessível. No Windows, esse fallback precisa de
`LETTERS_ALLOW_REMOTE_FALLBACK=true`. O cache de registros pode usar
um volume persistente por meio de `SHAREPOINT_CARDS_CACHE_PATH`.

Para links protegidos, o fallback de servidor usa uma aplicação Microsoft Entra com permissão de aplicação
`Files.Read.All`: configure `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_ID` e `MICROSOFT_CLIENT_SECRET`.

No aplicativo local para Windows, também é possível usar a sessão corporativa do módulo Microsoft Graph sem
configurar segredo de aplicação. Execute `autenticar_sharepoint.cmd` uma vez, conclua o login com a conta que
tem acesso à planilha e volte ao dashboard. A sessão fica protegida no perfil do Windows e é reutilizada nas
próximas atualizações.

Se a política do tenant bloquear o aplicativo padrão Microsoft Graph Command Line Tools com `AADSTS50105`, um
administrador deve atribuir o usuário ao aplicativo empresarial e consentir `Files.Read`. Como alternativa,
configure `MICROSOFT_CLIENT_ID` e `MICROSOFT_TENANT_ID` de uma aplicação pública corporativa autorizada antes
de executar o autenticador. Para execução sem usuário em servidor, use as três credenciais de aplicação
descritas acima.

Ao clicar em **Atualizar dados**, o mesmo processo atualiza o Jira, as equipes autorizadas e a aba
`Acompanhamento Cartas`. Se uma fonte falhar, as demais continuam sendo atualizadas e o último conjunto válido
da fonte com falha é preservado.

## Servidor

O objeto WSGI está exposto como `app:server`. O `Procfile` inclui um comando Gunicorn para hospedagem em ambiente Linux.
