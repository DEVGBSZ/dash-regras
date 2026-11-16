# Integração da tela principal com Jira

## Consulta realizada em 04/11/2026

Foi consultado o feed Appfire de Regras configurado em `etl.get_feed_configuration()`, incluindo seu catálogo e metadados. A extração isolada contém 678 issues, 570 comentários, 13.716 registros de histórico, 1.068 categorias e 460 vínculos de subtarefas. A entidade Palavras-chave retornou zero registros. O feed de Procedimentos não está configurado.

Os números abaixo descrevem essa extração; não são constantes de negócio. A interface calcula os totais a partir da base e informa a data da consulta em Brasília.

## Escopo e cobertura

O painel conta somente `Registro de Demanda` e `Consulta Técnica`: 126 itens (82 demandas e 44 consultas). Subtarefas, épicos, iniciativas, estudos e cadernos não são contados como demandas adicionais.

- 72 itens abertos: 50 demandas e 22 consultas.
- 51 itens concluídos; 3 cancelados excluídos das entregas.
- 22 itens na fila e 50 em acompanhamento.
- 17 demandas no status `Aguardando Aneel`.
- 25 itens abertos com prazo vencido, dentre 32 com prazo encontrado. Os 40 sem prazo não são classificados como pontuais nem atrasados.

| Informação | Fonte utilizada | Cobertura nos 72 itens abertos |
| --- | --- | --- |
| Chave, título e tipo | Issues | 72 |
| Status atual | History: `Current status? = Y`, `History Status` | 72 |
| Responsável | History: `Current assignee? = Y`, `History Assignee` | 60; 12 sem responsável encontrado |
| Participantes | Última alteração de `Participantes`, `customfield_10068` | 37 com histórico do campo; 35 sem informação |
| P/M/G | Último valor de `Complexidade`, `customfield_10249` | 7; 65 sem classificação |
| Prazo | `duedate`; para consultas, também `Data Prevista SLA`; `Prazo regulatório` ou `Prazo` | 32 |
| Progresso | `Andamento`, `% Progresso`, `% Evolução`, ou proporção explícita de subtarefas encerradas | 26 |
| Último comentário | Comments: texto, autor e data | 23 |
| Cartas / assinaturas | Tipos, títulos e campos disponíveis no feed | Não encontrados registros identificados nem fluxo de assinatura |
| Procedimentos | Segundo feed independente | Não configurado |

O campo `* Responsável` de Issues está vazio na extração, mas o histórico de `assignee` fornece responsáveis reais. Relator e autor de comentário **não** são usados como substitutos de responsável ou participante.

O histórico contém participantes em listas de nomes. Campo explicitamente vazio é diferente de campo sem histórico. Valores removidos não recuperam valores antigos. Valores literais `null` também são tratados como ausentes.

## Regras dos indicadores

- **Fila:** Aberto, To Do, Tarefas pendentes, Backlog, Radar ou Aguardando análise. A tela informa que esse agrupamento não é uma agenda de início.
- **Em acompanhamento:** outros status conhecidos de itens abertos, incluindo análise, desenvolvimento e espera pela Aneel. O cartão mantém o status original do Jira.
- **Prazo vencido:** dia local do prazo anterior ao dia da extração; pode coincidir com a fila. É um recorte dos abertos, não uma categoria adicional a somar. A origem do prazo aparece no cartão/detalhe.
- **Progresso:** usa o último valor válido do campo disponível. Sem percentual, calcula subtarefas encerradas/total apenas quando todos os vínculos estão presentes na extração. O rótulo informa essa fórmula, incluindo canceladas, e esclarece que não representa esforço realizado. Sem dados, mostra aviso em vez de uma barra com zero fictício.
- **Alocação:** cada responsável conta uma vez por item. Cada participante conta uma vez por item e papel. Ao mostrar ambos, um item pode gerar várias alocações. Itens sem responsável aparecem em grupo explícito. Participantes ausentes não recebem nomes inventados.
- **P/M/G:** usa exclusivamente o campo Complexidade com classificação explícita. Não converte prioridade, horas ou story points em esforço. A série `Não informado` preserva os totais.
- **Resultados:** mês da resolução em Brasília; exclui cancelamentos. Ciclo = resolução menos criação, em dias corridos. Datas inválidas não entram na média.
- **Tempo por status:** intervalos de `History Status`/`Status start`/`Status end`, deduplicados e limitados à criação/resolução. Reentradas no mesmo status são somadas por item antes da média. O denominador de cada status é o número de itens que passaram por ele, exibido ao passar o mouse. Lacunas e sobreposições são sinalizadas como cobertura incompleta. Nesta extração, os 51 concluídos têm histórico completo e a soma dos intervalos corresponde ao ciclo.
- **Resultados por esforço:** nenhum dos 51 concluídos tem P/M/G disponível na extração; a tela mostra `Não informado` e o aviso específico, sem inventar uma distribuição.

## Arquivos e atualização

### Modo provisório de apresentação

O botão no topo alterna entre **Mostrar dados fictícios** e **Mostrar dados reais**. O cenário de `demo_data.py` tem 30 itens abertos, seis analistas, quatro pendências Aneel, duas cartas e resultados simulados de setembro/outubro de 2026. Todos os campos estão preenchidos para demonstrar a experiência completa. A tela identifica o modo fictício com um aviso destacado.

A escolha é isolada por página, em memória do navegador: recarregar a página volta aos dados reais. A troca abrange cartões, gráficos, períodos, detalhes e a lateral, preservando o tema claro/escuro. Nenhum dado fictício é gravado na extração do Jira.

- `sync_jira.py`: somente leitura HTTP no Jira e gravação transacional de `prototipo_tela_principal/jira_snapshot.duckdb`.
- `jira_data.py`: leitura local, reconstrução dos campos e regras acima.
- `dashboard.py`: indicadores, cartões, gráficos, detalhes e mensagens de ausência.
- `app.py`: montagem da tela e alternância claro/escuro.
- `test_jira_data.py`: valida ausência de dados, campos apagados, cancelamentos, prazos e intervalos de status.

O banco original `jira.duckdb` e a rotina original do dashboard não são atualizados por essa integração. O novo snapshot está no `.gitignore`. Não são gravadas URLs autenticadas no relatório ou no novo banco.

Na raiz do projeto, atualize com:

```powershell
.\.venv\Scripts\python.exe .\prototipo_tela_principal\sync_jira.py
```

Depois recarregue a página. A leitura usa cache invalidado pela alteração do arquivo. O aplicativo não consulta a rede a cada clique. Se a sincronização de Issues falhar, preserva a base anterior; falhas de entidades complementares são registradas e sinalizadas. Sem snapshot isolado, tenta ler a base local anterior com avisos das informações ausentes.

Para iniciar:

```powershell
.\.venv\Scripts\python.exe .\prototipo_tela_principal\app.py
```

Para verificar as regras:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s prototipo_tela_principal -p test_jira_data.py -v
```
