"""CLI `research` — ogni fase eseguibile singolarmente o l'intera pipeline.

Esempi:
    research create "interval training and VO2max in trained competitive cyclists"
    research search <research_id>
    research run "interval training and VO2max in trained competitive cyclists"
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer

from .config import get_settings
from .db import Database
from .models import RecordState
from .pipeline import Pipeline, ResearchNotFound

app = typer.Typer(add_completion=False, help="Knowledge base ciclistica auto-mantenuta (MVP).")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


@app.callback()
def main(verbose: bool = typer.Option(True, "--verbose/--quiet", help="Log dettagliato.")):
    _setup_logging(verbose)


def _pipeline() -> Pipeline:
    return Pipeline()


def _print_stats(research) -> None:
    typer.echo(f"Ricerca: {research.id}  ({research.status.value})")
    if research.stats:
        for k, v in research.stats.items():
            typer.echo(f"  {k}: {v}")


def _handle_missing(fn):
    try:
        return fn()
    except ResearchNotFound as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --------------------------------------------------------------------------- #
@app.command()
def create(topic: str = typer.Argument(..., help="Argomento di ricerca.")):
    """Crea una nuova ricerca e ne stampa l'id."""
    research = _pipeline().create(topic)
    typer.secho(f"Creata ricerca: {research.id}", fg=typer.colors.GREEN)
    typer.echo(f"Topic: {research.topic}")


@app.command()
def search(research_id: str):
    """Interroga PubMed, OpenAlex, Semantic Scholar e Crossref + citation chasing."""
    p = _pipeline()
    research = _handle_missing(lambda: asyncio.run(p.search(research_id)))
    _print_stats(research)


@app.command()
def screen(research_id: str):
    """Valuta pertinenza e popolazione; include/esclude registrando il motivo."""
    p = _pipeline()
    research = _handle_missing(lambda: p.screen(research_id))
    _print_stats(research)


@app.command()
def verify(research_id: str):
    """Verifica DOI/PMID e coerenza dei metadati (Crossref + PubMed)."""
    p = _pipeline()
    research = _handle_missing(lambda: asyncio.run(p.verify(research_id)))
    _print_stats(research)


@app.command()
def extract(research_id: str):
    """Estrae i campi strutturati (distinguendo full text vs abstract)."""
    p = _pipeline()
    research = _handle_missing(lambda: asyncio.run(p.extract(research_id)))
    _print_stats(research)


@app.command()
def quality(research_id: str):
    """Classifica lo studio e valuta qualità/confidenza/trasferibilità."""
    p = _pipeline()
    research = _handle_missing(lambda: p.quality(research_id))
    _print_stats(research)


@app.command()
def synthesize(research_id: str):
    """Aggiorna le pagine Markdown della wiki collegando le affermazioni ai paper."""
    p = _pipeline()
    research = _handle_missing(lambda: p.synthesize(research_id))
    _print_stats(research)
    typer.echo(f"Wiki: {get_settings().wiki_dir}")


@app.command()
def athlete(research_id: str,
            profile: Path = typer.Argument(..., help="Percorso del profilo atleta (YAML/JSON).")):
    """Contestualizza le evidenze su un profilo atleta (ipotesi, non prescrizioni)."""
    import yaml
    from pydantic import ValidationError

    p = _pipeline()
    try:
        path = p.athlete(research_id, profile)
    except ResearchNotFound as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except FileNotFoundError:
        typer.secho(f"Profilo non trovato: {profile}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except (yaml.YAMLError, ValidationError) as exc:
        typer.secho(f"Profilo atleta non valido: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho(f"Pagina atleta generata: {path}", fg=typer.colors.GREEN)


@app.command()
def run(topic: str = typer.Argument(..., help="Argomento di ricerca."),
        profile: Optional[Path] = typer.Option(None, "--profile", help="Profilo atleta opzionale.")):
    """Esegue l'intera pipeline: search → screen → verify → extract → quality → synthesize."""
    p = _pipeline()
    research = asyncio.run(p.run(topic, profile))
    typer.secho("Pipeline completata.", fg=typer.colors.GREEN)
    _print_stats(research)
    typer.echo(f"Wiki: {get_settings().wiki_dir}")


@app.command(name="athlete-sync")
def athlete_sync(
    athlete_id: str = typer.Argument(..., help="Id atleta su intervals.icu."),
    oldest: Optional[str] = typer.Option(None, help="Data minima ISO (YYYY-MM-DD)."),
    newest: Optional[str] = typer.Option(None, help="Data massima ISO (YYYY-MM-DD)."),
):
    """Morning sync: ingesta wellness/fitness/attività da intervals.icu (Fase B)."""
    summary = asyncio.run(_pipeline().sync_athlete(athlete_id, oldest, newest))
    if not summary["available"]:
        typer.secho(
            "intervals.icu non configurato (KB_INTERVALS_ICU_API_KEY assente) o offline: "
            "nessun dato sincronizzato.",
            fg=typer.colors.YELLOW,
        )
    typer.echo(f"Serie storiche: {summary['timeseries_points']}  Attività: {summary['activities']}")


@app.command()
def retrieve(
    query: str = typer.Argument(..., help="Interrogazione (libera o derivata dallo stato atleta)."),
    athlete: Optional[str] = typer.Option(None, "--athlete", help="Id atleta per la personalizzazione."),
    k: int = typer.Option(8, "--k", help="Numero di studi da restituire."),
):
    """Interroga il pozzo di evidenza verificata (Fase C): studi pertinenti, pesati, conflict-aware."""
    from .retrieval import retrieve as _retrieve

    db = Database()
    ath = db.get_athlete(athlete) if athlete else None
    results = _retrieve(db, query, athlete=ath, k=k)
    if not results:
        typer.secho("Nessuno studio verificato pertinente.", fg=typer.colors.YELLOW)
        return
    typer.echo(f"Top {len(results)} studi verificati per «{query}»:")
    for i, r in enumerate(results, 1):
        rec = r.record
        who = f"{rec.authors[0] if rec.authors else '?'} {rec.year or ''}".strip()
        typer.echo(f"{i}. [{r.direction}] {who} — {rec.title or rec.doi}")
        typer.echo(f"     pertinenza={r.relevance} qualità={r.quality} fit={r.fit} "
                   f"score={r.score} · pop={r.signals.get('population')}")


@app.command(name="list")
def list_researches():
    """Elenca tutte le ricerche."""
    for r in Database().list_researches():
        typer.echo(f"{r.id}  [{r.status.value}]  {r.topic}")


@app.command()
def status(research_id: str):
    """Mostra il conteggio dei record per stato."""
    db = Database()
    research = _handle_missing(lambda: (db.get_research(research_id) or _raise(research_id)))
    counts = db.count_by_state(research_id)
    typer.echo(f"Ricerca {research.id}: {research.topic}  [{research.status.value}]")
    for state in RecordState:
        n = counts.get(state.value, 0)
        if n:
            typer.echo(f"  {state.value}: {n}")


def _raise(rid: str):
    raise ResearchNotFound(f"Ricerca '{rid}' inesistente.")


if __name__ == "__main__":
    app()
