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
from .db import Database
from .models import PaperRecord, RecordState, Research
from .pipeline import Pipeline, ResearchNotFound

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
