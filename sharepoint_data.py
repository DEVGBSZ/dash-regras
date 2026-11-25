"""Sincroniza e normaliza a aba Acompanhamento Cartas da planilha oficial."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
import unicodedata
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from zipfile import is_zipfile

import requests
from openpyxl import load_workbook

try:
    import truststore
except ImportError:  # Compatibilidade temporária com executáveis ainda não reconstruídos.
    truststore = None
else:
    truststore.inject_into_ssl()


ROOT = Path(__file__).resolve().parent
SHEET_NAME = "Acompanhamento Cartas"
DEFAULT_WORKBOOK_PATH = Path(
    r"\\AGM\GEREG\GRPC\09.Administrativo\atualização de planilha de demandas GRPC.xlsm"
)
DEFAULT_SHAREPOINT_URL = (
    "https://1drv.ms/x/c/dc200478f88d8a86/"
    "IQDN7yQGQbDVS4nVHS2EMi-TAfiI8DJ6gYoXmitB5znEANo"
)
DEFAULT_CACHE = ROOT / "sharepoint_cards_cache.json"


def _text(value):
    return "" if value is None else str(value).strip()


def _normal(value):
    return "".join(
        char for char in unicodedata.normalize("NFKD", _text(value).casefold())
        if not unicodedata.combining(char)
    )


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = _text(value)
    if not raw:
        return None
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(raw.split(" ")[0], pattern).date()
        except ValueError:
            continue
    return None


def _date_label(value):
    parsed = _date_value(value)
    return parsed.strftime("%d/%m/%Y") if parsed else None


def _display_value(value):
    """Formata datas sem descartar prazos expressos como número ou texto."""
    return _date_label(value) or _text(value) or None


def _tone(status):
    normalized = _normal(status)
    if any(term in normalized for term in ("aguard", "desenvolvimento", "recebida")):
        return "orange"
    if any(term in normalized for term in ("enviada", "conhecimento", "conclu")):
        return "blue"
    return "purple"


def _cache_path():
    return Path(os.environ.get("SHAREPOINT_CARDS_CACHE_PATH", DEFAULT_CACHE))


def _workbook_path():
    configured = os.environ.get("LETTERS_WORKBOOK_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_WORKBOOK_PATH


def _enabled(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "sim", "on"}


def _read_network_workbook():
    """Lê o arquivo compartilhado diretamente para memória, sem cópia local."""
    path = _workbook_path()
    retries = max(1, int(os.environ.get("LETTERS_WORKBOOK_READ_RETRIES", "5")))
    last_error = None
    for attempt in range(retries):
        try:
            before = path.stat()
            content = path.read_bytes()
            after = path.stat()
            stable = (
                before.st_size == after.st_size == len(content)
                and before.st_mtime_ns == after.st_mtime_ns
            )
            if stable and is_zipfile(BytesIO(content)):
                return BytesIO(content), path, after
            last_error = OSError("A planilha foi alterada durante a leitura.")
        except OSError as error:
            last_error = error
        if attempt + 1 < retries:
            time.sleep(0.5)
    raise RuntimeError(
        f"Não foi possível ler a planilha compartilhada em {path}."
    ) from last_error


def extract_letters(workbook):
    """Converte somente a aba de cartas em registros próprios para o dashboard."""
    book = load_workbook(workbook, read_only=True, data_only=True, keep_vba=False)
    if SHEET_NAME not in book.sheetnames:
        raise ValueError(f"A aba {SHEET_NAME!r} não foi encontrada na planilha.")
    sheet = book[SHEET_NAME]
    rows = sheet.iter_rows(values_only=True)
    headers = next(rows, ())
    columns = {_normal(value): index for index, value in enumerate(headers) if _text(value)}

    def value(row, header):
        index = columns.get(_normal(header))
        return row[index] if index is not None and index < len(row) else None

    letters = []
    for row_number, row in enumerate(rows, start=2):
        subject = _text(value(row, "ASSUNTO"))
        process = _text(value(row, "PROCESSO"))
        status = _text(value(row, "STATUS CARTA")) or "Status não informado"
        if not subject and not process:
            continue
        owner = _text(value(row, "PONTO FOCAL"))
        participants = _text(value(row, "PARTICIPANTES"))
        letter_type = _text(value(row, "TIPO"))
        front = _text(value(row, "FRENTE"))
        details = [part for part in (letter_type, owner, process) if part]
        letters.append({
            "id": process or f"carta-{row_number}",
            "title": subject or f"Carta {process}",
            "status": status,
            "description": " · ".join(details) or "Dados da planilha de acompanhamento",
            "tone": _tone(status),
            "icon": "fa-envelope-open-text",
            "process": process or None,
            "front": front or None,
            "owner": owner or None,
            "participants": participants or None,
            "type": letter_type or None,
            "received_date": _display_value(value(row, "DATA DE RECEBIMENTO")),
            "planned_send": _display_value(value(row, "ENVIO PREVISTO")),
            "regulatory_deadline": _display_value(value(row, "PRAZO REGULATÓRIO")),
            "source": SHEET_NAME,
        })
    book.close()
    return letters


def _graph_token():
    tenant = os.environ.get("MICROSOFT_TENANT_ID", "").strip()
    client = os.environ.get("MICROSOFT_CLIENT_ID", "").strip()
    secret = os.environ.get("MICROSOFT_CLIENT_SECRET", "").strip()
    if not all((tenant, client, secret)):
        raise RuntimeError(
            "Configure MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID e MICROSOFT_CLIENT_SECRET "
            "para sincronizar o SharePoint no servidor."
        )
    response = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={"client_id": client, "client_secret": secret,
              "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"},
        timeout=45,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _share_id():
    share_url = os.environ.get("SHAREPOINT_FILE_URL", DEFAULT_SHAREPOINT_URL).strip()
    return "u!" + base64.urlsafe_b64encode(share_url.encode()).decode().rstrip("=")


def _download_anonymous():
    """Baixa um link público do OneDrive diretamente, com validação TLS ativa."""
    share_url = os.environ.get("SHAREPOINT_FILE_URL", DEFAULT_SHAREPOINT_URL).strip()
    separator = "&" if "?" in share_url else "?"
    response = requests.get(
        f"{share_url}{separator}download=1&dashboard_refresh={time.time_ns()}",
        headers={"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"},
        timeout=90,
        allow_redirects=True,
    )
    response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise ValueError("O link compartilhado não retornou um arquivo Excel.")
    return BytesIO(response.content)


def _download_with_application():
    """Usa credenciais de aplicação, apropriadas para o servidor."""
    token = _graph_token()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})
    response = session.get(
        f"https://graph.microsoft.com/v1.0/shares/{_share_id()}/driveItem/content",
        timeout=90,
    )
    response.raise_for_status()
    return BytesIO(response.content)


def _download_with_local_graph_session():
    """Reutiliza a sessão delegada do Microsoft Graph no Windows, sem exportar token."""
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("As credenciais Microsoft do servidor não estão configuradas.")
    uri = f"https://graph.microsoft.com/v1.0/shares/{_share_id()}/driveItem/content"
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.Graph.Authentication
$context = Get-MgContext
if ($null -eq $context) {{ throw 'NO_GRAPH_CONTEXT' }}
$response = Invoke-MgGraphRequest -Method GET -Uri '{uri}' -OutputType HttpResponseMessage
$bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
[Console]::Out.Write([Convert]::ToBase64String($bytes))
"""
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", "-"],
        input=script,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise RuntimeError(
            "Autenticação do SharePoint necessária. Execute autenticar_sharepoint.cmd uma vez."
        )
    try:
        return BytesIO(base64.b64decode(result.stdout.strip(), validate=True))
    except ValueError as error:
        raise RuntimeError("A sessão Microsoft não retornou uma planilha válida.") from error


def _download_from_graph():
    """Baixa o conteúdo atual sem criar cópia local da planilha."""
    try:
        return _download_anonymous()
    except (requests.RequestException, ValueError):
        pass
    credentials = (
        os.environ.get("MICROSOFT_TENANT_ID", "").strip(),
        os.environ.get("MICROSOFT_CLIENT_ID", "").strip(),
        os.environ.get("MICROSOFT_CLIENT_SECRET", "").strip(),
    )
    if all(credentials):
        return _download_with_application()
    return _download_with_local_graph_session()


def _write_cache(letters, source, source_path=None, source_modified_at=None):
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"synced_at": datetime.now().astimezone().isoformat(), "source": source,
               "sheet": SHEET_NAME, "letters": letters}
    if source_path:
        payload["source_path"] = str(source_path)
    if source_modified_at:
        payload["source_modified_at"] = source_modified_at
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return payload


def sync_sharepoint_letters(progress=None):
    """Lê a planilha da rede em memória e troca o cache após sucesso completo."""
    if progress:
        progress("Lendo a planilha de cartas na rede Z…")
    try:
        workbook, path, file_info = _read_network_workbook()
        source = f"Rede compartilhada · {SHEET_NAME}"
        modified_at = datetime.fromtimestamp(file_info.st_mtime).astimezone().isoformat()
    except RuntimeError:
        if not _enabled("LETTERS_ALLOW_REMOTE_FALLBACK", default=os.name != "nt"):
            raise
        if progress:
            progress("Rede Z indisponível; usando o fallback remoto…")
        workbook, path, modified_at = _download_from_graph(), None, None
        source = f"OneDrive · {SHEET_NAME}"
    if progress:
        progress("Lendo Acompanhamento Cartas…")
    letters = extract_letters(workbook)
    return _write_cache(letters, source, path, modified_at)


def load_letters():
    """Lê somente o último cache obtido de uma fonte oficial reconhecida."""
    path = _cache_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if str(payload.get("source", "")).startswith(
                ("Rede compartilhada", "OneDrive", "SharePoint")
            ):
                return payload.get("letters", [])
        except (OSError, ValueError, TypeError):
            pass
    return []


def source_signature():
    path = _cache_path()
    return path.stat().st_mtime_ns if path.exists() else 0
