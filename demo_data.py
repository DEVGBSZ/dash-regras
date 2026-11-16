"""Cenário de apresentação separado da extração real do Jira."""

from datetime import datetime, timedelta
from functools import lru_cache

from jira_data import LOCAL_ZONE, get_data


def get_dataset(mode="real"):
    return demonstration_data() if mode == "demo" else get_data()


@lru_cache(maxsize=1)
def demonstration_data():
    people = ["Sarah", "Thais", "Matheus", "Rodrigo", "Bianca", "Luiz"]
    counts = [(4, 2), (3, 1), (2, 3), (5, 1), (2, 2), (3, 2)]
    titles = ["Consolidação das premissas", "Atualização dos procedimentos",
              "Revisão dos critérios de apuração", "Validação das regras de medição",
              "Ajustes no fluxo de contabilização", "Análise de contribuição dos agentes"]
    reference = datetime(2026, 11, 4, 12, tzinfo=LOCAL_ZONE)
    items = []
    for person_index, (person, quantities) in enumerate(zip(people, counts)):
        for kind, count in zip(["Demandas", "Consultas técnicas"], quantities):
            for j in range(count):
                n = len(items)
                queue = n % 4 == 3
                overdue = n % 7 == 6
                status = "Aberto" if queue else "Em andamento"
                if n in (2, 8, 16, 24):
                    status, queue = "Aguardando Aneel", False
                key = f"DEMO-{'CT' if kind == 'Consultas técnicas' else 'DEM'}-{101+n}"
                items.append(dict(
                    id=f"demo:{key}", key=key, title=titles[n % len(titles)] if kind == "Demandas" else f"Esclarecimento sobre {['medição', 'contabilização', 'liquidação'][j % 3]}",
                    kind=kind, topic="Regras" if n % 2 == 0 else "PdC", owner=person,
                    participants=[people[(person_index+1) % 6], people[(person_index+2) % 6]], participants_known=True,
                    effort=["P", "M", "G"][n % 3], status=status, closed=False, cancelled=False, queue=queue,
                    progress=0 if queue else [68, 42, 75, 30, 55][n % 5], progress_source="Percentual demonstrativo de andamento",
                    due=reference + timedelta(days=-3 if overdue else 5+j), due_source="Prazo demonstrativo", overdue=overdue,
                    regulatory_deadline=reference + timedelta(days=12+j) if kind == "Demandas" else None,
                    delivery_date=reference + timedelta(days=-3 if overdue else 5+j) if kind == "Demandas" else None,
                    end_date=reference + timedelta(days=-3 if overdue else 5+j) if kind == "Consultas técnicas" else None,
                    author="Rodrigo" if n % 2 == 0 else "Mariana",
                    comment="Revisei as premissas para o próximo alinhamento." if n % 2 == 0 else "Atualizei a proposta para validarmos os próximos passos.",
                    comment_date=reference-timedelta(days=1), created=reference-timedelta(days=30-n),
                    resolved=None, month=None, cycle=None, days={}, complete_history=False,
                ))
    for month, count in [(10, 24), (9, 18)]:
        for i in range(count):
            days = {"Fila": 1+i % 4, "Em andamento": 4+i % 9, "Em validação": 1+i % 3}
            resolved = datetime(2026, month, 1+i, 12, tzinfo=LOCAL_ZONE)
            key = f"DEMO-ENC-{month}-{i+1}"
            items.append(dict(
                id=f"demo:{key}", key=key, title=titles[i % len(titles)],
                kind="Consultas técnicas" if i % 3 == 0 else "Demandas", topic="Regras" if i % 2 == 0 else "PdC",
                owner=people[i % 6], participants=[people[(i+1) % 6]], participants_known=True,
                effort=["P", "M", "G"][(i // 3) % 3], status="Finalizado", closed=True, cancelled=False, queue=False,
                progress=100, progress_source="Percentual demonstrativo de andamento", due=resolved,
                due_source="Prazo demonstrativo", overdue=False, author=people[i % 6], comment="Entrega validada e concluída.",
                regulatory_deadline=resolved + timedelta(days=7) if i % 3 != 0 else None,
                delivery_date=resolved if i % 3 != 0 else None,
                end_date=resolved if i % 3 == 0 else None,
                comment_date=resolved, created=resolved-timedelta(days=sum(days.values())), resolved=resolved,
                month=f"2026-{month:02d}", cycle=sum(days.values()), days=days, complete_history=True,
            ))
    return dict(items=items, demo=True, feeds={}, synced_at=reference, source="Cenário demonstrativo",
                errors=[], raw_count=len(items), letters=[
                    {"title": "Aguarda assinatura de Cesar", "status": "Prioridade", "description": "Carta demonstrativa · aguarda próxima ação", "tone": "pink", "icon": "fa-pen-nib"},
                    {"title": "Ricardo", "status": "Acompanhar", "description": "Carta demonstrativa · verificar encaminhamento", "tone": "blue", "icon": "fa-user"},
                ])
