"""CoachAgent: genera e mantiene un Piano vivo verso un obiettivo metrico datato.

Pattern trasversale degli agenti (`run(...)` + ramo LLM/euristico, **mai
eccezione**): senza LLM (offline) la generazione degrada a una periodizzazione
euristica deterministica. Il Piano nasce sempre in stato PROPOSED (proponi-poi-
approva); la transizione ad ACTIVE avviene solo via `accept` → `promote_plan`.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional, Tuple

from ..athlete_metrics import (DEFAULT_COMPLIANCE_THRESHOLD, assessment_delta,
                              attribution_verdict, block_planned_load, compliance,
                              derive_executed_block, freeze_athlete_data_citation,
                              freeze_citation, medical_boundary_flag,
                              overload_guardrail)
from ..athlete_models import (BlockState, EvidenceCitation, MetricGoal,
                             MetricType, PlanStatus, Prescription,
                             ProvenanceKind, TrainingBlock, TrainingPlan,
                             TransferabilityMemo, TransferabilityVerdict,
                             make_block_id, make_memo_id, make_plan_id)
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

    # -- loop veloce (Task 8) --------------------------------------------- #
    def adapt_microcycle(self, athlete_id: str) -> TrainingPlan:
        """Loop veloce: dallo stato di prontezza recente propone una nuova
        versione PROPOSED che, in caso di sovraccarico non-funzionale, declassa
        il carico del microciclo entrante.

        Invarianti: la strategia (goal/provenance/citazioni dei blocchi) resta
        invariata; i blocchi FROZEN non vengono mai toccati (ADR-0002);
        l'evidenza N=1 non viene aggiornata qui. Nessuna auto-attivazione:
        proponi-poi-approva (la promozione ad ACTIVE resta in `accept`).
        """
        plan = self.db.active_plan(athlete_id)
        if plan is None:
            raise ValueError(
                f"Nessun piano ACTIVE per l'atleta {athlete_id}: "
                "genera prima un piano con run()."
            )

        recent_tsb, hrv_drop, sleep_drop = self._recent_readiness(athlete_id)
        caveat = overload_guardrail(recent_tsb, hrv_drop, sleep_drop, None)

        # Versione LIBERA fra TUTTI i piani (inclusi i PROPOSED pendenti): id/versione
        # DISTINTI, così un'eventuale proposta strategica aperta non collide né viene
        # persa (append-only).
        v = self._next_free_version(athlete_id)
        new = plan.model_copy(deep=True)
        new.version = v
        new.id = make_plan_id(athlete_id, v)
        new.status = PlanStatus.PROPOSED
        new.valid_from = None
        new.valid_to = None
        new.created_at = None
        if caveat:
            self._downscale_entering_microcycle(new, factor=0.85)

        self._apply_guardrails_and_disclaimer(new, None)
        if caveat:
            new.notes = (new.notes + "\n" + caveat) if new.notes else caveat
        else:
            neutral = ("Nessun sovraccarico rilevato: carico del microciclo "
                       "entrante confermato (proponi-poi-approva).")
            new.notes = (new.notes + "\n" + neutral) if new.notes else neutral

        new.supersedes_id = plan.id
        # Marca SUPERSEDED i PROPOSED pendenti sotto i LORO id (ora distinti da `new`):
        # preservati append-only, non sovrascritti. Poi salva la nuova proposta.
        self._supersede_open_proposals(athlete_id)       # al più un PROPOSED
        self.db.save_plan(new)
        return new

    def _recent_readiness(self, athlete_id):
        """Deriva lo stato recente dalle serie storiche: TSB dell'ultimo punto,
        e cali (ultimo < media dei precedenti) per HRV e sonno.
        Un calo non calcolabile (<2 punti) è None (nessun crash segnalato)."""
        recent_tsb = self._last_value(athlete_id, MetricType.TSB)
        hrv_drop = self._is_dropping(athlete_id, MetricType.HRV)
        sleep_drop = self._is_dropping(athlete_id, MetricType.SLEEP)
        return recent_tsb, hrv_drop, sleep_drop

    def _last_value(self, athlete_id, metric_type):
        points = self.db.list_timeseries(athlete_id, metric_type=metric_type.value)
        vals = [p.value for p in points if p.value is not None]
        return vals[-1] if vals else None

    def _is_dropping(self, athlete_id, metric_type):
        points = self.db.list_timeseries(athlete_id, metric_type=metric_type.value)
        vals = [p.value for p in points if p.value is not None]
        if len(vals) < 2:
            return None
        previous = vals[:-1]
        avg_previous = sum(previous) / len(previous)
        return vals[-1] < avg_previous

    def _downscale_entering_microcycle(self, plan: TrainingPlan, factor: float) -> None:
        """Riduce il carico delle Prescription dei SOLI blocchi non-FROZEN (il
        microciclo entrante). I blocchi FROZEN restano intatti (ADR-0002); la
        strategia (goal/provenance/citazioni) non viene toccata."""
        for block in plan.blocks:
            if block.state == BlockState.FROZEN:
                continue
            for pres in block.prescriptions:
                if pres.target_watts is not None:
                    pres.target_watts = pres.target_watts * factor
                if pres.duration_s is not None:
                    pres.duration_s = int(round(pres.duration_s * factor))

    # -- loop lento (Task 7) ---------------------------------------------- #
    def assess_block(self, athlete_id: str, plan_id: str,
                     block_id: str) -> TransferabilityMemo:
        """Valuta la trasferibilità di un Blocco eseguito → TransferabilityMemo.

        Gate di compliance (US 9): il carico eseguito è ricavato dalle Attività
        reali nel range pianificato; se il rapporto eseguito/pianificato è sotto
        soglia, non si attribuisce il delta di metrica (verdict INCONCLUSIVE,
        caveat esplicito). L'evidenza a supporto è N=1 (`athlete_data`), mai studio.
        """
        plan = self.db.get_plan(plan_id)
        if plan is None:
            raise ValueError(f"Piano {plan_id} inesistente.")
        block = next((b for b in plan.blocks if b.id == block_id), None)
        if block is None:
            raise ValueError(f"Blocco {block_id} inesistente nel piano {plan_id}.")
        activities = self.db.list_activities(athlete_id)
        exec_ = derive_executed_block(block, activities)
        planned = block_planned_load(block)          # durata pianificata (s)
        executed_s = exec_["executed_moving_time_s"]  # durata eseguita (s)

        assessments = self.db.list_assessments(athlete_id)
        before, after = self._pre_post_assessments(assessments, block)
        delta = assessment_delta(
            before.value if before else None, after.value if after else None
        )
        metric_key = (plan.target_metric_type.value
                      if plan.target_metric_type is not None else "metric")

        caveats: List[str] = []
        if planned <= 0:
            # Senza durata pianificata non si può attribuire nulla: la compliance
            # è indefinita (None), non un fallimento sotto soglia.
            compliance_ratio: Optional[float] = None
            verdict = TransferabilityVerdict.INCONCLUSIVE
            metric_deltas: Dict[str, float] = {}
            caveats.append("durata pianificata non derivabile")
        else:
            ratio = compliance(planned, executed_s)
            verdict = attribution_verdict(ratio, delta)
            if ratio < DEFAULT_COMPLIANCE_THRESHOLD:
                caveats.append("compliance < soglia")
            compliance_ratio = ratio
            metric_deltas = {} if delta is None else {metric_key: delta}

        citations = [
            freeze_athlete_data_citation(a.id, note="valutazione di blocco")
            for a in (before, after) if a
        ]
        memo = TransferabilityMemo(
            id=make_memo_id(block_id), athlete_id=athlete_id, block_id=block_id,
            verdict=verdict, metric_deltas=metric_deltas,
            compliance_ratio=compliance_ratio, caveats=caveats, citations=citations,
        )
        self.db.save_memo(memo)
        return memo

    def _pre_post_assessments(self, assessments, block):
        """Seleziona la valutazione pre (ultima con data <= planned_start) e post
        (prima con data >= planned_end). Restituisce (before, after), con None se
        una delle due non esiste."""
        def _date(a):
            return a.executed_date or a.planned_date

        before = None
        for a in assessments:
            d = _date(a)
            if d is None or block.planned_start is None:
                continue
            if d <= block.planned_start:
                before = a                         # last-wins (assessments ordinate ASC)
        after = None
        for a in assessments:
            d = _date(a)
            if d is None or block.planned_end is None:
                continue
            if d >= block.planned_end:
                after = a                          # first-wins
                break
        return before, after

    # -- interni ---------------------------------------------------------- #
    def _baseline_from_assessments(self, assessments, goal) -> Optional[float]:
        vals = [a.value for a in assessments if a.value is not None]
        return vals[-1] if vals else None

    def _next_free_version(self, athlete_id: str) -> int:
        """Prossima versione LIBERA fra TUTTI i piani (inclusi i PROPOSED pendenti):
        garantisce id/versione DISTINTI e monotoni (append-only), senza collisioni con
        una proposta ancora aperta."""
        return max((p.version for p in self.db.list_plans(athlete_id)), default=0) + 1

    def _periodize_dates(self, target_date, n_blocks: int,
                         weeks_per_block: int = 4) -> List[Tuple[Optional[str], Optional[str]]]:
        """Periodizzazione datata a ritroso (deterministica dall'input): `n_blocks`
        finestre CONSECUTIVE di `weeks_per_block` settimane, con l'ULTIMO blocco che
        termina esattamente a `target_date`. NON usa `date.today()`/`now()`.

        Degrada (non solleva) a `[(None, None)] * n_blocks` se `target_date` è None o
        non parseabile."""
        if not target_date or n_blocks <= 0:
            return [(None, None)] * max(n_blocks, 0)
        try:
            end = datetime.date.fromisoformat(str(target_date))
        except (ValueError, TypeError):
            return [(None, None)] * n_blocks
        span = datetime.timedelta(weeks=weeks_per_block)
        windows: List[Tuple[Optional[str], Optional[str]]] = []
        for _ in range(n_blocks):
            start = end - span
            windows.append((start.isoformat(), end.isoformat()))
            end = start                                  # blocco precedente adiacente
        windows.reverse()                                # ordine cronologico dei blocchi
        return windows

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
        version = self._next_free_version(athlete_id)
        plan = TrainingPlan(
            id=make_plan_id(athlete_id, version), athlete_id=athlete_id, version=version,
            status=PlanStatus.PROPOSED, target_metric_type=goal.metric_type,
            target_metric_start=start, target_metric_value=goal.target,
            target_metric_date=goal.target_date,
        )
        # Periodizzazione a ritroso deterministica: 3 blocchi (base→sviluppo→taper).
        blocks_spec = self._strategic_choices(goal)
        # Conflict-aware anche offline: interroga il Retriever (output deterministico)
        # per ogni scelta strategica, riusando lo stesso helper del ramo LLM.
        choices = self._retrieve_for_choices(athlete_id, goal, blocks_spec)
        windows = self._periodize_dates(goal.target_date, len(blocks_spec))
        blocks: List[TrainingBlock] = []
        for i, (spec, choice) in enumerate(zip(blocks_spec, choices)):
            g = spec["goal"]
            bid = make_block_id(plan.id, i)
            # start=None onesto: mai 0.0 travestito da target.
            target_watts = (start * (0.9 + 0.05 * i)) if start is not None else None
            pres = [Prescription(
                description=f"Seduta {g}", target_watts=target_watts,
                duration_s=3600, provenance=ProvenanceKind.HEURISTIC)]
            # Citazioni SOLO da evidenza verificata positiva → provenance STUDY del
            # blocco; i NUMERI restano HEURISTIC (regola del range invariata).
            citations = self._freeze_positives(choice["positives"])
            block_prov = ProvenanceKind.STUDY if citations else ProvenanceKind.HEURISTIC
            conflicts = self._conflicts_as_text(choice["conflicts"])
            start_iso, end_iso = windows[i]
            blocks.append(TrainingBlock(
                id=bid, plan_id=plan.id, goal=g, order=i, prescriptions=pres,
                provenance=block_prov, citations=citations, conflicts=conflicts,
                planned_start=start_iso, planned_end=end_iso,
            ))
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
        version = self._next_free_version(athlete_id)
        plan = TrainingPlan(
            id=make_plan_id(athlete_id, version), athlete_id=athlete_id, version=version,
            status=PlanStatus.PROPOSED, target_metric_type=goal.metric_type,
            target_metric_start=start, target_metric_value=goal.target,
            target_metric_date=goal.target_date,
        )
        athlete = self.db.get_athlete(athlete_id)
        blocks_spec = data.get("blocks") or []
        windows = self._periodize_dates(goal.target_date, len(blocks_spec))
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
            start_iso, end_iso = windows[i]
            blocks.append(TrainingBlock(
                id=bid, plan_id=plan.id, goal=str(spec.get("goal") or f"blocco-{i}"),
                order=i, prescriptions=prescriptions, provenance=block_prov,
                citations=citations, conflicts=conflicts,
                planned_start=start_iso, planned_end=end_iso,
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
