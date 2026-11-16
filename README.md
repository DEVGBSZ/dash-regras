# Dashboard de Demandas e Consultas Técnicas

Dashboard em Dash para acompanhamento gerencial de demandas e consultas técnicas do Jira.

## Funcionalidades

- visão geral com Kanban e filtros;
- resultados mensais e anuais;
- alocação por responsáveis e participantes;
- linha do tempo anual com campos recolhíveis;
- detalhes dos tickets e links para o Jira;
- modos claro e escuro;
- sincronização manual dos dados do Jira.

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

O snapshot local é criado por `sync_jira.py`. A aplicação preserva a última base válida quando uma atualização falha.

## Servidor

O objeto WSGI está exposto como `app:server`. O `Procfile` inclui um comando Gunicorn para hospedagem em ambiente Linux.
