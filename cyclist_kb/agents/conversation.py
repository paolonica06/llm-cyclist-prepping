"""CoachChatAgent (Fase E): «chiedi al preparatore» in linguaggio naturale.

Risponde a una domanda decisionale fondendo, come impone il Protocollo decisioni
atleta (CLAUDE.md): (1) dati misurati recenti dell'atleta, (2) piano attivo,
(3) evidenza verificata pertinente dal Pozzo (retriever). Ramo LLM (`complete_text`)
+ **fallback euristico deterministico** (offline): mai un'eccezione, sempre una
risposta ancorata e con la provenienza marcata (`studi`/`dati_atleta`/`euristica`).
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..athlete_models import MetricType
from ..db import Database
from ..llm import get_llm
from ..retrieval import retrieve

# Metriche mostrate nello snapshot (ordine di presentazione).
_SNAPSHOT_METRICS = [
    MetricType.CTL, MetricType.ATL, MetricType.TSB, MetricType.HRV,
    MetricType.RESTING_HR, MetricType.SLEEP, MetricType.WEIGHT,
]
_RECENT_WINDOW = 14                      # trend: media degli ultimi ~14 punti

_CHAT_SYSTEM = (
    "Sei il preparatore ciclistico scientifico di questo atleta. Rispondi in italiano, "
    "concreto e onesto. Regole: fonda la risposta sui DATI misurati e sull'EVIDENZA "
    "forniti; distingui «sei costretto a X dai dati» da «X è la scelta migliore»; marca "
    "la provenienza (studi / dati_atleta / euristica); niente numeri inventati; se emergono "
    "sintomi o dubbi clinici fermati e rimanda a un professionista."
)

_DISCLAIMER = ("Questa è una sintesi automatica dei tuoi dati e dell'evidenza disponibile, "
               "non una prescrizione medica. Per sintomi o dubbi clinici fermati e consulta "
               "un professionista.")


class EvidenceRef(BaseModel):
    title: Optional[str] = None
    doi: Optional[str] = None
    direction: str = "unclear"
    score: float = 0.0


class ChatAnswer(BaseModel):
    """Risposta del preparatore + il contesto su cui è fondata (auditabile)."""

    question: str
    athlete_id: Optional[str] = None
    answer: str
    snapshot: Dict[str, Any] = Field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None
    evidence: List[EvidenceRef] = Field(default_factory=list)
    used_llm: bool = False


class CoachChatAgent:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.llm = get_llm()

    def ask(self, question: str, athlete_id: Optional[str] = None,
            as_of: Optional[str] = None) -> ChatAnswer:
        # "as_of" = giorno di riferimento (oggi di default): esclude le PROIEZIONI
        # future (intervals.icu proietta CTL/ATL/TSB dal pianificato), altrimenti
        # "come sto?" leggerebbe una forma di mesi avanti invece di quella di oggi.
        as_of = as_of or datetime.date.today().isoformat()
        snapshot = self._snapshot(athlete_id, as_of) if athlete_id else {}
        plan = self._active_plan_summary(athlete_id) if athlete_id else None
        athlete = self.db.get_athlete(athlete_id) if athlete_id else None
        results = retrieve(self.db, question, athlete=athlete, k=5)
        evidence = [
            EvidenceRef(title=r.record.title, doi=r.record.doi,
                        direction=r.direction, score=r.score)
            for r in results
        ]

        answer, used_llm = None, False
        if self.llm.available:
            answer = self._llm_answer(question, snapshot, plan, results)
            used_llm = answer is not None
        if not answer:
            answer = self._heuristic_answer(question, snapshot, plan, results)

        return ChatAnswer(
            question=question, athlete_id=athlete_id, answer=answer,
            snapshot=snapshot, plan=plan, evidence=evidence, used_llm=used_llm,
        )

    # -- Contesto ----------------------------------------------------------- #
    def _snapshot(self, athlete_id: str, as_of: str) -> Dict[str, Any]:
        """Ultimo valore + media recente (trend) per ogni grandezza chiave, fino a
        `as_of` incluso (le proiezioni future sono escluse)."""
        snap: Dict[str, Any] = {}
        for metric in _SNAPSHOT_METRICS:
            points = self.db.list_timeseries(athlete_id, metric_type=metric.value)
            vals = [p.value for p in points
                    if p.value is not None and p.date <= as_of]
            if not vals:
                continue
            recent = vals[-_RECENT_WINDOW:]
            snap[metric.value] = {
                "last": round(vals[-1], 2),
                "mean_recent": round(sum(recent) / len(recent), 2),
                "n": len(vals),
            }
        return snap

    def _active_plan_summary(self, athlete_id: str) -> Optional[Dict[str, Any]]:
        plan = self.db.active_plan(athlete_id)
        if plan is None:
            return None
        return {
            "id": plan.id,
            "goal": (plan.target_metric_type.value if plan.target_metric_type else None),
            "target": plan.target_metric_value,
            "by": plan.target_metric_date,
            "blocks": [
                {"goal": b.goal, "planned_start": b.planned_start,
                 "planned_end": b.planned_end, "provenance": b.provenance.value}
                for b in plan.blocks
            ],
        }

    # -- Ramo LLM ----------------------------------------------------------- #
    def _llm_answer(self, question, snapshot, plan, results) -> Optional[str]:
        try:
            evidence = [
                {"title": r.record.title, "direction": r.direction,
                 "score": r.score, "quality": r.quality}
                for r in results
            ]
            prompt = (
                f"Domanda dell'atleta: «{question}».\n"
                f"Dati misurati recenti (dati_atleta): {json.dumps(snapshot, ensure_ascii=False)}\n"
                f"Piano attivo: {json.dumps(plan, ensure_ascii=False)}\n"
                f"Evidenza verificata pertinente (studi): {json.dumps(evidence, ensure_ascii=False)}\n"
                "Rispondi da preparatore, ancorando ai dati e all'evidenza sopra, con la "
                "provenienza marcata e il confine medico se pertinente."
            )
            return self.llm.complete_text(prompt=prompt, system=_CHAT_SYSTEM)
        except Exception:
            return None

    # -- Fallback euristico deterministico ---------------------------------- #
    def _heuristic_answer(self, question, snapshot, plan, results) -> str:
        parts: List[str] = []
        if snapshot:
            bits = []
            for metric, v in snapshot.items():
                trend = "→"
                if v["last"] > v["mean_recent"]:
                    trend = "↑"
                elif v["last"] < v["mean_recent"]:
                    trend = "↓"
                bits.append(f"{metric}={v['last']:g} {trend} (media {v['mean_recent']:g})")
            parts.append("Dati misurati (dati_atleta): " + "; ".join(bits) + ".")
        else:
            parts.append("Dati misurati (dati_atleta): nessuna serie disponibile per l'atleta.")

        if plan and plan.get("goal"):
            parts.append(
                f"Piano attivo (dati_atleta): obiettivo {plan['goal']} → {plan.get('target')} "
                f"entro {plan.get('by')}, {len(plan.get('blocks') or [])} blocchi."
            )

        if results:
            pos = sum(1 for r in results if r.direction == "positive")
            conf = sum(1 for r in results if r.direction in ("negative", "mixed"))
            titles = "; ".join((r.record.title or r.record.doi or r.record.id) for r in results[:3])
            parts.append(
                f"Evidenza (studi): {len(results)} studi verificati pertinenti "
                f"({pos} a favore, {conf} in conflitto). In cima: {titles}."
            )
        else:
            parts.append("Evidenza (studi): nessuno studio verificato pertinente alla domanda nel pozzo.")

        parts.append(
            "Sintesi (euristica): incrocia i dati misurati con l'evidenza sopra prima di "
            "decidere; questa risposta non distingue da sola «costretto dai dati» da «scelta "
            "migliore» — serve il tuo giudizio sul contesto."
        )
        parts.append(_DISCLAIMER)
        return "\n".join(parts)
