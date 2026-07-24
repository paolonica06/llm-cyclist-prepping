"""Athlete Context Agent: contestualizza le evidenze su un profilo atleta.

Legge un profilo separato, confronta popolazione e protocollo degli studi con
età/categoria/livello/volume/obiettivi/storico dell'atleta, evidenzia le
differenze rilevanti e formula **ipotesi applicative** (mai prescrizioni certe).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import yaml

from ..config import get_settings
from ..llm import get_llm
from ..models import (AthleteProfile, PaperRecord, PopulationType, RecordState,
                      Research)
from ..wiki import Wiki, slugify

logger = logging.getLogger("cyclist_kb.athlete")


def load_profile(path: Path) -> AthleteProfile:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return AthleteProfile.model_validate(data)


class AthleteContextAgent:
    def __init__(self, db) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm()
        self.wiki = Wiki()

    def run(self, research: Research, profile: AthleteProfile) -> Path:
        records = self.db.list_records(research.id, states=[RecordState.SYNTHESIZED])
        comparisons = [self._compare(rec, profile) for rec in records]
        page = self._page(research, profile, records, comparisons)
        path = self.wiki.athlete_path(profile.name)
        self.wiki.write(path, page)
        self.wiki.commit(f"Contesto atleta '{profile.name}' su '{research.topic}'")
        logger.info("Contesto atleta %s: %d studi confrontati", profile.name, len(records))
        return path

    def _compare(self, rec: PaperRecord, profile: AthleteProfile) -> dict:
        diffs: List[str] = []
        pop = rec.screening.population_type if rec.screening else PopulationType.UNCLEAR
        text = f"{rec.title or ''} {rec.abstract or ''}".lower()

        # Popolazione vs disciplina/livello dell'atleta.
        if pop == PopulationType.CYCLING:
            aligned_pop = True
        elif pop in (PopulationType.MIXED, PopulationType.UNCLEAR):
            aligned_pop = True
            diffs.append("Popolazione dello studio non esclusivamente ciclistica.")
        else:
            aligned_pop = False
            diffs.append(f"Popolazione dello studio '{pop.value}' diversa dal profilo (ciclista).")

        # Livello di allenamento.
        competitive_study = any(w in text for w in ("competitive", "elite", "professional",
                                                    "well-trained", "trained cyclists", "national level"))
        athlete_competitive = (profile.level or "").lower() in ("competitivo", "competitive", "elite") \
            or (profile.category or "").lower() in ("elite", "u23", "pro")
        if athlete_competitive and not competitive_study:
            diffs.append("Lo studio non è su atleti competitivi: possibile minore trasferibilità.")

        # Età.
        study_age = _study_age(rec)
        if profile.age and study_age and abs(profile.age - study_age) >= 10:
            diffs.append(f"Età media dello studio (~{study_age}) distante dall'atleta ({profile.age}).")

        # Sesso.
        study_sex = rec.extraction.sex.value if rec.extraction and rec.extraction.sex.value else None
        if profile.sex and study_sex and study_sex != "mixed" \
                and _sex_norm(profile.sex) != _sex_norm(str(study_sex)):
            diffs.append(f"Sesso dei partecipanti ({study_sex}) diverso dall'atleta ({profile.sex}).")

        # Durata protocollo vs orizzonte dell'atleta (informativo).
        dur = rec.extraction.duration.value if rec.extraction and rec.extraction.duration.value else None

        transfer = rec.quality.transferability_to_competitive_cyclists.value if rec.quality else "?"
        if not diffs:
            alignment = "allineato"
        elif aligned_pop:
            alignment = "parziale"
        else:
            alignment = "divergente"

        return {"rec": rec, "alignment": alignment, "diffs": diffs,
                "duration": dur, "transferability": transfer, "study_age": study_age}

    def _page(self, research: Research, profile: AthleteProfile,
              records: List[PaperRecord], comparisons: List[dict]) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        topic_link = f"../topics/{slugify(research.topic)}.md"
        out = [f"# Contesto atleta — {profile.name}", ""]
        out.append(f"> Confronto fra le evidenze su [{research.topic}]({topic_link}) e il profilo "
                   f"dell'atleta. Aggiornato {now}. **Ipotesi applicative, non prescrizioni.**")
        out.append("")
        out.append("## Profilo")
        for label, val in [("Età", profile.age), ("Sesso", profile.sex), ("Categoria", profile.category),
                           ("Livello", profile.level), ("Disciplina", profile.discipline),
                           ("Ore/sett.", profile.weekly_hours), ("TSS/sett.", profile.weekly_tss),
                           ("FTP (W)", profile.ftp_w), ("FTP (W/kg)", profile.ftp_w_kg),
                           ("VO₂max", profile.vo2max)]:
            if val not in (None, ""):
                out.append(f"- **{label}**: {val}")
        if profile.goals:
            out.append(f"- **Obiettivi**: {', '.join(profile.goals)}")
        if profile.history:
            out.append(f"- **Storico**: {', '.join(profile.history)}")
        if profile.constraints:
            out.append(f"- **Vincoli**: {', '.join(profile.constraints)}")
        out.append("")

        # Differenze rilevanti studio-per-studio.
        out.append("## Confronto con gli studi")
        out.append("")
        out.append("| Studio | Allineamento | Trasferibilità | Durata protocollo | Differenze principali |")
        out.append("|---|---|---|---|---|")
        for c in sorted(comparisons, key=lambda x: _align_rank(x["alignment"])):
            rec = c["rec"]
            cite = f"{_first_author(rec)} {rec.year or 's.d.'}"
            diffs = "; ".join(c["diffs"]) if c["diffs"] else "—"
            dur = c.get("duration") or "n/d"
            out.append(f"| [{cite}](../papers/{rec.id}.md) | {c['alignment']} | "
                       f"{c['transferability']} | {dur} | {diffs} |")
        out.append("")

        # Ipotesi applicative.
        out.append("## Ipotesi applicative")
        out.append("")
        out.append("> Formulate a partire dagli studi più allineati al profilo. Sono ipotesi da "
                   "verificare sul campo, non indicazioni prescrittive.")
        out.append("")
        hyps = self._hypotheses(profile, comparisons)
        for h in hyps:
            out.append(f"- {h}")
        out.append("")

        # Avvertenze sulle differenze critiche.
        divergent = [c for c in comparisons if c["alignment"] == "divergente"]
        if divergent:
            out.append("## Differenze critiche")
            out.append("")
            for c in divergent:
                rec = c["rec"]
                out.append(f"- **{rec.title or rec.id}**: {'; '.join(c['diffs'])}")
            out.append("")
        return "\n".join(out)

    def _hypotheses(self, profile: AthleteProfile, comparisons: List[dict]) -> List[str]:
        aligned = [c for c in comparisons
                   if c["alignment"] in ("allineato", "parziale")
                   and c["transferability"] in ("high", "moderate")]
        if self.llm.available:
            narrative = self._llm_hypotheses(profile, aligned)
            if narrative:
                return narrative
        hyps = []
        if not aligned:
            return ["Nessuno studio sufficientemente allineato al profilo: raccogliere evidenze "
                    "più specifiche prima di trarre indicazioni."]
        target = profile.level or profile.category or "l'atleta"
        hyps.append(f"Gli studi più trasferibili ({len(aligned)}) provengono da popolazioni "
                    f"compatibili con «{target}»: "
                    f"le loro conclusioni sono un punto di partenza plausibile.")
        if profile.goals:
            hyps.append(f"Rispetto agli obiettivi ({', '.join(profile.goals)}), valutare un test "
                        f"controllato di 4-8 settimane monitorando gli outcome chiave.")
        hyps.append("Adattare volume e intensità al carico attuale dell'atleta "
                    f"({profile.weekly_hours or '?'} h/sett.) evitando incrementi bruschi.")
        hyps.append("Verificare la risposta individuale con misure oggettive (VO₂max, potenza a soglia) "
                    "prima di consolidare qualsiasi modifica.")
        return hyps

    def _llm_hypotheses(self, profile: AthleteProfile, aligned: List[dict]) -> Optional[List[str]]:
        studies = "\n".join(
            f"- {c['rec'].title} (trasferibilità {c['transferability']})" for c in aligned[:15]
        )
        data = self.llm.complete_json(
            prompt=(
                "Dato questo profilo atleta e gli studi allineati, formula 3-6 IPOTESI applicative "
                "(non prescrizioni), evidenziando incertezze.\n"
                f"Profilo: {profile.model_dump_json()}\nStudi:\n{studies}\n\n"
                "Restituisci JSON: {\"hypotheses\": [\"...\"]}."
            )
        )
        if data and isinstance(data.get("hypotheses"), list):
            return [str(h) for h in data["hypotheses"] if str(h).strip()]
        return None


def _first_author(rec: PaperRecord) -> str:
    """Cognome del primo autore in modo difensivo (gestisce voci vuote/sporche)."""
    if rec.authors:
        parts = rec.authors[0].split(",")[0].split()
        if parts:
            return parts[0]
    return "Anon"


def _study_age(rec: PaperRecord) -> Optional[int]:
    val = rec.extraction.age.value if rec.extraction and rec.extraction.age.value else None
    if not val:
        return None
    import re
    s = str(val)
    # Range "X to Y" / "X-Y" → media degli estremi; "X ± SD" o "X anni" → X (non mediare la SD).
    range_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)", s)
    if range_m:
        return round((float(range_m.group(1)) + float(range_m.group(2))) / 2)
    first = re.search(r"\d+(?:\.\d+)?", s)
    return round(float(first.group(0))) if first else None


def _sex_norm(s: str) -> str:
    s = s.lower()
    if s in ("m", "male", "maschio", "uomo", "men"):
        return "male"
    if s in ("f", "female", "femmina", "donna", "women"):
        return "female"
    return s


def _align_rank(a: str) -> int:
    return {"allineato": 0, "parziale": 1, "divergente": 2}.get(a, 3)
