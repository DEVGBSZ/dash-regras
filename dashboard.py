"""Visão gerencial baseada na extração real do Jira, com lacunas explícitas."""

from collections import Counter, defaultdict
from math import ceil
from statistics import mean
from datetime import datetime, timedelta
from calendar import monthrange
from functools import lru_cache

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from jira_data import LOCAL_ZONE, date_label, normal
from demo_data import get_dataset

COLORS = {"Demandas": "#4478f0", "Consultas técnicas": "#ed9a50",
          "P": "#36af80", "M": "#4478f0", "G": "#8c6de7", "Não informado": "#808080",
          "Responsável": "#4478f0", "Participante": "#8c6de7"}
NO_OWNER = "Responsável não encontrado"
JIRA_BASE_URL = "https://centraldeservicosccee.atlassian.net"


def icon(name):
    return html.I(className=f"fa-solid {name}", **{"aria-hidden": "true"})


def badge(text, tone="neutral"):
    return html.Span(text, className=f"mini-badge mini-badge--{tone}")


def missing(subject, reason=None):
    return html.Div([icon("fa-circle-info"), html.Span(f"{subject}: dados necessários não encontrados."),
                     html.Small(reason) if reason else None], className="data-missing")


def metric(value, label, detail=None):
    return html.Div([html.Strong("—" if value is None else str(value)), html.Span(label),
                     html.Small(detail) if detail else None], className="metric")


def active_items(data):
    return [item for item in data["items"] if not item["closed"]]


def successful_items(data):
    return [item for item in data["items"] if item["closed"] and not item["cancelled"]]


def result_items_for_range(data, period):
    """Itens concluídos dentro de um intervalo relativo à data da extração."""
    items = successful_items(data)
    if period == "all":
        return items
    anchor = data.get("synced_at") or max((item["resolved"] for item in items if item["resolved"]), default=datetime.now(LOCAL_ZONE))
    if period == "year":
        cutoff = anchor.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        months = {"6m": 6, "3m": 3, "1m": 1}.get(period, 12)
        month_index = anchor.year * 12 + anchor.month - 1 - months
        year, month = divmod(month_index, 12)
        cutoff = anchor.replace(year=year, month=month + 1, day=min(anchor.day, monthrange(year, month + 1)[1]))
    return [item for item in items if item["resolved"] and cutoff <= item["resolved"] <= anchor]


def filtered_data(data, kind, owner="all", order="created"):
    items = [item for item in data["items"] if (kind == "all" or item["kind"] == kind) and (owner == "all" or (item["owner"] or NO_OWNER) == owner)]
    return {**data, "items": items, "selected_kind": kind, "sort": order}


def ordered_items(items, order):
    def key(item):
        if order == "key":
            return int(item["key"].split("-")[-1])
        if order == "effort":
            return {"P":0, "M":1, "G":2}.get(item["effort"], 3)
        if order in ("kind", "owner"):
            return (not bool(item[order]), item[order] or "")
        if order == "progress":
            return (item["progress"] is None, -(item["progress"] or 0))
        value = item.get("regulatory_deadline") if order == "regulatory_deadline" else item["created"]
        return (value is None, value.timestamp() * (1 if order == "regulatory_deadline" else -1) if value else 0)
    return sorted(items, key=key)


def source_info(data):
    if data.get("demo"):
        return html.Div([
            html.Strong("Cenário de apresentação — todos os dados desta visão são fictícios."),
            html.P("Exemplo completo com demandas, PdC, consultas técnicas, alocação, cartas e resultados. Use o botão acima para voltar aos dados reais do Jira."),
        ], className="demo-notice")
    stamp = data["synced_at"].astimezone(LOCAL_ZONE).strftime("%d/%m/%Y às %H:%M") if data["synced_at"] else "data não encontrada"
    notices = [html.P(f"Fonte: {data['source']} · consulta em {stamp} (Brasília).", className="source-line"),
               html.P(f"Escopo: {len(data['items'])} demandas e consultas técnicas de {data['raw_count']} itens disponíveis. Épicos, cadernos e subtarefas não entram nos totais de demandas.", className="chart-note")]
    if data.get("team_scope", {}).get("configured"):
        notices.append(html.P(
            f"Pessoas: {data['team_scope']['members']} membros sincronizados da equipe configurada da área.",
            className="chart-note",
        ))
    if data["feeds"].get("procedimentos", {}).get("state") == "not_configured":
        notices.append(missing("Procedimentos de Comercialização", "Feed de Procedimentos não configurado. Os totais exibidos cobrem somente o feed de demandas."))
    notices.extend(missing("Fonte Jira", message) for message in data["errors"])
    return html.Div(notices, className="source-info")


def compact_item(item, scope=""):
    tone = "orange" if item["kind"] == "Consultas técnicas" else "blue" if item["topic"] == "Regras" else "purple"
    progress = item["progress"]
    return html.Article([
        html.Div([badge("Consulta Técnica" if item["kind"] == "Consultas técnicas" else "Demanda" if item["topic"] == "Regras" else item["topic"], tone),
                  badge(f"Complexidade {item['effort']}", item["effort"]) if item["effort"] else badge("P/M/G não encontrado")], className="compact-meta"),
        html.H3(item["title"], title=item["title"]),
        html.Div([html.Span(item["status"] or "Status não encontrado"),
                  badge("Prazo vencido", "orange") if item["overdue"] else None], className="compact-progress-label"),
        html.Div([
            html.Div([html.Span("Progresso"), html.Strong(f"{progress:g}%")], className="compact-progress-label"),
            html.Div(html.Div(style={"width": f"{progress}%", "background": COLORS[item["kind"]]}),
                     className="compact-progress", role="progressbar", title=item["progress_source"],
                     **{"aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": progress, "aria-label": f"Progresso: {item['title']}"}),
            html.Small(item["progress_source"], className="progress-source"),
        ]) if progress is not None else missing("Progresso"),
        html.Div([icon("fa-user"), html.Strong(item["author"] or "Autor não encontrado"), html.Span(item["comment"])],
                 className="compact-comment", title=f"{item['author'] or 'Autor não encontrado'}: {item['comment']}") if item["comment"] else missing("Último comentário"),
        html.Div([html.Span(f"{item['key']} · {item['owner'] or NO_OWNER}"),
                  html.Span(f"{item['due_source'] or 'Prazo'}: {date_label(item['due'])}")], className="compact-footer"),
        html.Button("Ver detalhes", id={"type": "issue-button", "key": f"{scope}:{item['id']}" if scope else item["id"]}, n_clicks=0, className="item-detail-button"),
    ], className="compact-item real-item")


def item_list(items):
    if not items:
        return html.P("Nenhum item encontrado para esta seleção.", className="empty-state")
    pages = [items[start:start + 3] for start in range(0, len(items), 3)]
    if len(pages) == 1:
        return html.Div([compact_item(item) for item in pages[0]], className="compact-grid")
    return dcc.Tabs(value="0", className="item-pages", children=[
        dcc.Tab(label=f"{index * 3 + 1}–{index * 3 + len(page)}", value=str(index),
                className="item-page", selected_className="item-page--selected",
                children=html.Div([compact_item(item) for item in page], className="compact-grid"))
        for index, page in enumerate(pages)
    ])


def kanban_card(item, scope):
    return html.Button([
        html.Div([html.Span(item["key"], className="kanban-ticket-key"),
                  badge("Consulta Técnica" if item["kind"] == "Consultas técnicas" else "Demanda", "blue")], className="kanban-ticket-meta"),
        html.Span(item["title"], className="kanban-ticket-title"),
        html.Div([badge("Complexidade " + (item["effort"] or "—"), item["effort"] or "neutral"), html.Span(f"{item['progress']:g}%" if item["progress"] is not None else "Progresso não informado")], className="kanban-ticket-meta"),
        html.Div([icon("fa-user"), html.Span(item["owner"] or NO_OWNER)], className="kanban-ticket-owner"),
        html.Div([html.Span(item["status"] or "Status não encontrado"),
                  html.Span("Regulatório: " + date_label(item.get("regulatory_deadline"))) if item["kind"] == "Demandas" else html.Span("Data fim: " + date_label(item.get("end_date")))], className="kanban-ticket-footer"),
    ], id={"type": "issue-button", "key": f"{scope}:{item['id']}"}, n_clicks=0, className="kanban-ticket", title="Abrir detalhes: " + item["title"])


def kanban_items(data, lane):
    scope, tone = lane.split(":", 1)
    active = [item for item in active_items(data) if item["queue"] == (scope == "upcoming")]
    if tone == "finished":
        return successful_items(data)
    return [item for item in active if bool(item["overdue"]) == (tone == "late")]


def search_kanban(items, query):
    term = normal(query).strip()
    return [item for item in items if not term or any(term in normal(value) for value in (item["title"], item["key"], item["comment"]))]


def kanban_board(data, upcoming=False, query=""):
    scope = "upcoming" if upcoming else "ongoing"
    lanes = [("Na fila" if upcoming else "Em desenvolvimento", "development"),
             ("Atrasado", "late"), ("Finalizado", "finished")]
    columns = []
    for title, tone in lanes:
        lane = f"{scope}:{tone}"
        items = search_kanban(kanban_items(data, lane), query)
        if query and not items:
            continue
        items = ordered_items(items, data.get("sort", "created"))
        cards = html.Div([kanban_card(item, scope) for item in items], className="kanban-cards") if items else html.P("Nenhum item nesta etapa.", className="empty-state")
        columns.append(html.Section([
            html.Div([html.Button(title, id={"type": "lane-open", "lane": lane}, n_clicks=0, className="lane-open"), html.Span(str(len(items)), className="kanban-count")], className="kanban-heading"),
            html.Div(cards, id={"type": "kanban-cards", "lane": lane}, className="kanban-card-area", tabIndex=0, **{"aria-label": title}),
        ], className=f"kanban-column kanban-column--{tone}"))
    return html.Div([
        html.Div([html.H2("O que está próximo" if upcoming else "O que está rolando", className="section-title"),
                  html.Span("Situação atual dos itens no Jira", className="muted")], className="panel-heading"),
        html.Div(columns if columns else [html.P("Nenhum item corresponde à busca.", className="empty-state")], className="kanban-board"),
    ], className="kanban-view")


def activity_panel(data, upcoming=False, query=""):
    if not upcoming:
        return kanban_board(data, query=query)
    active = active_items(data)
    items = search_kanban([item for item in active if item["queue"]], query)
    items = ordered_items(items, data.get("sort", "created"))
    technical = [item for item in active if item["kind"] == "Consultas técnicas"]
    known_status = [item for item in active if item["status"]]
    missing_due = sum(item["due"] is None for item in active)
    has_source = bool(data["items"]) or (not data["errors"] and bool(data["feeds"]))
    technical_status_known = any(i["status"] for i in technical) or (not technical and has_source)
    return html.Div([
        html.Div([
            metric(len(active) if has_source else None, "Itens abertos", data.get("selected_kind", "Demandas + consultas")),
            metric(sum(not item["queue"] for item in known_status) if known_status else None, "Em acompanhamento", "Execução, análise ou espera"),
            metric(sum(item["queue"] for item in known_status) if known_status else None, "Na fila", "Aberto, Backlog ou Radar"),
            metric(sum(bool(item["overdue"]) for item in active) if len(active) > missing_due else None, "Prazo vencido", f"{missing_due} itens sem prazo encontrado"),
        ], className="metrics-row"),
        html.Div([html.H2("O que está próximo" if upcoming else "O que está rolando", className="section-title"),
                  html.Span(f"{len(items)} itens", className="muted")], className="panel-heading"),
        item_list(items),
        html.Div([
            html.Strong([icon("fa-magnifying-glass"), " Consulta Técnica"]),
            *[html.Span([html.B(str(value) if value is not None else "—"), f" {label}"], className=f"technical-chip technical-chip--{tone}")
              for label, value, tone in [
                  ("Fila", sum(i["queue"] for i in technical if i["status"]) if technical_status_known else None, "blue"),
                  ("Em acompanhamento", sum(not i["queue"] for i in technical if i["status"]) if technical_status_known else None, "green"),
                  ("Prazo vencido", sum(bool(i["overdue"]) for i in technical) if any(i["due"] for i in technical) else None, "orange")]],
        ], className="technical-strip") if technical else None,
        missing("Status das consultas técnicas", "O histórico necessário não está disponível.") if not technical_status_known else None,
        missing("Prazos de consultas técnicas", f"{sum(i['due'] is None for i in technical)} consultas abertas sem prazo; não é possível verificar atraso nesses casos.") if any(i["due"] is None for i in technical) else None,
    ])


def base_figure(height=250, theme="light"):
    dark = theme == "dark"
    fig = go.Figure()
    fig.update_layout(template="plotly_dark" if dark else "plotly_white", height=height,
                      margin=dict(l=45, r=15, t=35, b=35),
                      font=dict(family="Arial, sans-serif", size=11, color="#b5b5b5" if dark else "#68748b"),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=1.2, x=0, traceorder="normal"), bargap=.4)
    fig.update_xaxes(gridcolor="#2b2b2b" if dark else "#edf0f5", zeroline=False)
    fig.update_yaxes(gridcolor="#2b2b2b" if dark else "#edf0f5", zeroline=False)
    return fig


def assignments(data, role, items=None):
    result = []
    for item in (active_items(data) if items is None else items):
        if role in ("owner", "all"):
            result.append((item["owner"] or NO_OWNER, "Responsável", item))
        if role in ("participant", "all"):
            result.extend((person, "Participante", item) for person in item["participants"])
    return result


def allocation_view(data, mode="kind", role="owner", theme="light", items=None):
    rows = assignments(data, role, items)
    people = sorted({person for person, _, _ in rows}, key=lambda name: (name == NO_OWNER, name))
    categories = {"kind": ["Demandas", "Consultas técnicas"], "effort": ["P", "M", "G", "Não informado"],
                  "role": ["Responsável", "Participante"]}[mode]
    fig = base_figure(theme=theme)
    for category in categories:
        values = [sum(person == name and (assigned_role if mode == "role" else item[mode] or "Não informado") == category
                      for person, assigned_role, item in rows) for name in people]
        fig.add_bar(name=category, x=people, y=values, marker_color=COLORS[category], text=[v or "" for v in values], textposition="inside",
                    hovertemplate="%{x}<br>" + category + ": %{y}<extra></extra>")
    fig.update_layout(barmode="stack", clickmode="event", uirevision=f"{mode}-{role}")
    max_total = max(Counter(person for person, _, _ in rows).values(), default=0)
    fig.update_yaxes(title="Nº de alocações" if role == "all" else "Nº de itens", rangemode="tozero", dtick=max(1, ceil(max_total / 6)))
    fig.update_xaxes(showticklabels=False, fixedrange=True)
    if not rows:
        fig.add_annotation(text="Nenhuma alocação encontrada para os filtros selecionados", x=.5, y=.5,
                           xref="paper", yref="paper", showarrow=False, font={"size": 14, "color": "#8b94a5"})
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
    buttons = [html.Button(name, id={"type": "person-button", "name": name}, n_clicks=0,
                           title=f"Ver detalhes de {name}") for name in people]
    style = {"gridTemplateColumns": f"repeat({max(len(people), 1)}, minmax(0, 1fr))"}
    active = active_items(data) if items is None else items
    notices = [html.P("Responsáveis: assignee atual do histórico Jira. Participantes: último valor do campo Participantes. Cada pessoa conta uma vez por papel e item; o total de alocações pode superar o de itens.", className="chart-note")]
    if data.get("demo"):
        notices = [html.P("Alocação demonstrativa. Clique no nome ou na coluna para ver os detalhes. Demandas e consultas são empilhadas por pessoa; o filtro permite comparar complexidade e papel na atividade.", className="chart-note")]
    if len(people) > 10:
        notices.insert(0, html.P(f"{len(people)} pessoas/grupos na seleção. Role o gráfico na horizontal para ver todos; clique no nome ou na coluna para abrir os detalhes.", className="chart-note"))
    if not rows:
        notices.append(missing("Alocação", "Não foram encontrados nomes para a seleção atual."))
    for field, title in [("owner", "Responsável"), ("effort", "Classificação P/M/G")]:
        count = sum(not i[field] for i in active)
        if count:
            notices.append(missing(title, f"{count} de {len(active)} itens selecionados sem esse dado. Nenhum valor foi estimado."))
    count = sum(not i["participants_known"] for i in active)
    if count:
        notices.append(missing("Participantes", f"Histórico do campo não encontrado em {count} de {len(active)} itens selecionados. Autores de comentários e relatores não são tratados como participantes."))
    return fig, buttons, style, {"minWidth": f"{max(550, len(people) * 95)}px"}, notices


def details_table(rows, kind):
    demand = kind == "Demandas"
    date_headers = ["Prazo regulatório", "Data de entrega"] if demand else ["Data fim"]
    return html.Div(html.Table([
        html.Thead(html.Tr([html.Th(label) for label in ["Item", "Papel", "P/M/G", "Status", *date_headers]])),
        html.Tbody([html.Tr([
            html.Td([html.Button(item["title"], id={"type": "issue-button", "key": f"allocation:{'owner' if role == 'Responsável' else 'participant'}:{item['id']}"}, n_clicks=0, className="allocation-item-link"), html.Small(f"{item['key']} · {item['kind']} · {item['owner'] or NO_OWNER}")]),
            html.Td(badge(role, "blue" if role == "Responsável" else "purple")),
            html.Td(badge(item["effort"], item["effort"]) if item["effort"] else "Não encontrado"),
            html.Td(item["status"] or "Não encontrado"),
            *([html.Td(date_label(item.get("regulatory_deadline"))), html.Td(date_label(item.get("delivery_date")))]
              if demand else [html.Td(date_label(item.get("end_date")))]),
        ]) for role, item in rows]),
    ], className="detail-table"), className="table-scroll")


def person_details(data, name, role, items=None):
    rows = [(assigned_role, item) for person, assigned_role, item in assignments(data, role, items) if person == name]
    effort = Counter(item["effort"] for _, item in rows)
    return html.Div([
        html.Div([metric(len(rows), "Alocações selecionadas"), *[metric(effort[size], f"Complexidade {size}") for size in "PMG"]], className="metrics-row"),
        missing("P/M/G", f"{effort[None]} alocações sem classificação encontrada.") if effort[None] else None,
        *[html.Div([html.H3(kind, className="chart-title"), details_table([row for row in rows if row[1]["kind"] == kind], kind)]) for kind in ("Demandas", "Consultas técnicas") if any(row[1]["kind"] == kind for row in rows)],
    ])


def issue_details(item):
    def tile(label, value, icon_name, tone="blue", detail=None):
        return html.Div([
            html.Div(icon(icon_name), className=f"issue-detail-icon issue-detail-icon--{tone}"),
            html.Div([html.Span(label, className="issue-detail-label"),
                      html.Strong(value, className="issue-detail-value"),
                      html.Small(detail, className="issue-detail-hint") if detail else None]),
        ], className="issue-detail-tile")

    owner = item["owner"] or NO_OWNER
    initials = "".join(part[0] for part in owner.split()[:2]).upper() if item["owner"] else "—"
    owner_mark = html.Span(initials, className="issue-owner-mark", **{"aria-hidden": "true"})
    participants = item["participants"]
    status_tone = "green" if item["closed"] and not item["cancelled"] else "orange" if item["overdue"] else "blue"
    dates = ([tile("Prazo regulatório", date_label(item.get("regulatory_deadline")), "fa-scale-balanced", "purple"),
              tile("Data de entrega", date_label(item.get("delivery_date")), "fa-calendar-check", "orange")]
             if item["kind"] == "Demandas" else
             [tile("Data fim", date_label(item.get("end_date")), "fa-calendar-check", "orange")])
    progress = item["progress"]
    return html.Div([
        html.Div([
            html.Div([html.Span(item["key"], className="issue-key"),
                      html.A(["Abrir no Jira ", icon("fa-arrow-up-right-from-square")], href=f"{JIRA_BASE_URL}/browse/{item['key']}", target="_blank", rel="noopener noreferrer", className="issue-jira-link") if not item["id"].startswith("demo:") else None,
                      badge("Consulta Técnica" if item["kind"] == "Consultas técnicas" else "Demanda", "orange" if item["kind"] == "Consultas técnicas" else "blue"),
                      html.Span(item["status"] or "Status não encontrado", className=f"issue-status issue-status--{status_tone}")], className="issue-detail-tags"),
            html.Div([owner_mark, html.Div([
                html.Span("RESPONSÁVEL", className="issue-detail-label"),
                html.H3(owner, className="issue-owner-name"),
                html.Div([html.Span("Participantes: "),
                          *([html.Span(person, className="issue-participant") for person in participants]
                            if participants else [html.Span("Nenhum informado" if item["participants_known"] else "Dados não encontrados")])], className="issue-participants"),
            ])], className="issue-owner-row"),
        ], className="issue-detail-hero"),
        html.Div([
            tile("Complexidade P/M/G", item["effort"] or "Não informado", "fa-layer-group", "purple"),
            tile("Criado em", date_label(item["created"]), "fa-calendar-plus"),
            *dates,
        ], className="issue-detail-grid"),
        html.Div([
            html.Div([html.Span("PROGRESSO", className="issue-detail-label"),
                      html.Strong(f"{progress:g}%" if progress is not None else "Não informado")], className="issue-progress-heading"),
            html.Div(html.Div(style={"width": f"{progress}%" if progress is not None else "0%"}), className="issue-progress-track"),
            html.Small(item["progress_source"] or "Dados necessários não encontrados", className="issue-detail-hint"),
        ], className="issue-progress-card"),
        html.Section([
            html.Div([html.Div(icon("fa-comment-dots"), className="issue-comment-icon"),
                      html.Div([html.H3("Último comentário"),
                                html.Span(f"{item['author'] or 'Autor não encontrado'} · {date_label(item['comment_date'])}" if item["comment"] else "Sem comentário disponível")])], className="issue-comment-heading"),
            html.P(item["comment"], className="issue-comment-text") if item["comment"] else html.P("Dados necessários não encontrados no Jira.", className="issue-comment-empty"),
        ], className="issue-comment-card"),
    ], className="issue-detail-dashboard")


def periods(data):
    return sorted({i["month"] for i in successful_items(data) if i["month"]}, reverse=True)


def result_period_options(data):
    months = periods(data)
    years = sorted({month[:4] for month in months}, reverse=True)
    return ([{"label": f"Ano completo — {year}", "value": f"year:{year}"} for year in years] +
            [{"label": f"{month[5:]}/{month[:4]}", "value": month} for month in months])


def result_items_for_period(data, period):
    items = successful_items(data)
    if not period:
        return []
    if str(period).startswith("year:"):
        year = str(period).split(":", 1)[1]
        return [item for item in items if item["month"] and item["month"].startswith(year + "-")]
    return [item for item in items if item["month"] == period]


def results_content(data, period, theme="light"):
    items = result_items_for_period(data, period)
    if not items:
        return missing("Resultados do período", "Não foram encontrados itens concluídos com data de resolução para este período.")
    counts = Counter(item["kind"] for item in items)
    cycles = [i["cycle"] for i in items if i["cycle"] is not None]
    with_effort = [i for i in items if i["effort"]]
    effort = base_figure(theme=theme)
    for kind in ["Demandas", "Consultas técnicas"]:
        values = [sum(item["kind"] == kind and (item["effort"] or "Não informado") == size for item in items) for size in ["P", "M", "G", "Não informado"]]
        effort.add_bar(x=["P", "M", "G", "Não informado"], y=values, name=kind,
                       marker_color=COLORS[kind], text=[value or "" for value in values], textposition="inside")
    # Barras agrupadas mantêm os dois tipos visíveis mesmo quando todos os
    # itens caem na mesma categoria (por exemplo, "Não informado").
    effort.update_layout(barmode="group", bargap=.28, bargroupgap=.08)
    effort.update_yaxes(title="Itens concluídos", dtick=1)
    measured = defaultdict(list)
    for item in items:
        for status, days in item["days"].items():
            measured[status].append(days)
    time = base_figure(theme=theme, height=max(250, 38 * len(measured)))
    if measured:
        labels = sorted(measured, key=lambda s: mean(measured[s]))
        time.add_bar(y=labels, x=[mean(measured[s]) for s in labels], orientation="h", marker_color="#8c6de7",
                     customdata=[len(measured[s]) for s in labels], text=[f"{mean(measured[s]):.1f} d".replace(".", ",") for s in labels], textposition="auto",
                     hovertemplate="%{y}: %{x:.1f} dias<br>%{customdata} itens com esse status<extra></extra>")
        time.update_layout(margin=dict(l=130, r=15, t=20, b=40))
        time.update_yaxes(automargin=True)
        time.update_xaxes(title="Dias corridos", rangemode="tozero")
    return html.Div([
        html.Div([metric(len(items), "Itens concluídos"), metric(counts["Demandas"], "Demandas concluídas"),
                  metric(counts["Consultas técnicas"], "Consultas concluídas"),
                  metric(f"{mean(cycles):.1f} dias".replace(".", ",") if cycles else None, "Tempo médio de ciclo", f"Criação → resolução · {len(cycles)}/{len(items)} itens")], className="metrics-row"),
        html.Div([
            html.Div([html.H3("Entregas por complexidade", className="chart-title"),
                      missing("P/M/G das entregas", f"Classificação não encontrada em {len(items) - len(with_effort)} de {len(items)} itens; exibidos como Não informado.") if len(with_effort) != len(items) else None,
                      dcc.Graph(figure=effort, responsive=True, style={"height": "250px", "width": "100%"}, config={"displayModeBar": False})]),
            html.Div([html.H3("Tempo médio em cada status", className="chart-title"),
                      dcc.Graph(figure=time, responsive=True, style={"height": f"{max(250, 38 * len(measured))}px", "width": "100%"}, config={"displayModeBar": False}) if measured else missing("Tempo em cada status", "Histórico de transições não encontrado."),
                      html.P(f"Histórico completo: {sum(i['complete_history'] for i in items)}/{len(items)} itens. Média por item que passou pelo status; retornos à mesma etapa são somados. Intervalos limitados à resolução.", className="chart-note")]),
        ], className="results-grid"),
        html.P("Período definido pela data de resolução. Cancelamentos não entram nas entregas. P/M/G vem do campo Complexidade; não é estimado a partir de prioridade ou story points.", className="chart-note"),
        missing("Datas de resolução", f"{sum(i['month'] is None for i in successful_items(data))} itens concluídos não puderam ser vinculados a um mês.") if any(i["month"] is None for i in successful_items(data)) else None,
    ])


def sidebar_layout(data):
    pending = [item for item in active_items(data) if normal(item["status"]) == "aguardando aneel"]
    pending_section = html.Section([
        html.P("ACOMPANHAMENTO", className="section-kicker"), html.H2("Pendências Aneel", className="section-title"),
        html.Div([html.Div(str(len(pending)), className="pending-count"), html.Div([html.Strong("Aguardando Aneel"), html.P("Cenário demonstrativo" if data.get("demo") else "Status atual encontrado no Jira")])], className="pending-summary") if any(i["status"] for i in data["items"]) else missing("Pendências Aneel"),
        html.Ul([html.Li([html.Strong(item["title"]), html.Small(f"{item['key']} · {item['owner'] or NO_OWNER}"),
                          html.Button("Ver detalhes", id={"type": "issue-button", "key": "pending:" + item["id"]}, n_clicks=0, className="item-detail-button")], className="real-pending") for item in pending[:3]], className="pending-list"),
        html.Button(f"Ver todas as {len(pending)} pendências", id={"type": "sidebar-open", "view": "pending"}, n_clicks=0, className="sidebar-open-button"),
    ], className="surface side-card pending-card")
    cards_section = html.Section([html.P("AÇÕES EM DESTAQUE", className="section-kicker"), html.H2("Cartas", className="section-title"),
                  *[html.Article([
                      html.Div(icon(letter["icon"]), className=f"action-icon action-icon--{letter['tone']}"),
                      html.Div([badge(letter["status"], letter["tone"]), html.H3(letter["title"]), html.P(letter["description"])]),
                  ], className="action-card") for letter in data.get("letters", [])[:2]],
                  html.Button("Ver todas as cartas", id={"type": "sidebar-open", "view": "cards"}, n_clicks=0, className="sidebar-open-button"),
                  missing("Cartas e assinaturas", "Não foram encontrados registros identificados como cartas/ofícios nem um fluxo de assinatura nos dados disponíveis do Jira.") if not data.get("letters") else None], className="surface side-card cards-section")
    unassigned = [i for i in active_items(data) if i["kind"] == "Consultas técnicas" and not i["owner"]]
    queue_section = html.Section([
        html.H2("Consultas sem responsável", className="section-title"), html.P(f"{len(unassigned)} consultas aguardando atribuição"),
        *[kanban_card(i, "pending") for i in unassigned[:2]],
        html.Button("Ver todas as consultas", id={"type":"sidebar-open","view":"unassigned"}, n_clicks=0, className="sidebar-open-button"),
    ], className="surface side-card")
    return dcc.Tabs(id="sidebar-tabs", value="unassigned", className="sidebar-tabs", children=[
        dcc.Tab(label="Consultas na fila", value="unassigned", className="sidebar-tab", selected_className="sidebar-tab--selected", children=queue_section),
        dcc.Tab(label="Pendências Aneel", value="pending", className="sidebar-tab", selected_className="sidebar-tab--selected", children=pending_section),
        dcc.Tab(label="Cartas", value="cards", className="sidebar-tab", selected_className="sidebar-tab--selected", children=cards_section),
    ])


def sidebar_window(data, view):
    if view == "unassigned":
        items = [i for i in active_items(data) if i["kind"] == "Consultas técnicas" and not i["owner"]]
        return html.Div([kanban_card(i, "list") for i in items], className="sidebar-window-grid") if items else html.P("Nenhuma consulta sem responsável.")
    if view == "pending":
        items = [item for item in active_items(data) if normal(item["status"]) == "aguardando aneel"]
        return html.Div([
            html.P(f"{len(items)} pendências · Clique no título para abrir os detalhes.", className="muted"),
            html.Div([kanban_card(item, "list") for item in items], className="sidebar-window-grid") if items else html.P("Nenhuma pendência encontrada."),
        ])
    letters = data.get("letters", [])
    return html.Div([
        html.P(f"{len(letters)} cartas", className="muted"),
        html.Div([html.Article([
            badge(letter["status"], letter["tone"]), html.H3(letter["title"]), html.P(letter["description"]),
        ], className="letter-window-card") for letter in letters], className="sidebar-window-grid") if letters else
        html.P("Nenhuma carta ou fluxo de assinatura foi encontrado nos dados disponíveis do Jira."),
    ])


def timeline_years(data):
    """Anos que possuem alguma data útil para a linha do tempo."""
    years = {datetime.now(LOCAL_ZONE).year}
    for item in data["items"]:
        for field in ("start_date", "regulatory_deadline", "delivery_date", "end_date", "due", "created", "resolved"):
            value = item.get(field)
            if value:
                years.add(value.astimezone(LOCAL_ZONE).year)
    return list(range(min(years), max(years) + 1))


def timeline_view(items, page, selected_year):
    if not items:
        return html.P("Nenhum item para esta seleção.")
    grouped = defaultdict(list)
    for item in items:
        grouped[item["owner"] or NO_OWNER].append(item)
    names = sorted(grouped)
    pages = max(1, ceil(len(names)/5))
    page = max(1,min(int(page or 1),pages))
    year = int(selected_year or datetime.now(LOCAL_ZONE).year)
    low = datetime(year, 1, 1, tzinfo=LOCAL_ZONE)
    high = datetime(year + 1, 1, 1, tzinfo=LOCAL_ZONE)
    def shifted_month(base, offset):
        index = base.year*12+base.month-1+offset
        return datetime(index//12,index%12+1,1,tzinfo=LOCAL_ZONE)
    # A faixa horizontal corresponde sempre ao ano civil completo. Janeiro e
    # dezembro deixam de desaparecer quando o foco estava nos meses centrais.
    days = (high-low).days
    today = datetime.now(LOCAL_ZONE)
    today_pos = (today-low).total_seconds()/(high-low).total_seconds()*100
    def track(item=None):
        marks = []
        if 0 <= today_pos <= 100:
            marks.append(html.Span(className="gantt-today", style={"left":f"{today_pos}%"}))
        if item:
            finish = item.get("regulatory_deadline") or item.get("delivery_date") or item.get("end_date")
            start = item.get("start_date") or finish
            if finish and start and start <= finish and start < high and finish >= low:
                left = (max(start,low)-low).total_seconds()/(high-low).total_seconds()*100
                width = (min(finish,high)-max(start,low)).total_seconds()/(high-low).total_seconds()*100
                marks.append(html.Span("←" if start < low else "", className="gantt-bar", style={"left":f"{left}%", "width":f"{max(0.6,width)}%", "background":"#ff8c70" if item["overdue"] else "#00a3ba"}, title=f"Início: {date_label(item.get('start_date'))} · Fim: {date_label(finish)}"))
            else:
                marks.append(html.Small("Sem prazo" if not finish else date_label(finish),className="muted"))
        return html.Div(marks,className="gantt-track",style={"backgroundSize":f"{7/days*100}% 100%"})
    headers = ["# / Ticket", "Responsável", "% Progresso", "Complexidade", "Criticidade", "Prazo regulatório", "Status"]
    month_names = ["jan.","fev.","mar.","abr.","mai.","jun.","jul.","ago.","set.","out.","nov.","dez."]
    month_starts = [shifted_month(low, offset) for offset in range(12)]
    axis = html.Div([
        *[html.Strong(f"{month_names[start.month-1]} {start.year}", style={"left":f"{(start-low).total_seconds()/(high-low).total_seconds()*100}%"}) for start in month_starts],
        *[html.Span((low + timedelta(days=d)).strftime("%d"),style={"left":f"{d/days*100}%"}) for d in range(0,days,7)],
    ],className="gantt-axis")
    groups=[]
    for name in names:
        rows=[]
        for n,item in enumerate(grouped[name],1):
            initials=''.join(part[0] for part in name.split()[:2])
            rows.append(html.Div([
                html.Button([html.Small(str(n)), html.Span(item["key"],className="gantt-key"), " ", item["title"]], id={"type":"issue-button","key":"timeline:"+item["id"]}, n_clicks=0, className="gantt-ticket", title=item["title"]),
                html.Span(html.Span(initials,className="gantt-avatar"),title=name,className="gantt-owner"),
                html.Span("—" if item["progress"] is None else f"{item['progress']:g}%"),
                html.Span(item.get("effort") or "—",title="Complexidade"),
                html.Span(item.get("criticality") or "—",title="Criticidade"),
                html.Span(date_label(item.get("regulatory_deadline")) if item.get("regulatory_deadline") else "—"),
                html.Span(item["status"],className="gantt-status",title=item["status"]),track(item)
            ],className="gantt-grid gantt-item"))
        groups.append(html.Details([html.Summary([html.Span([html.Span("›",className="gantt-chevron"),name],className="gantt-person"),html.Span(f"{len(rows)} tickets",className="gantt-total"),track()],className="gantt-group-head"),*rows],className="gantt-group"))
    return html.Div([html.P(f"{len(names)} responsáveis · {len(items)} tickets · Clique no nome para expandir",className="chart-note"),
        html.Div([html.Div([*[html.Span(h,title=h) for h in headers],axis],className="gantt-grid gantt-header"),*groups],className="gantt-table", **{"data-timeline-year":str(year)})])


@lru_cache(maxsize=96)
def cached_activity(mode, version, kind, owner, order, query, upcoming):
    data = filtered_data(get_dataset(mode), kind, owner, order)
    return activity_panel(data, upcoming, query or "")


@lru_cache(maxsize=48)
def cached_sidebar(mode, version):
    return sidebar_layout(get_dataset(mode))


@lru_cache(maxsize=96)
def cached_results(mode, version, kind, owner, order, month, theme):
    data = filtered_data(get_dataset(mode), kind, owner, order)
    return results_content(data, month, theme)


@lru_cache(maxsize=128)
def cached_allocation(mode, version, color_mode, role, theme, tab, result_range, kind, owner, order, query):
    data = filtered_data(get_dataset(mode), kind, owner, order)
    items = result_items_for_range(data, result_range) if tab == "results" else [
        item for item in active_items(data) if item["queue"] == (tab == "upcoming")
    ]
    return allocation_view(data, color_mode, role, theme, search_kanban(items, query))


@lru_cache(maxsize=96)
def cached_timeline(mode, version, kind, owner, order, query, tab, result_month, page, calendar_year):
    data = filtered_data(get_dataset(mode), kind, owner, order)
    items = (result_items_for_period(data, result_month)
             if tab == "results" else [i for i in active_items(data) if i["queue"] == (tab == "upcoming")])
    ordered = ordered_items(search_kanban(items, query), order)
    ordered.sort(key=lambda i: (i["owner"] or NO_OWNER).casefold())
    return timeline_view(ordered, page, calendar_year)


def dashboard_layout(data):
    owners = sorted({item["owner"] or NO_OWNER for item in data["items"]})
    data = filtered_data(data, "all")
    months = periods(data)
    result_options = result_period_options(data)
    years = timeline_years(data)
    # Deixa as visões mais usadas prontas no primeiro carregamento. Assim, a troca
    # de aba não precisa aguardar a primeira construção dos cards ou do Plotly.
    initial_items = [item for item in active_items(data) if not item["queue"]]
    fig, buttons, button_style, chart_style, notices = allocation_view(
        data, "kind", "owner", "light", initial_items
    )
    return [
        html.Section([
            html.H1("Dashboard de Demandas e Consultas Técnicas", className="dashboard-title"),
            dcc.Tabs(id="activity-tabs", value="ongoing", className="manager-tabs", children=[
                dcc.Tab(label=label, value=value, className="manager-tab", selected_className="manager-tab--selected")
                for label, value in [("O que está rolando", "ongoing"), ("O que está próximo", "upcoming"), ("Resultados", "results")]
            ]),
            html.Div([
                html.Div([
                    html.Span([icon("fa-filter"), " Filtrar itens"], className="navigation-label"),
                    dcc.Tabs(id="item-kind", value="all", className="filter-tabs", children=[
                        dcc.Tab(label="Todos", value="all", className="filter-tab", selected_className="filter-tab--selected"),
                        dcc.Tab(label="Demandas", value="Demandas", className="filter-tab", selected_className="filter-tab--selected"),
                        dcc.Tab(label="Consulta Técnica", value="Consultas técnicas", className="filter-tab", selected_className="filter-tab--selected"),
                    ]),
                ], className="navigation-group"),
                html.Div([
                    html.Span([icon("fa-table-columns"), " Visualizar"], className="navigation-label"),
                    dcc.Tabs(id="content-view", value="overview", className="filter-tabs", children=[
                        dcc.Tab(label="Visão geral", value="overview", className="filter-tab", selected_className="filter-tab--selected"),
                        dcc.Tab(label="Alocação por pessoa", value="allocation", className="filter-tab", selected_className="filter-tab--selected"),
                        dcc.Tab(label="Linha do tempo", value="timeline", className="filter-tab", selected_className="filter-tab--selected"),
                    ]),
                ], className="navigation-group"),
            html.Div([html.Span("Responsável", className="navigation-label"), dcc.Dropdown(id="owner-filter", options=[{"label":"Todos", "value":"all"}] + [{"label":name,"value":name} for name in owners], value="all", clearable=False)], className="navigation-group extra-filter"),
            html.Div([html.Span("Ordenar por", className="navigation-label"), dcc.Dropdown(id="sort-items", options=[{"label":label,"value":value} for label,value in [("Mais recentes","created"),("Prazo regulatório","regulatory_deadline"),("Tipo","kind"),("Responsável","owner"),("Complexidade","effort"),("Progresso","progress"),("Código do ticket","key")]], value="created", clearable=False)], className="navigation-group extra-filter"),
            html.Div([icon("fa-magnifying-glass"), dcc.Input(id="kanban-search", type="search", placeholder="Buscar título, código ou comentário", debounce=0.3, className="kanban-search-input")], id="kanban-search-wrap", className="kanban-search-wrap"),
            ], className="navigation-controls", role="group", **{"aria-label": "Filtros e visualização"}),
            html.Div([

            html.Div(activity_panel(data), id="ongoing-panel"),
            html.Div(activity_panel(data, True), id="upcoming-panel", hidden=True),
            html.Div([
                html.Div([html.H2("Resultados da equipe", className="section-title"),
                          html.Div([html.Label("Período de resolução", htmlFor="results-month"), dcc.Dropdown(
                              id="results-month", options=result_options,
                              value=months[0] if months else None, clearable=False, placeholder="Nenhum período encontrado")], className="period-control")], className="panel-heading"),
                html.Div(id="results-content"),
            ], id="results-panel", hidden=True),
            ], id="overview-panel"),
        html.Section([
            html.Div([html.Div([html.P("VISÃO DA EQUIPE", className="section-kicker"), html.H2("Alocação por pessoa", className="section-title")]), html.Span("P/M/G conforme o campo Complexidade", className="muted")], className="panel-heading"),
            html.Div([
                html.Div([html.Label("Cores por", htmlFor="allocation-mode"), dcc.Dropdown(id="allocation-mode", options=[{"label": "Tipo de item", "value": "kind"}, {"label": "Complexidade P / M / G", "value": "effort"}, {"label": "Papel na atividade", "value": "role"}], value="kind", clearable=False)]),
                html.Div([html.Label("Mostrar alocações como", htmlFor="allocation-role"), dcc.Dropdown(id="allocation-role", options=[{"label": "Responsável", "value": "owner"}, {"label": "Participante", "value": "participant"}, {"label": "Responsável + participante", "value": "all"}], value="owner", clearable=False)]),
                html.Div([html.Label("Período dos resultados", htmlFor="result-range"), dcc.Dropdown(id="result-range", options=[
                    {"label": "Todo o histórico", "value": "all"}, {"label": "Ano atual", "value": "year"},
                    {"label": "Últimos 6 meses", "value": "6m"}, {"label": "Últimos 3 meses", "value": "3m"},
                    {"label": "Último mês", "value": "1m"}], value="year", clearable=False)], id="allocation-period-control", hidden=True),
            ], className="allocation-controls"),
            html.Div(html.Div([
                dcc.Graph(id="allocation-chart", figure=fig, responsive=True, style={"height": "250px"}, config={"displayModeBar": False}),
                html.Div(buttons, id="person-buttons", className="person-buttons", style=button_style),
            ], id="allocation-inner", style=chart_style), className="allocation-scroll"),
            html.Div(notices, id="allocation-notices"),
        ], id="allocation-panel", className="surface section-card workload-section", hidden=True),
        dbc.Modal([dbc.ModalHeader(dbc.ModalTitle("Linha do tempo")), dbc.ModalBody([
                  dcc.Store(id="timeline-page", data=1),
                  html.Div([
                      html.Button("← Ano anterior", id="timeline-prev", n_clicks=0),
                      html.Div([html.Label("Ano", htmlFor="timeline-year"), dcc.Dropdown(
                          id="timeline-year", options=[{"label": str(year), "value": year} for year in years],
                          value=datetime.now(LOCAL_ZONE).year if datetime.now(LOCAL_ZONE).year in years else years[-1],
                          clearable=False, searchable=False,
                      )], className="timeline-year-control"),
                      html.Button("Ano atual", id="timeline-today", n_clicks=0),
                      html.Button("Próximo ano →", id="timeline-next", n_clicks=0),
                      html.Div([
                          html.Button("Minimizar campos", id="timeline-fields-toggle", n_clicks=0,
                                      title="Recolher as colunas de detalhes", **{"aria-pressed": "false"}),
                          html.Button("Expandir todos", id="timeline-groups-toggle", n_clicks=0,
                                      title="Abrir todos os responsáveis", **{"aria-pressed": "false"}),
                      ], className="timeline-view-actions"),
                  ], className="timeline-month-controls"),
                  html.Div(id="timeline-content")])], id="timeline-modal", is_open=False, centered=True, className="timeline-dialog", backdrop="static"),
        ], className="surface section-card activity-section"),
        dbc.Modal([dbc.ModalHeader(dbc.ModalTitle(id="person-title")), dbc.ModalBody(id="person-details")], id="person-modal", is_open=False, size="xl", scrollable=True),
    ]


def register_callbacks(app):
    @app.callback(Output("owner-filter", "options"), Output("owner-filter", "value"),
                  Input("jira-data-version", "data"), Input("data-mode", "data"), State("owner-filter", "value"))
    def refresh_owner_options(version, mode, current):
        owners = sorted({item["owner"] or NO_OWNER for item in get_dataset(mode)["items"]})
        options = [{"label": "Todos", "value": "all"}] + [{"label": name, "value": name} for name in owners]
        return options, current if current == "all" or current in owners else "all"

    app.clientside_callback(
        "function(tab) { return tab !== 'results'; }",
        Output("allocation-period-control", "hidden"), Input("activity-tabs", "value")
    )

    @app.callback(Output("timeline-year", "options"), Input("jira-data-version", "data"), Input("data-mode", "data"))
    def refresh_timeline_years(version, mode):
        return [{"label": str(year), "value": year} for year in timeline_years(get_dataset(mode))]

    @app.callback(Output("timeline-year", "value"), Input("timeline-prev", "n_clicks"),
                  Input("timeline-next", "n_clicks"), Input("timeline-today", "n_clicks"),
                  State("timeline-year", "value"), State("timeline-year", "options"), prevent_initial_call=True)
    def change_year(prev, following, today, current, options):
        years = sorted(int(option["value"]) for option in (options or []))
        if not years:
            raise PreventUpdate
        if ctx.triggered_id == "timeline-today":
            this_year = datetime.now(LOCAL_ZONE).year
            return this_year if this_year in years else min(years, key=lambda year: abs(year - this_year))
        target = int(current or years[-1]) + (1 if ctx.triggered_id == "timeline-next" else -1)
        return target if target in years else no_update

    @app.callback(Output("timeline-content", "children"), Input("item-kind", "value"), Input("owner-filter", "value"), Input("sort-items", "value"), Input("kanban-search", "value"), Input("activity-tabs", "value"), Input("results-month", "value"), Input("data-mode", "data"), Input("timeline-page", "data"), Input("timeline-year", "value"), Input("jira-data-version", "data"), Input("timeline-modal", "is_open"))
    def update_timeline(kind, owner, order, query, tab, month, mode, page, calendar_year, version, opened):
        if not opened:
            raise PreventUpdate
        return cached_timeline(mode, version, kind, owner, order, query or "", tab, month, page, calendar_year)

    app.clientside_callback(
        """function(view, opened) {
            const trigger = dash_clientside.callback_context.triggered_id;
            if (trigger === 'timeline-modal' && !opened) view = 'overview';
            return [view === 'allocation', view !== 'allocation', view === 'timeline', view];
        }""",
        Output("overview-panel", "hidden"), Output("allocation-panel", "hidden"),
        Output("timeline-modal", "is_open"), Output("content-view", "value"),
        Input("content-view", "value"), Input("timeline-modal", "is_open")
    )

    @app.callback(Output("ongoing-panel", "children"),
                  Output("upcoming-panel", "children"), Output("sidebar-data", "children"),
                  Output("results-month", "options"), Output("results-month", "value"),
                  Input("data-mode", "data"), Input("item-kind", "value"), Input("owner-filter", "value"), Input("sort-items", "value"), Input("kanban-search", "value"), Input("activity-tabs", "value"), Input("jira-data-version", "data"), State("results-month", "value"))
    def switch_data(mode, kind, owner, order, query, active_tab, version, current_month):
        data = filtered_data(get_dataset(mode), kind, owner, order)
        months = periods(data)
        options = result_period_options(data)
        values = {option["value"] for option in options}
        month = current_month if current_month in values else (months[0] if months else None)
        ongoing = cached_activity(mode, version, kind, owner, order, query or "", False) if active_tab == "ongoing" else no_update
        upcoming = cached_activity(mode, version, kind, owner, order, query or "", True) if active_tab == "upcoming" else no_update
        sidebar = cached_sidebar(mode, version) if ctx.triggered_id in (None, "data-mode", "jira-data-version") else no_update
        return (ongoing, upcoming, sidebar,
                options, month)

    app.clientside_callback(
        """function(value) {
            return [value !== 'ongoing', value !== 'upcoming', value !== 'results',
                    value === 'results', value === 'upcoming' ? 'upcoming-view' : ''];
        }""",
        Output("ongoing-panel", "hidden"), Output("upcoming-panel", "hidden"),
        Output("results-panel", "hidden"), Output("kanban-search-wrap", "hidden"),
        Output("overview-panel", "className"), Input("activity-tabs", "value")
    )

    @app.callback(Output("results-content", "children"), Input("activity-tabs", "value"),
                  Input("results-month", "value"), Input("theme-preference", "data"),
                  Input("data-mode", "data"), Input("item-kind", "value"),
                  Input("owner-filter", "value"), Input("sort-items", "value"),
                  Input("jira-data-version", "data"))
    def update_results(value, month, theme, mode, kind, owner, order, version):
        if value != "results":
            raise PreventUpdate
        return cached_results(mode, version, kind, owner, order, month, theme)

    @app.callback(Output("allocation-chart", "figure"), Output("person-buttons", "children"), Output("person-buttons", "style"),
                  Output("allocation-inner", "style"), Output("allocation-notices", "children"),
                  Input("allocation-mode", "value"), Input("allocation-role", "value"), Input("theme-preference", "data"), Input("data-mode", "data"),
                  Input("activity-tabs", "value"), Input("result-range", "value"), Input("item-kind", "value"), Input("owner-filter", "value"), Input("sort-items", "value"), Input("kanban-search", "value"), Input("jira-data-version", "data"))
    def update_allocation(mode, role, theme, data_mode, tab, result_range, kind, owner, order, query, version):
        # Mantém o gráfico pronto em segundo plano. A abertura da aba passa a ser
        # uma troca puramente visual no navegador, sem aguardar Plotly no servidor.
        return cached_allocation(data_mode, version, mode, role, theme, tab, result_range, kind, owner, order, query or "")

    @app.callback(Output("person-modal", "is_open"), Output("person-title", "children"), Output("person-details", "children"),
                  Input({"type": "person-button", "name": ALL}, "n_clicks"), Input("allocation-chart", "clickData"),
                  Input({"type": "issue-button", "key": ALL}, "n_clicks"), Input("data-mode", "data"), Input("jira-data-version", "data"),
                  Input({"type": "sidebar-open", "view": ALL}, "n_clicks"), Input({"type":"lane-open", "lane":ALL}, "n_clicks"),
                  State("allocation-role", "value"), State("activity-tabs", "value"), State("results-month", "value"), State("result-range", "value"), State("item-kind", "value"), State("owner-filter", "value"), State("sort-items", "value"), State("kanban-search", "value"), prevent_initial_call=True)
    def select_details(person_clicks, chart_click, issue_clicks, mode, version, sidebar_clicks, lane_clicks, role, tab, month, result_range, kind, owner, order, query):
        if ctx.triggered_id in ("data-mode", "jira-data-version"):
            return False, "", []
        data, triggered = get_dataset(mode), ctx.triggered_id
        if isinstance(triggered, dict):
            if not ctx.triggered[0].get("value"):
                raise PreventUpdate
            if triggered.get("type") == "lane-open":
                filtered = filtered_data(data, kind, owner, order)
                items = ordered_items(search_kanban(kanban_items(filtered, triggered["lane"]), query), order)
                title = {"development":"Em desenvolvimento", "late":"Atrasado", "finished":"Finalizado"}[triggered["lane"].split(":")[1]]
                return True, title, html.Div([kanban_card(item, "list") for item in items], className="sidebar-window-grid")
            if triggered.get("type") == "sidebar-open":
                view = triggered["view"]
                return True, {"pending":"Pendências Aneel", "cards":"Cartas", "unassigned":"Consultas sem responsável"}[view], sidebar_window(data, view)
            if triggered.get("type") == "issue-button":
                key = triggered["key"].removeprefix("pending:").removeprefix("ongoing:").removeprefix("upcoming:").removeprefix("list:").removeprefix("timeline:")
                if key.startswith("allocation:"):
                    key = key.split(":", 2)[2]
                item = next((i for i in data["items"] if i["id"] == key), None)
                if item:
                    return True, item["title"], issue_details(item)
                raise PreventUpdate
            name = triggered.get("name")
        else:
            name = chart_click["points"][0]["x"] if chart_click and triggered == "allocation-chart" else None
        data = filtered_data(data, kind, owner, order)
        selected_items = (result_items_for_range(data, result_range) if tab == "results" else [item for item in active_items(data) if item["queue"] == (tab == "upcoming")])
        selected_items = search_kanban(selected_items, query)
        if name not in {person for person, _, _ in assignments(data, role, selected_items)}:
            raise PreventUpdate
        return True, f"Alocação · {name}", person_details(data, name, role, selected_items)
