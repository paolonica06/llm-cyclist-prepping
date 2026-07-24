"""CoachAgent: genera e mantiene un Piano vivo verso un obiettivo metrico datato.

Pattern trasversale degli agenti (`run(...)` + ramo LLM/euristico, **mai
eccezione**): senza LLM (offline) la generazione degrada a una periodizzazione
euristica deterministica. Il Piano nasce sempre in stato PROPOSED (proponi-poi-
approva); la transizione ad ACTIVE avviene solo via `accept` → `promote_plan`.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..athlete_metrics import (assessment_gap_to_goal, freeze_athlete_data_citation,
                              freeze_citation, medical_boundary_flag,
                              overload_guardrail)
from ..athlete_models import (Assessment, Athlete, EvidenceCitation, MetricGoal,
                             PlanStatus, Prescription, ProvenanceKind,
                             TrainingBlock, TrainingPlan, make_block_id,
                             make_plan_id)
from ..config import get_settings
from ..db import Database
from ..llm import get_llm
from ..models import AthleteProfile
from ..retrieval import RetrievalResult, retrieve

_COACH_SYSTEM = "Sei un preparatore ciclistico scientifico. Rispondi SOLO con JSON."

# Direzioni "in conflitto" con l'evidenza a supporto: da conservare come testo.
_CONFLICT_DIRECTIONS = {"negative", "mixed"}

_DISCLAIMER = "Questo è un piano-ipotesi generato automaticamente, non una prescrizione medica."


class CoachAgent:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm()

    def run(self, athlete_id: str, goal: MetricGoal,
            profile: Optional[AthleteProfile] = None) -> TrainingPlan:
        assessments = self.db.list_assessments(athlete_id)
        start = (goal.start if goal.start is not None
                 else self._baseline_from_assessments(assessments, goal))
        prev_active = self.db.active_plan(athlete_id)
        plan = None
        if self.llm.available:
            plan = self._llm_generate_plan(athlete_id, goal, start, profile, prev_active)  # Task 6
        if plan is None:
            plan = self._heuristic_generate_plan(athlete_id, goal, start, prev_active)
        self._apply_guardrails_and_disclaimer(plan, profile)
        plan.status = PlanStatus.PROPOSED
        if prev_active is not None:
            plan.supersedes_id = prev_active.id
        self._supersede_open_proposals(athlete_id)       # al più un PROPOSED
        self.db.save_plan(plan)
        return plan

    def accept(self, plan_id: str) -> TrainingPlan:
        return self.db.promote_plan(plan_id)

    # -- interni ---------------------------------------------------------- #
    def _baseline_from_assessments(self, assessments, goal) -> Optional[float]:
        vals = [a.value for a in assessments if a.value is not None]
        return vals[-1] if vals else None

    def _next_proposed_version(self, athlete_id: str) -> int:
        non_proposed = [p for p in self.db.list_plans(athlete_id)
                        if p.status is not PlanStatus.PROPOSED]
        base = max((p.version for p in non_proposed), default=0)
        return base + 1

    def _supersede_open_proposals(self, athlete_id: str) -> None:
        for p in self.db.list_plans(athlete_id, status=PlanStatus.PROPOSED.value):
            p.status = PlanStatus.SUPERSEDED
            self.db.save_plan(p)

    def _apply_guardrails_and_disclaimer(self, plan: TrainingPlan, profile) -> None:
        notes = [_DISCLAIMER]
        constraints = list(getattr(profile, "constraints", []) or [])
        med = medical_boundary_flag(constraints)
        if med:
            notes.append(med)
        plan.notes = ("\n".join(notes) if not plan.notes
                      else plan.notes + "\n" + "\n".join(notes))

    def _heuristic_generate_plan(self, athlete_id, goal, start, prev_active) -> TrainingPlan:
        version = self._next_proposed_version(athlete_id)
        plan = TrainingPlan(
            id=make_plan_id(athlete_id, version), athlete_id=athlete_id, version=version,
            status=PlanStatus.PROPOSED, target_metric_type=goal.metric_type,
            target_metric_start=start, target_metric_value=goal.target,
            target_metric_date=goal.target_date,
        )
        # Periodizzazione a ritroso deterministica: 3 blocchi (base→sviluppo→taper).
        gap = assessment_gap_to_goal(start, goal.target) or 0.0
        goals = ["base", "sviluppo", "taper"]
        blocks: List[TrainingBlock] = []
        for i, g in enumerate(goals):
            bid = make_block_id(plan.id, i)
            pres = [Prescription(
                description=f"Seduta {g}", target_watts=(start or 0.0) * (0.9 + 0.05 * i),
                duration_s=3600, provenance=ProvenanceKind.HEURISTIC)]
            blocks.append(TrainingBlock(id=bid, plan_id=plan.id, goal=g, order=i,
                                        prescriptions=pres, provenance=ProvenanceKind.HEURISTIC))
        plan.blocks = blocks
        return plan

    # -- ramo LLM (Task 6) ------------------------------------------------ #
    def _llm_generate_plan(self, athlete_id, goal, start, profile, prev_active):
        try:
            # Le scelte strategiche seminano le query del Retriever: partiamo dagli
            # scopi fisiologici canonici per obiettivo e recuperiamo l'evidenza,
            # poi la passiamo all'LLM che costruisce il piano.
            blocks_spec = self._strategic_choices(goal)
            choices = self._retrieve_for_choices(athlete_id, goal, blocks_spec)
            prompt = self._build_prompt(athlete_id, goal, start, profile, choices)
            data = self.llm.complete_json(prompt=prompt, system=_COACH_SYSTEM)
            if not data:
                return None
            return self._build_plan_from_llm(data, athlete_id, goal, start)
        except Exception:
            return None                    # fallback silenzioso all'euristica

    def _strategic_choices(self, goal) -> List[Dict[str, str]]:
        """Scelte strategiche deterministiche (scopi fisiologici) verso l'obiettivo,
        ognuna con una query lessicale per sondare il Pozzo di Evidenza."""
        metric = goal.metric_type.value
        return [
            {"goal": "base", "strategy_query": f"aerobic base endurance training {metric} cyclists"},
            {"goal": "sviluppo", "strategy_query": f"interval training {metric} trained cyclists"},
            {"goal": "taper", "strategy_query": f"tapering peaking {metric} cyclists"},
        ]

    def _retrieve_for_choices(self, athlete_id, goal, blocks_spec):
        """Materializza il Retriever per ciascuna scelta strategica. Ritorna una
        lista parallela con positives/conflicts/query."""
        athlete = self.db.get_athlete(athlete_id)
        out = []
        for spec in blocks_spec:
            query = (spec.get("strategy_query") or spec.get("goal")
                     or goal.metric_type.value)
            results: List[RetrievalResult] = retrieve(self.db, query, athlete=athlete, k=8)
            positives = [r for r in results if r.direction == "positive"]
            conflicts = [r for r in results if r.direction in _CONFLICT_DIRECTIONS]
            out.append({"positives": positives, "conflicts": conflicts, "query": query})
        return out

    def _build_prompt(self, athlete_id, goal, start, profile, choices) -> str:
        athlete = self.db.get_athlete(athlete_id)
        memos = self.db.list_memos(athlete_id) if hasattr(self.db, "list_memos") else []
        retrieved = [
            {
                "query": c["query"],
                "positive_evidence": [self._serialize_result(r) for r in c["positives"]],
                "conflicting_evidence": [self._serialize_result(r) for r in c["conflicts"]],
            }
            for c in choices
        ]
        profile_txt = self._serialize_profile(profile)
        memos_txt = json.dumps(
            [{"block_id": m.block_id, "verdict": getattr(m.verdict, "value", str(m.verdict))}
             for m in (memos or [])],
            ensure_ascii=False,
        )
        return (
            "Costruisci un piano di allenamento periodizzato a ritroso verso "
            f"l'obiettivo {goal.metric_type.value}: da {start} a {goal.target} "
            f"entro {goal.target_date}.\n"
            f"Evidenza recuperata (per blocco): {json.dumps(retrieved, ensure_ascii=False)}\n"
            f"Profilo atleta: {profile_txt}\n"
            f"Memo di trasferibilità pregressi: {memos_txt}\n"
            "Regole: la strategia di un blocco può essere 'study' SOLO se supportata "
            "da positive_evidence; i numeri (watt, durate) NON sono mai 'study' "
            "(derivali dallo stato dell'atleta). Conserva i conflitti.\n"
            'Rispondi con JSON: {"blocks": [{"goal": "...", "provenance": '
            '"study|heuristic", "strategy_query": "...", "prescriptions": '
            '[{"description": "...", "target_watts": 0, "duration_s": 0, '
            '"reps": 0, "provenance": "heuristic|athlete_data"}]}]}'
        )

    @staticmethod
    def _serialize_result(r: RetrievalResult) -> Dict[str, Any]:
        rec = r.record
        return {
            "record_id": rec.id, "title": rec.title, "doi": rec.doi,
            "direction": r.direction, "score": r.score, "quality": r.quality,
        }

    @staticmethod
    def _serialize_profile(profile) -> str:
        if profile is None:
            return "n/d"
        try:
            return profile.model_dump_json()
        except Exception:
            return str(profile)

    def _build_plan_from_llm(self, data, athlete_id, goal, start) -> TrainingPlan:
        version = self._next_proposed_version(athlete_id)
        plan = TrainingPlan(
            id=make_plan_id(athlete_id, version), athlete_id=athlete_id, version=version,
            status=PlanStatus.PROPOSED, target_metric_type=goal.metric_type,
            target_metric_start=start, target_metric_value=goal.target,
            target_metric_date=goal.target_date,
        )
        athlete = self.db.get_athlete(athlete_id)
        blocks_spec = data.get("blocks") or []
        blocks: List[TrainingBlock] = []
        for i, spec in enumerate(blocks_spec):
            bid = make_block_id(plan.id, i)
            query = (spec.get("strategy_query") or spec.get("goal")
                     or goal.metric_type.value)
            results = retrieve(self.db, query, athlete=athlete, k=8)
            positives = [r for r in results if r.direction == "positive"]
            conflicting = [r for r in results if r.direction in _CONFLICT_DIRECTIONS]

            citations = self._freeze_positives(positives)
            # Un blocco è STUDY SOLO se ha ≥1 citazione verificata (SEAM 5):
            # altrimenti degrada a HEURISTIC anche se l'LLM ha detto "study".
            wants_study = str(spec.get("provenance", "")).lower() == "study"
            if wants_study and citations:
                block_prov = ProvenanceKind.STUDY
            else:
                block_prov = ProvenanceKind.HEURISTIC   # mai STUDY senza citazione (SEAM 5)
            # Conflitti conservati come testo (conflict-aware, invariante SEAM).
            conflicts = self._conflicts_as_text(conflicting)

            prescriptions = self._build_prescriptions(spec.get("prescriptions") or [], citations)
            blocks.append(TrainingBlock(
                id=bid, plan_id=plan.id, goal=str(spec.get("goal") or f"blocco-{i}"),
                order=i, prescriptions=prescriptions, provenance=block_prov,
                citations=citations, conflicts=conflicts,
            ))
        plan.blocks = blocks
        return plan

    @staticmethod
    def _freeze_positives(positives) -> List[EvidenceCitation]:
        cites: List[EvidenceCitation] = []
        for r in positives:
            try:
                cites.append(freeze_citation(r.record))   # solo evidenza verificata
            except ValueError:
                continue                                   # non citabile → salta
        return cites

    @staticmethod
    def _conflicts_as_text(conflicting) -> List[str]:
        out: List[str] = []
        for r in conflicting:
            rec = r.record
            label = rec.title or rec.doi or rec.id
            out.append(f"[{r.direction}] {label}")
        return out

    def _build_prescriptions(self, specs, block_citations) -> List[Prescription]:
        cite_ids = [c.record_id for c in block_citations if c.record_id]
        prescriptions: List[Prescription] = []
        for ps in specs:
            # Regola del range: i NUMERI non sono mai STUDY. Mappa a
            # ATHLETE_DATA/HEURISTIC (mai STUDY, anche se l'LLM lo suggerisce).
            raw = str(ps.get("provenance", "")).lower()
            prov = (ProvenanceKind.ATHLETE_DATA if raw == "athlete_data"
                    else ProvenanceKind.HEURISTIC)
            prescriptions.append(Prescription(
                description=str(ps.get("description") or "Seduta"),
                target_watts=ps.get("target_watts"),
                duration_s=ps.get("duration_s"),
                reps=ps.get("reps"),
                provenance=prov,
                citation_ids=list(cite_ids),
            ))
        return prescriptions
