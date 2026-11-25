"""Valida a leitura da aba de cartas e a sincronização sem cópia da planilha."""

import tempfile
import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook

from sharepoint_data import extract_letters, load_letters, sync_sharepoint_letters


def workbook_bytes():
    book = Workbook()
    sheet = book.active
    sheet.title = "Acompanhamento Cartas"
    sheet.append([
        None, "PROCESSO", "FRENTE", "PONTO FOCAL", "PARTICIPANTES", "ASSUNTO",
        "TIPO", "STATUS CARTA", "DATA DE RECEBIMENTO", "ENVIO PREVISTO",
        "PRAZO REGULATÓRIO",
    ])
    sheet.append([
        None, "03020.000008/2026-73", "Regras e PdC", "Bianca Tavela",
        "Bianca, Thais", "Proposta de Regras", "Ofício", "Enviada",
        datetime(2026, 9, 10), datetime(2026, 9, 25), 15,
    ])
    content = BytesIO()
    book.save(content)
    content.seek(0)
    return content


class SharePointDataTests(unittest.TestCase):
    def test_extracts_expected_columns(self):
        letters = extract_letters(workbook_bytes())

        self.assertEqual(len(letters), 1)
        self.assertEqual(letters[0]["process"], "03020.000008/2026-73")
        self.assertEqual(letters[0]["title"], "Proposta de Regras")
        self.assertEqual(letters[0]["received_date"], "10/09/2026")
        self.assertEqual(letters[0]["planned_send"], "25/09/2026")
        self.assertEqual(letters[0]["regulatory_deadline"], "15")

    def test_sync_uses_memory_and_persists_only_normalized_records(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "letters.json"
            with (
                patch.dict("os.environ", {"SHAREPOINT_CARDS_CACHE_PATH": str(cache)}),
                patch("sharepoint_data._read_network_workbook", side_effect=lambda: (
                    workbook_bytes(), Path(r"\\servidor\pasta\cartas.xlsm"),
                    SimpleNamespace(st_mtime=1_794_000_000),
                )),
            ):
                result = sync_sharepoint_letters()
                loaded = load_letters()

            self.assertTrue(cache.exists())
            self.assertEqual(result["letters"], loaded)
            self.assertTrue(result["source"].startswith("Rede compartilhada"))
            self.assertEqual(loaded[0]["title"], "Proposta de Regras")
            self.assertFalse(any(Path(folder).glob("*.xls*")))


if __name__ == "__main__":
    unittest.main()
