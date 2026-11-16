"""Leitura do Jira e regras auditáveis para a tela principal; sem dados simulados."""

import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from team_members import load_team_scope

ROOT = Path(__file__).resolve().parent
LOCAL_ZONE = ZoneInfo("America/Sao_Paulo")
QUEUE_STATUSES = {"aberto", "to do", "tarefas pendentes", "backlog", "radar", "aguardando analise"}
CLOSED_STATUSES = {"done", "finalizado", "concluido", "resolvido"}
SCOPE_TYPES = {"registro de demanda": "Demandas", "consulta tecnica": "Consultas técnicas"}


def text(value):
    cleaned = str(value).strip() if value is not None else ""
    return "" if cleaned.casefold() in ("null", "none", "nan") else cleaned


def normal(value):
    return "".join(c for c in unicodedata.normalize("NFKD", text(value).casefold()) if not unicodedata.combining(c))


def date_value(value):
    raw = text(value)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        dt = None
        for fmt in ("%d/%m/%y %H:%M", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d/%m/%y"):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                pass
        if dt is None:
            return None
    return dt.replace(tzinfo=LOCAL_ZONE) if dt.tzinfo is None else dt


def date_label(value):
    return value.astimezone(LOCAL_ZONE).strftime("%d/%m/%Y") if value else "Dado não encontrado"


def rows(con, name, tables):
    if name not in tables:
        return []
    cur = con.execute('SELECT * FROM "' + name.replace('"', '""') + '"')
    names = [col[0] for col in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def history_order(row):
    dt = date_value(row.get("history_new_value_start"))
    return (dt.timestamp() if dt else float("-inf"), float(row.get("history_sequence") or 0))


def latest_fields(history):
    result = {}
    for row in history:
        key = (text(row.get("chave")), text(row.get("history_field_id")))
        if key not in result or history_order(row) > history_order(result[key]):
            result[key] = row
    return result


def latest_value(fields, key, field):
    row = fields.get((key, field))
    return row.get("history_new_value") if row else None


def participant_names(value):
    raw = text(value)
    if not raw or normal(raw) in ("null", "none"):
        return []
    # O conector exporta Participantes como uma lista de nomes entre colchetes.
    return sorted({name.strip().strip('"\'') for name in raw.strip("[]").split(",") if name.strip().strip('"\'')})


def percent_value(value):
    raw = text(value).replace("%", "").replace(",", ".").strip()
    try:
        number = float(raw)
        return round(number, 1) if 0 <= number <= 100 else None
    except ValueError:
        return None


def latest_comments(comments):
    result = {}
    for row in comments:
        key = text(row.get("chave"))
        created = date_value(row.get("comment_created")) or date_value(row.get("comment_updated"))
        sort = created.timestamp() if created else float("-inf")
        if key not in result or sort > result[key][0]:
            result[key] = (sort, row)
    return {key: row for key, (_, row) in result.items()}


def status_durations(history, created, resolved):
    """Soma intervalos únicos por status, limitados à criação/resolução do item.

    Intervalos sobrepostos ou negativos são descartados. Lacunas permanecem
    explícitas; o tempo desconhecido não é atribuído a nenhum status.
    """
    if not created or not resolved or resolved < created:
        return {}, False
    intervals = set()
    for row in history:
        status = text(row.get("history_status"))
        start = date_value(row.get("status_start"))
        end = date_value(row.get("status_end"))
        if not status or not start:
            continue
        start, end = max(start, created), min(end or resolved, resolved)
        if end > start:
            intervals.add((start, end, status))
    total, cursor, complete = defaultdict(float), created, True
    for start, end, status in sorted(intervals):
        if start < cursor:
            complete = False
            continue
        if (start - cursor).total_seconds() > 1:
            complete = False
        total[status] += (end - start).total_seconds() / 86400
        cursor = end
    if (resolved - cursor).total_seconds() > 1 or not total:
        complete = False
    return dict(total), complete


def build_items(raw_issues, history, comments, subtasks, feed, as_of, team_scope):
    fields = latest_fields(history)
    comments_by_key = latest_comments(comments)
    histories = defaultdict(list)
    for row in history:
        histories[text(row.get("chave"))].append(row)
    raw_by_key = {text(row.get("chave")): row for row in raw_issues}
    children = defaultdict(set)
    for row in subtasks:
        if row.get("chave") and row.get("subtarefas"):
            children[text(row["chave"])].add(text(row["subtarefas"]))
    result = []
    for raw in raw_issues:
        kind = SCOPE_TYPES.get(normal(raw.get("tipo_de_item")))
        if not kind:
            continue
        key = text(raw.get("chave"))
        item_history = histories[key]
        current_status = [h for h in item_history if normal(h.get("current_status?")) in ("y", "yes", "true")]
        current_owner = [h for h in item_history if normal(h.get("current_assignee?")) in ("y", "yes", "true")]
        status = text(max(current_status, key=history_order).get("history_status")) if current_status else ""
        owner = text(max(current_owner, key=history_order).get("history_assignee")) if current_owner else text(raw.get("responsavel_name"))
        owner_account_id = text(raw.get("responsavel_accountid"))
        allowed_accounts = team_scope["account_ids"]
        allowed_names = {normal(name) for name in team_scope["users"].values()}
        # Itens sem responsável continuam visíveis; responsáveis externos são excluídos.
        if owner and owner_account_id not in allowed_accounts and normal(owner) not in allowed_names:
            continue
        resolution = normal(raw.get("resolucao"))
        cancelled = "cancel" in resolution or "cancel" in normal(status)
        closed = cancelled or bool(resolution and resolution != "unresolved") or normal(status) in CLOSED_STATUSES
        created, resolved = date_value(raw.get("criado")), date_value(raw.get("resolvido"))
        participants_row = fields.get((key, "customfield_10068"))
        participants = [name for name in participant_names(latest_value(fields, key, "customfield_10068"))
                        if normal(name) in allowed_names]
        complexity = text(latest_value(fields, key, "customfield_10249"))
        match = re.search(r"(?:^|[^A-Za-z])([PMG])$", complexity)
        effort = match.group(1) if match else None
        progress, progress_source = None, None
        for field, label in [("customfield_14702", "Andamento"), ("customfield_14495", "% Progresso"), ("customfield_10053", "% Evolução")]:
            progress = percent_value(latest_value(fields, key, field))
            if progress is not None:
                progress_source = f"Campo Jira: {label} (último valor no histórico)"
                break
        if progress is None and children[key] and all(child in raw_by_key for child in children[key]):
            done = sum(bool(text(raw_by_key[child].get("resolucao"))) and normal(raw_by_key[child].get("resolucao")) != "unresolved" for child in children[key])
            progress = round(100 * done / len(children[key]), 1)
            progress_source = f"{done}/{len(children[key])} subtarefas encerradas (inclui canceladas); não representa esforço realizado"
        due, due_source = None, None
        regulatory_deadline = date_value(latest_value(fields, key, "customfield_14751")) if kind == "Demandas" else None
        delivery_date = date_value(latest_value(fields, key, "duedate")) if kind == "Demandas" else None
        end_date = (date_value(latest_value(fields, key, "duedate")) or
                    date_value(latest_value(fields, key, "customfield_10768"))) if kind == "Consultas técnicas" else None
        due_fields = [("duedate", "Prazo Jira")]
        if kind == "Consultas técnicas":
            due_fields.append(("customfield_10768", "Data Prevista SLA"))
        due_fields += [("customfield_14751", "Prazo regulatório"), ("customfield_10374", "Prazo")]
        for field, label in due_fields:
            due = date_value(latest_value(fields, key, field))
            if due:
                due_source = label
                break
        # Datas sem hora são consideradas vencidas somente no dia seguinte.
        overdue = due.astimezone(LOCAL_ZONE).date() < as_of.astimezone(LOCAL_ZONE).date() if due and not closed else False if closed else None
        comment = comments_by_key.get(key, {})
        comment_author = text(comment.get("comment_author")) or None
        if comment_author and normal(comment_author) not in allowed_names:
            comment_author = None
        days, complete_history = status_durations(item_history, created, resolved) if closed else ({}, False)
        result.append(dict(
            id=f"{feed}:{key}", key=key, title=text(raw.get("resumo")) or "Título não encontrado",
            kind=kind, topic="Regras" if feed == "regras" else "PdC", owner=owner or None,
            owner_account_id=owner_account_id or None,
            participants=participants, participants_known=participants_row is not None,
            effort=effort, status=status or None, closed=closed, cancelled=cancelled,
            queue=normal(status) in QUEUE_STATUSES, progress=progress, progress_source=progress_source,
            due=due, due_source=due_source, overdue=overdue,
            regulatory_deadline=regulatory_deadline, delivery_date=delivery_date, end_date=end_date,
            start_date=date_value(latest_value(fields, key, "customfield_10015")),
            criticality=text(latest_value(fields, key, "customfield_10216")),
            author=comment_author,
            comment=text(comment.get("comment_body")) or None,
            comment_date=date_value(comment.get("comment_created")),
            created=created, resolved=resolved,
            month=resolved.astimezone(LOCAL_ZONE).strftime("%Y-%m") if resolved else None,
            cycle=(resolved - created).total_seconds() / 86400 if created and resolved and resolved >= created else None,
            days=days, complete_history=complete_history,
        ))
    return result


def get_data():
    snapshot = Path(os.environ.get("JIRA_SNAPSHOT_PATH", ROOT / "jira_snapshot.duckdb"))
    fallback = ROOT.parent / "jira.duckdb"
    path = snapshot if snapshot.exists() else fallback
    return _load(str(path), path.stat().st_mtime_ns if path.exists() else 0)


def invalidate_cache():
    """Descarta snapshots processados após uma sincronização bem-sucedida."""
    _load.cache_clear()


@lru_cache(maxsize=2)
def _load(path, modified):
    result = dict(items=[], feeds={}, synced_at=None, source="Jira / Appfire", errors=[], raw_count=0)
    team_scope = load_team_scope()
    if team_scope:
        result["team_scope"] = {"configured": True, "synced_at": team_scope.get("synced_at"),
                                "members": len(team_scope["account_ids"]), "team_ids": team_scope.get("team_ids", [])}
    else:
        # Falha fechada: nenhum nome atribuído é exibido até existir um cache válido.
        team_scope = {"account_ids": set(), "users": {}}
        result["team_scope"] = {"configured": False, "members": 0}
        result["errors"].append("Equipes da área ainda não sincronizadas. Configure as credenciais Atlassian e atualize os dados do Jira.")
    if not modified:
        result["errors"].append("Não foram encontrados os dados necessários: base Jira ausente.")
        return result
    try:
        with duckdb.connect(path, read_only=True) as con:
            tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
            if "snapshot_meta" in tables:
                stamp, report = con.execute("SELECT CAST(synced_at AS VARCHAR), report FROM snapshot_meta LIMIT 1").fetchone()
                result["synced_at"] = date_value(stamp)
                result["feeds"] = json.loads(report)
                feeds = [(feed, feed + "_") for feed in result["feeds"] if result["feeds"][feed]["state"] != "not_configured"]
            else:
                result["source"] = "Jira / Appfire · base local anterior"
                stamp_rows = rows(con, "meta_sync", tables)
                result["synced_at"] = date_value(stamp_rows[0]["last_sync"]) if stamp_rows else None
                result["feeds"] = {"regras": {"state": "partial"}, "procedimentos": {"state": "not_configured"}}
                result["errors"].append("Histórico não encontrado na base local anterior. Execute a sincronização da tela principal.")
                feeds = [("regras", "")]
            as_of = result["synced_at"] or datetime.now(timezone.utc)
            for feed, prefix in feeds:
                issues = rows(con, prefix + "issues", tables)
                result["raw_count"] += len(issues)
                result["items"].extend(build_items(issues, rows(con, prefix + "history", tables),
                    rows(con, prefix + "comments", tables), rows(con, prefix + "subtarefas", tables), feed, as_of, team_scope))
                for missing in result["feeds"][feed].get("errors", []):
                    result["errors"].append(f"Não foi possível consultar {missing} no feed {feed}; os indicadores relacionados estão incompletos.")
    except duckdb.Error:
        result["items"] = []
        result["errors"].append("Não foi possível ler a base Jira. Confira a sincronização e se o arquivo está disponível.")
    return result
