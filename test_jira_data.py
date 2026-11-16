"""Valida casos que podem produzir indicadores incorretos na integração Jira."""

import unittest

from jira_data import build_items, date_value, status_durations


def event(field, value, start="2026-10-01T12:00:00Z", **extra):
    return dict(chave="TEST-1", history_field_id=field, history_new_value=value,
                history_new_value_start=start, history_sequence=1, **extra)


class JiraMappingTests(unittest.TestCase):
    def item(self, history=(), **raw_values):
        raw = dict(chave="TEST-1", tipo_de_item="Registro de Demanda", resumo="Teste",
                   criado="2026-10-01T12:00:00Z", relator_name="Relator não é responsável")
        raw.update(raw_values)
        team_scope = {"account_ids": {"account-a"}, "users": {"account-a": "Pessoa A"}}
        return build_items(
            [raw], list(history), [], [], "regras",
            date_value("2026-11-04T12:00:00Z"), team_scope,
        )[0]

    def test_missing_values_are_not_invented(self):
        item = self.item()
        for field in ("owner", "status", "effort", "progress", "due", "overdue", "comment"):
            self.assertIsNone(item[field], field)
        self.assertFalse(item["participants_known"])

    def test_latest_cleared_values_do_not_restore_old_values(self):
        history = [event("duedate", "2026-10-02"), event("duedate", "", "2026-10-03T12:00:00Z"),
                   event("customfield_10068", "[Pessoa A]"), event("customfield_10068", "[]", "2026-10-03T12:00:00Z"),
                   event("assignee", "null", history_assignee="null", **{"current_assignee?": "Y"})]
        item = self.item(history)
        self.assertIsNone(item["due"])
        self.assertIsNone(item["owner"])
        self.assertEqual(item["participants"], [])
        self.assertTrue(item["participants_known"])

    def test_explicit_zero_progress_and_complexity_are_valid(self):
        item = self.item([event("customfield_14702", "0%"), event("customfield_10249", "🔴G")])
        self.assertEqual(item["progress"], 0)
        self.assertEqual(item["effort"], "G")

    def test_cancellation_is_not_an_open_item(self):
        item = self.item([event("status", "Cancelado", history_status="Cancelado", **{"current_status?": "Y"})])
        self.assertTrue(item["cancelled"])
        self.assertTrue(item["closed"])

    def test_deadline_is_evaluated_after_the_local_date(self):
        same_day = self.item([event("duedate", "2026-11-04")])
        previous_day = self.item([event("duedate", "2026-11-03")])
        self.assertFalse(same_day["overdue"])
        self.assertTrue(previous_day["overdue"])

    def test_status_reentry_deduplication_and_resolution_boundary(self):
        history = [dict(history_status="Aberto", status_start="2026-10-01T12:00:00Z", status_end="2026-10-02T12:00:00Z"),
                   dict(history_status="Em análise", status_start="2026-10-02T12:00:00Z", status_end="2026-10-04T12:00:00Z"),
                   dict(history_status="Aberto", status_start="2026-10-04T12:00:00Z", status_end="2026-10-06T12:00:00Z")]
        history.append(dict(history[0]))
        days, complete = status_durations(history, date_value("2026-10-01T12:00:00Z"), date_value("2026-10-05T12:00:00Z"))
        self.assertEqual(days, {"Aberto": 2, "Em análise": 2})
        self.assertTrue(complete)

    def test_incomplete_history_is_identified(self):
        days, complete = status_durations([
            dict(history_status="Em análise", status_start="2026-10-03T12:00:00Z", status_end=None)],
            date_value("2026-10-01T12:00:00Z"), date_value("2026-10-05T12:00:00Z"))
        self.assertFalse(complete)
        self.assertEqual(days, {"Em análise": 2})


if __name__ == "__main__":
    unittest.main()
