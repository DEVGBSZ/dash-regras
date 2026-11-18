# Aplicação do Design System CCEE

Referências consultadas em 18/11/2026

- [Cores — nó 2181:5032](https://www.figma.com/proto/ieuzCnh0kFx1HzfXFhavir/Design-System--Legado-?node-id=2181-5032)
- [Botões — nó 2095:4268](https://www.figma.com/proto/ieuzCnh0kFx1HzfXFhavir/Design-System--Legado-?node-id=2095-4268)

| Uso no dashboard | Claro | Escuro |
| --- | --- | --- |
| Identidade e demandas | Blue 500 `#06038D` | Blue 50 `#E1E1F1` em texto, Blue 200 `#8381C6` nos gráficos |
| Consultas técnicas | Verde petróleo `#01665E` | Acqua 500 `#B8DDE1` |
| Atualizar dados | Neon 500 `#00FFFF`, texto Blue 500 | Mesmo par |
| Texto | Gray 500 `#4C4C4C` | Branco |
| Superfície | Branco | Gray 800 `#333333` |
| Fundo | Acqua 50 `#F6FBFB` | Gray 900 `#242424` |
| Sucesso | Green 500 `#2E7D32` | Green 200 `#97BE99` |
| Cartas / Ofícios no gráfico | Acqua 900 `#91C7CD` | Acqua 500 `#B8DDE1` |
| Avisos de prazo | Orange 500 `#D94801` | Orange 200 `#F0A480` |
| PdCs e participantes | Purple 500 `#542788` | Purple 200 `#AA93C4` |
| Regulatório no gráfico | Purple 500 `#542788` | Purple 200 `#AA93C4` |

Os pares de superfície e texto são uma adaptação da paleta documentada ao dashboard. O verde petróleo e os tons acqua distinguem as consultas técnicas sem usar vermelho nos cards e gráficos. As cores de aviso de prazo continuam reservadas aos alertas.

Botões de ação seguem Roboto Regular 14 px, altura mínima de 44 px, largura mínima de 44 px, espaçamento de 10 px e raio de 30 px. Exportação e acesso aos detalhes usam o estilo primário. Tema, navegação e links usam o secundário. Atualização usa o accent. Há estados hover, pressionado, foco por teclado e desabilitado. Cards clicáveis e linhas da tabela preservam sua estrutura de conteúdo.

No modo claro, o primário usa azul com texto branco. No escuro, usa branco com texto azul. A amostra de sucesso na página de botões repete o exemplo vermelho de danger. Para sucesso no dashboard foi seguida a definição verde da página de cores.

O tema está centralizado em `assets/zzzzzzzz-ccee.css`. As cores dos gráficos e suas variantes de contraste estão em `dashboard.py`.
