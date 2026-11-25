"""Atualização assíncrona e segura do snapshot usado pelo dashboard."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import Lock

from jira_data import LOCAL_ZONE, get_data, invalidate_cache
from sync_jira import sync_snapshot
from team_members import load_team_scope, sync_team_scope
from sharepoint_data import sync_sharepoint_letters


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jira-refresh")
_lock = Lock()
_state = {
    "running": False,
    "progress": 0,
    "message": "Dados locais prontos.",
    "error": None,
    "version": None,
    "finished_at": None,
}


def _set_state(**changes):
    with _lock:
        _state.update(changes)


def refresh_state():
    with _lock:
        return deepcopy(_state)


def _progress(message, completed, total):
    percentage = round(completed / total * 100) if total else 0
    _set_state(progress=percentage, message=message)


def _refresh():
    failures = []
    try:
        sync_snapshot(lambda message, completed, total: _set_state(
            progress=round((completed / total * 72) if total else 0), message=message))
    except Exception as error:
        failures.append(f"Jira ({type(error).__name__})")

    team_warning = ""
    try:
        _set_state(progress=75, message="Sincronizando as equipes autorizadas…")
        sync_team_scope(lambda message: _set_state(progress=82, message=message))
    except Exception:
        if load_team_scope():
            team_warning = " A última lista válida das equipes foi mantida."
        else:
            team_warning = " Configure ATLASSIAN_EMAIL e ATLASSIAN_API_TOKEN para liberar os membros da área."
        failures.append("equipes Atlassian")

    try:
        _set_state(progress=86, message="Sincronizando Acompanhamento Cartas no SharePoint…")
        sync_sharepoint_letters(lambda message: _set_state(progress=94, message=message))
    except Exception as error:
        sharepoint_failure = (
            "SharePoint (autenticação necessária)"
            if isinstance(error, RuntimeError)
            else f"SharePoint ({type(error).__name__})"
        )
        failures.append(sharepoint_failure)

    try:
        invalidate_cache()
        get_data()
        finished = datetime.now(LOCAL_ZONE)
        version = finished.isoformat()
        message = (
            "Atualização parcial; bases anteriores preservadas para: " + ", ".join(failures) + "." + team_warning
            if failures else f"Jira e SharePoint atualizados em {finished.strftime('%d/%m/%Y às %H:%M')}."
        )
        _set_state(running=False, progress=100,
                   message=message, error="; ".join(failures) if failures else None,
                   version=version, finished_at=finished.isoformat())
    except Exception as error:
        _set_state(running=False, message="Não foi possível recarregar o dashboard. As bases anteriores foram preservadas.",
                   error=type(error).__name__, finished_at=datetime.now(LOCAL_ZONE).isoformat())


def start_refresh():
    with _lock:
        if _state["running"]:
            return deepcopy(_state)
        _state.update(running=True, progress=0, message="Iniciando atualização do Jira e do SharePoint…", error=None)
    _executor.submit(_refresh)
    return refresh_state()
