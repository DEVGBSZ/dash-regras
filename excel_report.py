"""Exportação das seleções do dashboard para Excel."""
from collections import Counter
from datetime import datetime

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from jira_data import LOCAL_ZONE


def write_report(stream, title, items, filters, allocations, stages, processes):
    book = Workbook()
    book.remove(book.active)

    def table(name, headers, widths, rows):
        sheet = book.create_sheet(name)
        sheet.sheet_view.showGridLines = False
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        sheet["A1"] = title + "  |  " + name
        sheet["A1"].fill = PatternFill("solid", fgColor="193455")
        sheet["A1"].font = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
        sheet.row_dimensions[1].height = 32
        sheet.append([])
        sheet.append(headers)
        for col, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(col)].width = width
            cell = sheet.cell(3, col)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="365D84")
        for index, row in enumerate(rows, 4):
            for col, value in enumerate(row, 1):
                cell = sheet.cell(index, col)
                if isinstance(value, datetime):
                    cell.value = value.astimezone(LOCAL_ZONE).replace(tzinfo=None)
                    cell.number_format = "dd/mm/yyyy hh:mm"
                elif isinstance(value, str):
                    cell.value = ILLEGAL_CHARACTERS_RE.sub("", value)
                    cell.data_type = "s"
                else:
                    cell.value = value
                    if isinstance(value, float):
                        cell.number_format = "#,##0.00"
                if index % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor="EDF3FA")
                cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.freeze_panes = "B4"
        sheet.auto_filter.ref = f"A3:{get_column_letter(len(headers))}{sheet.max_row}"
        sheet.print_title_rows = "1:3"
        return sheet

    counts = Counter(i["kind"] for i in items)
    summary = [("Itens selecionados", len(items)), ("Demandas", counts["Demandas"]),
               ("Consultas técnicas", counts["Consultas técnicas"])]
    if title == "Resultados":
        cycles = [i["cycle"] for i in items if i.get("cycle") is not None]
        summary.append(("Ciclo médio (dias)", sum(cycles) / len(cycles) if cycles else None))
    summary.extend(filters)
    cover = table("Resumo", ["Indicador ou filtro", "Valor"], [37, 65], summary)
    for row, color in [(4, "193455"), (5, "315DBF"), (6, "A62D3A")]:
        cover.row_dimensions[row].height = 26
        cover.cell(row, 2).font = Font(size=16, bold=True, color=color)
    stage_counts = Counter((stages[i["id"]], i["kind"]) for i in items)
    table("Etapas", ["Etapa", "Demandas", "Consultas técnicas"], [35, 18, 22],
          [(s, stage_counts[s, "Demandas"], stage_counts[s, "Consultas técnicas"])
           for s in (list(dict.fromkeys(stages.values())) + (["Estudos"] if title == "Etapas gerais" else []))])
    fields = [("Código", "key", 19), ("Título", "title", 58), ("Tipo", "kind", 22),
              ("Status Jira", "status", 24), ("Responsável", "owner", 30),
              ("Participantes", "participants", 42), ("Complexidade", "effort", 16),
              ("Criticidade", "criticality", 16), ("Progresso (%)", "progress", 17),
              ("Criação", "created", 21), ("Início", "start_date", 21),
              ("Prazo regulatório", "regulatory_deadline", 21), ("Entrega", "delivery_date", 21),
              ("Data fim", "end_date", 21), ("Prazo do item", "due", 21),
              ("Resolução", "resolved", 21), ("Ciclo (dias)", "cycle", 17),
              ("Autor do comentário", "author", 28), ("Data do comentário", "comment_date", 21),
              ("Último comentário", "comment", 72), ("Categorias", "categories", 34)]
    def detail(item):
        values = [item.get(key) for _, key, _ in fields]
        return [", ".join(v) if isinstance(v, list) else v for v in values] + [
            stages[item["id"]], processes[item["id"]]]
    table("Itens", [h for h, _, _ in fields] + ["Etapa", "Processo"],
          [w for _, _, w in fields] + [27, 26], map(detail, items))
    if allocations is not None:
        table("Alocações", ["Pessoa", "Papel", "Código", "Título", "Tipo", "Complexidade"],
              [32, 20, 20, 58, 23, 18],
              [(name, role, i["key"], i["title"], i["kind"], i["effort"]) for name, role, i in allocations])
    if title == "Etapas gerais":
        history = Counter((i["created"].astimezone(LOCAL_ZONE).strftime("%Y-%m"), processes[i["id"]]) for i in items)
        table("Histórico", ["Mês de criação", "Processo", "Itens"], [24, 34, 16],
              [(month, process, n) for (month, process), n in sorted(history.items())])
    if title == "Resultados":
        table("Tempo por status", ["Código", "Status", "Dias corridos"], [20, 32, 20],
              [(i["key"], status, days) for i in items for status, days in i["days"].items()])
    book.save(stream)
