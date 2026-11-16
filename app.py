"""Tela principal com dados reais do Jira e avisos para campos indisponiveis."""

from pathlib import Path

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from dashboard import dashboard_layout, register_callbacks, sidebar_layout
from jira_data import get_data
from jira_refresh import refresh_state, start_refresh


APP_DIR = Path(__file__).resolve().parent

app = Dash(
    __name__,
    assets_folder=str(APP_DIR / "assets"),
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css",
    ],
    title="Protótipo | Central da Área",
)
server = app.server


def serve_layout():
    data = get_data()
    version = data["synced_at"].isoformat() if data.get("synced_at") else "sem-versao"
    stamp = data["synced_at"].strftime("%d/%m/%Y às %H:%M") if data.get("synced_at") else "não disponível"
    team_scope = data.get("team_scope", {})
    team_status = (f"{team_scope.get('members', 0)} membros da área" if team_scope.get("configured")
                   else "equipes ainda não sincronizadas")
    return html.Main([
        dcc.Store(id="theme-preference", data="light", storage_type="local"),
        dcc.Store(id="data-mode", data="real", storage_type="memory"),
        dcc.Store(id="jira-data-version", data=version, storage_type="memory"),
        # O polling só é habilitado enquanto uma sincronização está em andamento.
        # Mantê-lo ativo em repouso criava requisições e rerenders a cada 3 segundos.
        dcc.Interval(id="refresh-poll", interval=1000, n_intervals=0, disabled=True),
        html.Div([
            html.Div([
                html.Div(dashboard_layout(data), className="main-column"),
                html.Aside([
                    html.Div(sidebar_layout(data), id="sidebar-data", className="sidebar-data"),
                    html.Button([
                        html.I(id="theme-icon", className="fa-solid fa-moon", **{"aria-hidden": "true"}),
                        html.Span("Ativar modo escuro", id="theme-label"),
                    ], id="theme-toggle", n_clicks=0, className="theme-toggle",
                       role="switch", **{"aria-checked": "false", "aria-label": "Modo escuro"}),
                    html.Div([
                        html.Button([
                            html.I(className="fa-solid fa-rotate", **{"aria-hidden": "true"}),
                            html.Span("Atualizar dados do Jira"),
                        ], id="refresh-jira", n_clicks=0, className="refresh-jira"),
                        html.Progress(id="refresh-progress", value=0, max=100, className="refresh-progress", style={"display": "none"}),
                        html.Small(f"Última atualização: {stamp} · {team_status}", id="refresh-status", className="refresh-status", **{"aria-live": "polite"}),
                    ], className="refresh-panel"),
                ], className="side-column"),
            ], className="dashboard-grid"),
        ], className="app-shell"),
    ])


app.layout = serve_layout


register_callbacks(app)


@app.callback(
    Output("refresh-jira", "disabled"), Output("refresh-poll", "disabled"),
    Output("refresh-status", "children"), Output("refresh-progress", "value"),
    Output("refresh-progress", "style"), Output("jira-data-version", "data"),
    Input("refresh-jira", "n_clicks"), Input("refresh-poll", "n_intervals"),
    State("jira-data-version", "data"), prevent_initial_call=True,
)
def refresh_jira_data(clicks, ticks, current_version):
    state = start_refresh() if ctx.triggered_id == "refresh-jira" else refresh_state()
    running = state["running"]
    if ctx.triggered_id == "refresh-poll" and not running and not state.get("finished_at"):
        return False, False, no_update, no_update, no_update, no_update
    message = state["message"]
    if state.get("error"):
        message += " Tente novamente ou confira a conexão com o feed."
    version = state.get("version") if state.get("version") and state.get("version") != current_version else no_update
    return running, not running, message, state["progress"], ({"display": "block"} if running else {"display": "none"}), version

app.clientside_callback(
    """function(clicks, theme) {
        return theme === 'dark' ? 'light' : 'dark';
    }""",
    Output("theme-preference", "data"), Input("theme-toggle", "n_clicks"),
    State("theme-preference", "data"), prevent_initial_call=True,
)

app.clientside_callback(
    """function(theme) {
        const dark = theme === 'dark';
        document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
        document.documentElement.setAttribute('data-bs-theme', dark ? 'dark' : 'light');
        return [dark ? 'Ativar modo claro' : 'Ativar modo escuro',
                dark ? 'fa-solid fa-sun' : 'fa-solid fa-moon', dark ? 'true' : 'false'];
    }""",
    Output("theme-label", "children"), Output("theme-icon", "className"),
    Output("theme-toggle", "aria-checked"), Input("theme-preference", "data"),
)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8060)
