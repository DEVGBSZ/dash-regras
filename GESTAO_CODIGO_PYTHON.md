# Gestão técnica do código — Dashboard de Demandas e Consultas Técnicas

Este é o manual do dashboard novo, publicado a partir do repositório `DEVGBSZ/dash-regras`. Os arquivos deste diretório formam uma aplicação Dash independente do dashboard legado que fica na pasta pai. Não fixe aqui números de tickets, cartas ou responsáveis: eles mudam a cada sincronização.

## Arquitetura e arquivos principais

| Arquivo | Responsabilidade |
| --- | --- |
| `app.py` | Cria a aplicação Dash, expõe `app:server`, monta a tela e liga o botão **Atualizar dados** ao estado da sincronização. |
| `dashboard.py` | Monta as abas, filtros, visualizações, detalhes, exportação Excel e callbacks. Usa cache em memória para resultados de renderização. |
| `sync_jira.py` | Lê os feeds OData de Regras e, quando configurado, Procedimentos; grava `jira_snapshot.duckdb` por troca atômica. |
| `etl.py` | Fornece configuração dos feeds e leitura OData com paginação e tentativas. Também contém rotinas do banco analítico legado; a tela nova usa `fetch_odata_entity()` e `get_feed_configuration()`. |
| `jira_data.py` | Lê o snapshot em modo somente leitura, interpreta histórico e campos Jira, aplica o escopo de equipes e produz os itens usados pela interface. |
| `jira_refresh.py` | Executa a atualização em uma thread, consolida erros parciais e expõe progresso à interface. |
| `team_members.py` | Sincroniza e guarda a lista de equipes Atlassian autorizadas. |
| `sharepoint_data.py` | Lê e normaliza a aba `Acompanhamento Cartas` da planilha oficial; mantém cache apenas dos registros normalizados. |
| `excel_report.py` | Gera a exportação Excel da seleção da interface. |
| `demo_data.py` | Fornece o modo de demonstração, separado dos dados reais. |
| `assets/` | CSS e JavaScript de tema, layout, listas expansíveis, linha do tempo e cartas. |

`AUDITORIA_JIRA.md` detalha os mapeamentos e lacunas dos campos do Jira. `README.md` descreve a configuração inicial e as fontes de cartas.

## Fluxo de dados e sincronização

1. `sync_jira.py` consulta `Issues`, `Comments`, `History`, `Categorias`, `Subtarefas` e `Palavras-chave` dos feeds configurados. Regras usa o endpoint padrão ou `JIRA_REGRAS_FEED_URL`; Procedimentos requer `JIRA_PROCEDIMENTOS_FEED_URL`.
2. O snapshot novo é montado em arquivo temporário e substitui `jira_snapshot.duckdb` somente após a escrita completa. A falta de issues interrompe a troca para preservar a base anterior.
3. `jira_data.get_data()` lê o snapshot, interpreta datas, situação, responsáveis, participantes, andamento e comentários. Se o snapshot novo não existe, há leitura de compatibilidade do `jira.duckdb` da pasta pai.
4. `team_members.py` limita a exibição de nomes ao escopo autorizado. Sem um cache válido de equipes, o dashboard mostra um aviso e não libera os nomes.
5. `sharepoint_data.py` lê a planilha da rede `Z:\GRPC\09.Administrativo\atualização de planilha de demandas GRPC.xlsm` (ou o caminho UNC equivalente). O arquivo é processado em memória. Em Linux, o fallback remoto é habilitado por padrão quando a rede não está disponível; em Windows, exige `LETTERS_ALLOW_REMOTE_FALLBACK=true`. O cache `sharepoint_cards_cache.json` contém registros normalizados, não uma cópia da planilha.
6. O botão **Atualizar dados** chama `jira_refresh.start_refresh()`. A atualização tenta Jira, equipes e cartas em sequência; uma falha parcial aparece no status e as fontes válidas continuam disponíveis. O polling de um segundo só fica ativo enquanto a atualização está em andamento.

O estado da atualização e os caches de renderização ficam na memória do processo. Por isso, o `Procfile` usa um worker Gunicorn. Para múltiplos workers ou instâncias, será necessário compartilhar estado e coordenar a escrita do snapshot.

## Interface atual

As abas principais são **Etapas gerais**, **O que está rolando**, **O que está próximo** e **Resultados**. O painel lateral reúne Consultas na fila, Pendências Aneel, Cartas, tema claro/escuro e sincronização.

Em **O que está rolando**, as colunas Em desenvolvimento, Atrasado e Finalizado aparecem em **Visão geral** (listas expansíveis) ou **Cards**. O seletor **Ordenar por** no cabeçalho dessas colunas oferece **Data de criação** e **Data fim**; Data fim usa a distância do prazo ao momento atual e deixa itens sem prazo por último. O filtro geral **Preferência** oferece Mais recentes, Tipo, Responsável, Complexidade, Progresso e Código do ticket. A opção Prazo regulatório foi removida desse filtro para evitar conflito com a ordenação do quadro.

As outras visualizações incluem **Alocação por pessoa** e **Linha do tempo**. Ao mudar IDs, filtros ou o layout em `dashboard.py`, revise os callbacks e os seletores em `assets/`, especialmente `zzzzzzzzzzz-board-order.css` e `zzzzzzzzzz-kanban-list.css`. O JavaScript `native-rows.js` monta listas grandes no navegador para reduzir o custo da renderização.

## Configuração e execução

Instale `requirements.txt`, configure variáveis de ambiente sem gravar segredos no repositório e execute `python app.py` neste diretório. O servidor local usa a porta `8060`. Em Linux, o `Procfile` executa `gunicorn app:server` na porta fornecida pelo host.

As variáveis de exemplo para cartas e Microsoft Entra estão em `.env.example`. O snapshot Jira pode ser redirecionado por `JIRA_SNAPSHOT_PATH`; o cache de cartas por `SHAREPOINT_CARDS_CACHE_PATH`. O servidor precisa de permissão de escrita nesses destinos e de armazenamento persistente se os dados devem sobreviver a reinicializações. No Windows, `autenticar_sharepoint.cmd` permite usar uma sessão Microsoft Graph autorizada quando necessário.

Arquivos `.env`, tokens, `jira_snapshot.duckdb`, caches de equipes e cartas e credenciais não devem entrar no Git. A sincronização do feed usa configuração de TLS definida em `etl.py`; revise a cadeia de certificados do ambiente antes de alterar esse comportamento.

## Evolução e verificação

1. Ao adicionar um campo, confira a entidade e o histórico do Jira, atualize `jira_data.build_items()` e revise visualizações, detalhes e exportação que o utilizam.
2. Ao mudar uma visualização, teste as quatro abas, filtros, tema claro/escuro, abertura de detalhes e interação em Visão geral e Cards. Preserve os modos real e demonstração.
3. Ao mudar a sincronização, confirme que falhas de Jira, equipes ou cartas não apagam a última base válida; verifique os caminhos persistentes do servidor.
4. Rode `python -m unittest -q test_jira_data test_sharepoint_data` e `python -m py_compile app.py dashboard.py jira_data.py jira_refresh.py sharepoint_data.py`.
5. Antes de publicar, revise `git diff --check`, `Procfile`, dependências, variáveis do host e o commit no branch conectado ao site. Enviar o código ao GitHub confirma o push, mas o status da hospedagem deve ser conferido separadamente.
