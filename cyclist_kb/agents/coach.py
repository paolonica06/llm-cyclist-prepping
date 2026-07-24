"""CoachAgent: genera e mantiene un Piano vivo verso un obiettivo metrico datato.

Pattern trasversale degli agenti (`run(...)` + ramo LLM/euristico, **mai
eccezione**): senza LLM (offline) la generazione degrada a una periodizzazione
euristica deterministica. Il Piano nasce sempre in stato PROPOSED (proponi-poi-
approva); la transizione ad ACTIVE avviene solo via `accept` → `promote_plan`.
"""

from __future__ import annotations

from typing import List, Optional

from ..athlete_metrics import (assessment_gap_to_goal, medical_boundary_flag,
                              overload_guardrail)
from ..athlete_models import (Assessment, Athlete, MetricGoal, PlanStatus,
                             Prescription, ProvenanceKind, TrainingBlock,
                             TrainingPlan, make_block_id, make_plan_id)
from ..config import get_settings
from ..db import Database
from ..llm import get_llm

_DISCLAIMER = "Questo è un piano-ipotesi generato automaticamente, non una prescrizione medica."


class CoachAgent:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm()

    def run(self, athlete_id: str, goal: MetricGoal,
            profile: Optional["AthleteProfile"] = None) -> TrainingPlan:
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

    def _llm_generate_plan(self, athlete_id, goal, start, profile, prev_active):
        return None   # implementato in Task 6
