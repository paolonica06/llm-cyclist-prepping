"""API FastAPI: espone la pipeline prima della realizzazione della GUI.

Avvio:  uvicorn cyclist_kb.api:app --reload
Le fasi di rete (search/verify/extract) sono endpoint asincroni.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ValidationError

from .agents.athlete import load_profile
from .athlete_models import (MetricGoal, MetricType, TrainingPlan,
                            TransferabilityMemo)
from .db import Database
from .models import PaperRecord, RecordState, Research
from .pipeline import (AthleteNotFound, Pipeline, PlanNotFound, PlanStateError,
                      ResearchNotFound)
from .retrieval import RetrievalResult, retrieve

app = FastAPI(title="Cyclist KB", version="0.1.0",
              description="Knowledge base scientifica ciclistica auto-mantenuta (MVP).")


def pipeline() -> Pipeline:
    return Pipeline()


class CreateRequest(BaseModel):
    topic: str


class RunRequest(BaseModel):
    topic: str
    profile_path: Optional[str] = None


class AthleteRequest(BaseModel):
    profile_path: str


class RetrieveRequest(BaseModel):
    query: str
    athlete_id: Optional[str] = None
    k: int = 8
    rerank: bool = False


class CoachRequest(BaseModel):
    metric: str = "ftp"
    to: float
    by: str                                   # data-obiettivo ISO YYYY-MM-DD
    start: Optional[float] = None             # valore di partenza (opzionale)
    profile_path: Optional[str] = None


def _research_or_404(research_id: str) -> Research:
    r = Database().get_research(research_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Ricerca '{research_id}' inesistente.")
    return r


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/research", response_model=Research)
def create(req: CreateRequest) -> Research:
    return pipeline().create(req.topic)


@app.get("/research", response_model=List[Research])
def list_researches() -> List[Research]:
    return Database().list_researches()


@app.get("/research/{research_id}")
def get_research(research_id: str) -> dict:
    r = _research_or_404(research_id)
    return {"research": r.model_dump(), "counts": Database().count_by_state(research_id)}


@app.get("/research/{research_id}/records", response_model=List[PaperRecord])
def list_records(research_id: str, state: Optional[RecordState] = Query(None)) -> List[PaperRecord]:
    _research_or_404(research_id)
    return Database().list_records(research_id, states=[state] if state else None)


@app.post("/research/{research_id}/search", response_model=Research)
async def search(research_id: str) -> Research:
    try:
        return await pipeline().search(research_id)
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/research/{research_id}/screen", response_model=Research)
def screen(research_id: str) -> Research:
    try:
        return pipeline().screen(research_id)
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/research/{research_id}/verify", response_model=Research)
async def verify(research_id: str) -> Research:
    try:
        return await pipeline().verify(research_id)
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/research/{research_id}/extract", response_model=Research)
async def extract(research_id: str) -> Research:
    try:
        return await pipeline().extract(research_id)
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/research/{research_id}/quality", response_model=Research)
def quality(research_id: str) -> Research:
    try:
        return pipeline().quality(research_id)
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/research/{research_id}/synthesize", response_model=Research)
def synthesize(research_id: str) -> Research:
    try:
        return pipeline().synthesize(research_id)
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/research/{research_id}/athlete")
def athlete(research_id: str, req: AthleteRequest) -> dict:
    try:
        path = pipeline().athlete(research_id, Path(req.profile_path))
        return {"page": str(path)}
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Profilo atleta non trovato.")
    except (ValidationError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Profilo atleta non valido: {exc}")


@app.post("/retrieve", response_model=List[RetrievalResult])
def retrieve_endpoint(req: RetrieveRequest) -> List[RetrievalResult]:
    """Fase C: interroga il pozzo di evidenza verificata (conflict-aware).

    `rerank=True` attiva il tier LLM opzionale (degrada all'ordine deterministico
    se nessun LLM è disponibile).
    """
    db = Database()
    ath = db.get_athlete(req.athlete_id) if req.athlete_id else None
    return retrieve(db, req.query, athlete=ath, k=req.k, rerank=req.rerank)


# --------------------------------------------------------------------------- #
# Fase D: CoachAgent (piano vivo verso obiettivo metrico datato)
# --------------------------------------------------------------------------- #
@app.post("/coach/{athlete_id}", response_model=TrainingPlan)
def coach(athlete_id: str, req: CoachRequest) -> TrainingPlan:
    """Genera un piano PROPOSED verso l'obiettivo metrico datato (proponi-poi-approva)."""
    try:
        goal = MetricGoal(metric_type=MetricType(req.metric), target=req.to,
                          target_date=req.by, start=req.start)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Grandezza obiettivo non valida: {exc}")
    profile = Path(req.profile_path) if req.profile_path else None
    try:
        return pipeline().coach(athlete_id, goal, profile)
    except AthleteNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/coach/accept/{plan_id}", response_model=TrainingPlan)
def coach_accept(plan_id: str) -> TrainingPlan:
    """Promuove un piano PROPOSED → ACTIVE."""
    try:
        return pipeline().coach_accept(plan_id)
    except PlanNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PlanStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/coach/adapt/{athlete_id}", response_model=TrainingPlan)
def coach_adapt(athlete_id: str) -> TrainingPlan:
    """Loop veloce: adatta il microciclo entrante e propone una nuova versione PROPOSED."""
    try:
        return pipeline().coach_adapt(athlete_id)
    except AthleteNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PlanStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/coach/assess/{athlete_id}/{plan_id}/{block_id}",
          response_model=TransferabilityMemo)
def coach_assess(athlete_id: str, plan_id: str, block_id: str) -> TransferabilityMemo:
    """Loop lento: valuta un blocco eseguito → TransferabilityMemo (N=1)."""
    try:
        return pipeline().coach_assess(athlete_id, plan_id, block_id)
    except PlanNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PlanStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/coach/plans/{athlete_id}", response_model=List[TrainingPlan])
def coach_plans(athlete_id: str, status: Optional[str] = Query(None)) -> List[TrainingPlan]:
    """Elenca i piani dell'atleta (filtro `status` opzionale: proposed/active/superseded)."""
    return Database().list_plans(athlete_id, status=status)


@app.get("/coach/memos/{athlete_id}", response_model=List[TransferabilityMemo])
def coach_memos(athlete_id: str, block_id: Optional[str] = Query(None)) -> List[TransferabilityMemo]:
    """Elenca i memo di trasferibilità dell'atleta (filtro `block_id` opzionale)."""
    return Database().list_memos(athlete_id, block_id=block_id)


@app.post("/research/run", response_model=Research)
async def run(req: RunRequest) -> Research:
    profile = Path(req.profile_path) if req.profile_path else None
    # Valida il profilo PRIMA di avviare le fasi di rete (fallimento rapido).
    if profile is not None:
        try:
            load_profile(profile)
        except FileNotFoundError:
            raise HTTPException(status_code=400, detail="Profilo atleta non trovato.")
        except (ValidationError, yaml.YAMLError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail=f"Profilo atleta non valido: {exc}")
    return await pipeline().run(req.topic, profile)
