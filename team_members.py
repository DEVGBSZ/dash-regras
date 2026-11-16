"""Sincroniza e armazena os membros das equipes autorizadas da área."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests


APP_DIR = Path(__file__).resolve().parent
ORG_ID = os.environ.get("ATLASSIAN_ORG_ID", "ba61jb15-96bb-1kc7-ka88-k642k4jk16k3")
CLOUD_ID = os.environ.get("ATLASSIAN_CLOUD_ID", "dc84ad47-68dd-4be9-bc55-b820b2ab48b1")
TEAM_IDS = tuple(value.strip() for value in os.environ.get(
    "ATLASSIAN_TEAM_IDS",
    "7b3408c8-0503-49fa-b416-805600221ba4",
).split(",") if value.strip())
JIRA_SITE = os.environ.get("ATLASSIAN_JIRA_SITE", "https://centraldeservicosccee.atlassian.net").rstrip("/")
SNAPSHOT_PATH = Path(os.environ.get("JIRA_SNAPSHOT_PATH", APP_DIR / "jira_snapshot.duckdb"))
TEAM_CACHE_PATH = Path(os.environ.get("ATLASSIAN_TEAM_CACHE_PATH", SNAPSHOT_PATH.with_name("team_members_cache.json")))


class TeamSyncError(RuntimeError):
    pass


def load_team_scope():
    """Lê somente o último cache válido; nunca retorna um arquivo parcial."""
    try:
        payload = json.loads(TEAM_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    account_ids = {str(value).strip() for value in payload.get("account_ids", []) if str(value).strip()}
    users = {str(key).strip(): str(value).strip() for key, value in payload.get("users", {}).items()
             if str(key).strip() and str(value).strip()}
    if not account_ids:
        return None
    return {**payload, "account_ids": account_ids, "users": users,
            "names": {name.casefold() for name in users.values()}}


def _membership_id(value):
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    nested = value.get("member") if isinstance(value.get("member"), dict) else {}
    return str(value.get("accountId") or value.get("account_id") or value.get("id") or
               nested.get("accountId") or nested.get("id") or "").strip()


def _fetch_team_accounts(session, team_id, progress_callback=None):
    endpoint = f"{JIRA_SITE}/gateway/api/public/teams/v1/org/{ORG_ID}/teams/{team_id}/members"
    account_ids, cursor = set(), None
    while True:
        body = {"first": 50}
        if cursor:
            body["after"] = cursor
        response = session.post(endpoint, params={"siteId": CLOUD_ID}, json=body, timeout=(15, 60))
        response.raise_for_status()
        payload = response.json()
        values = payload.get("results") or payload.get("members") or []
        account_ids.update(filter(None, (_membership_id(value) for value in values)))
        page = payload.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
        if not cursor:
            break
    if progress_callback:
        progress_callback(f"Equipe sincronizada: {len(account_ids)} membros encontrados.")
    return account_ids


def _fetch_user_names(session, account_ids):
    users = {}
    ids = sorted(account_ids)
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        params = [("accountId", account_id) for account_id in chunk]
        params.extend((("startAt", 0), ("maxResults", len(chunk))))
        response = session.get(f"{JIRA_SITE}/rest/api/3/user/bulk", params=params, timeout=(15, 60))
        response.raise_for_status()
        payload = response.json()
        values = payload.get("values", []) if isinstance(payload, dict) else payload
        for user in values:
            account_id = str(user.get("accountId") or "").strip()
            display_name = str(user.get("displayName") or "").strip()
            if account_id and display_name:
                users[account_id] = display_name
    return users


def sync_team_scope(progress_callback=None):
    """Atualiza o cache de equipes; em erro, o cache anterior permanece intacto."""
    email = os.environ.get("ATLASSIAN_EMAIL", "").strip()
    token = os.environ.get("ATLASSIAN_API_TOKEN", "").strip()
    if not email or not token:
        raise TeamSyncError("Configure ATLASSIAN_EMAIL e ATLASSIAN_API_TOKEN no servidor.")
    if not TEAM_IDS:
        raise TeamSyncError("Nenhuma equipe foi configurada em ATLASSIAN_TEAM_IDS.")

    with requests.Session() as session:
        session.auth = (email, token)
        session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        account_ids = set()
        for team_id in TEAM_IDS:
            if progress_callback:
                progress_callback("Sincronizando membros das equipes da área…")
            account_ids.update(_fetch_team_accounts(session, team_id, progress_callback))
        if not account_ids:
            raise TeamSyncError("As equipes configuradas não retornaram membros.")
        users = _fetch_user_names(session, account_ids)

    payload = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": ORG_ID,
        "cloud_id": CLOUD_ID,
        "team_ids": list(TEAM_IDS),
        "account_ids": sorted(account_ids),
        "users": users,
    }
    TEAM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="team_members_", suffix=".json", dir=TEAM_CACHE_PATH.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
        os.replace(temporary_name, TEAM_CACHE_PATH)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return payload
