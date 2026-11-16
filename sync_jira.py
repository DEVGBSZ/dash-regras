"""Atualiza a base isolada da tela principal com leituras do feed Jira existente."""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
from etl import fetch_odata_entity, get_feed_configuration

SNAPSHOT_PATH = Path(os.environ.get("JIRA_SNAPSHOT_PATH", APP_DIR / "jira_snapshot.duckdb"))
ENTITIES = {"issues": "Issues", "comments": "Comments", "history": "History",
            "categorias": "Categorias", "subtarefas": "Subtarefas", "palavras_chave": "Palavras-chave"}


def sync_snapshot(progress_callback=None):
    """Somente GET no Jira; nÃ£o altera o banco do dashboard original."""
    frames = {}
    report = {}
    completed = 0
    total = len(ENTITIES) * 2

    def progress(message):
        if progress_callback:
            progress_callback(message, completed, total)

    with requests.Session() as session:
        for feed in ("regras", "procedimentos"):
            try:
                url, _ = get_feed_configuration(feed)
            except RuntimeError:
                report[feed] = {"state": "not_configured"}
                completed += len(ENTITIES)
                progress(f"Feed de {feed} nÃ£o configurado; seguindo com os demais dados.")
                continue
            counts, errors = {}, []
            for table, entity in ENTITIES.items():
                progress(f"Atualizando {feed}: {entity}â€¦")
                try:
                    frame = fetch_odata_entity(entity, session, feed_base_url=url)
                    counts[table] = len(frame)
                    if len(frame.columns):
                        frames[f"{feed}_{table}"] = frame
                except Exception:
                    # NÃ£o registrar exceÃ§Ãµes HTTP que possam conter a URL autenticada.
                    errors.append(table)
                    print(f"NÃ£o foi possÃ­vel ler {feed}/{table}.")
                completed += 1
                progress(f"{feed}: {entity} concluÃ­do.")
            if not counts.get("issues"):
                raise RuntimeError(f"A leitura de issues de {feed} falhou; base anterior preservada.")
            report[feed] = {"state": "partial" if errors else "ok", "counts": counts, "errors": errors}
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="jira_snapshot_", suffix=".duckdb", dir=SNAPSHOT_PATH.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    # O DuckDB cria o arquivo; um arquivo vazio prÃ©-existente nÃ£o Ã© uma base vÃ¡lida.
    temporary_path.unlink()
    try:
        with duckdb.connect(str(temporary_path)) as con:
            for (table,) in con.execute("SHOW TABLES").fetchall():
                con.execute('DROP TABLE "' + table.replace('"', '""') + '"')
            for table, frame in frames.items():
                con.register("incoming", frame)
                con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM incoming')
                con.unregister("incoming")
            con.execute("CREATE TABLE snapshot_meta (synced_at TIMESTAMPTZ, report VARCHAR)")
            con.execute("INSERT INTO snapshot_meta VALUES (?, ?)", [datetime.now(timezone.utc), json.dumps(report)])
        os.replace(temporary_path, SNAPSHOT_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)
    if progress_callback:
        progress_callback("AtualizaÃ§Ã£o concluÃ­da.", total, total)
    return report


if __name__ == "__main__":
    try:
        print(json.dumps(sync_snapshot(), ensure_ascii=False))
    except Exception as error:
        print(f"SincronizaÃ§Ã£o nÃ£o concluÃ­da ({type(error).__name__}); confira a configuraÃ§Ã£o e a conexÃ£o.")
        sys.exit(1)

