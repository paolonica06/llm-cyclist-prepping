#!/usr/bin/env python3
"""Arricchisce l'evento gara su intervals.icu con il brief di percorso e pacing.

Additivo: aggiunge distanza e analisi del percorso alla descrizione della gara,
senza toccare struttura del piano, date o carichi. Come push_plan_20260728.py,
verifica il nome live e senza --apply non scrive.

    python scripts/push_race_brief.py            # dry-run
    python scripts/push_race_brief.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cyclist_kb.clients.base import HttpFetcher  # noqa: E402
from cyclist_kb.clients.intervals_icu import IntervalsClient  # noqa: E402

ATHLETE = "i215294"
EVENT_ID = 124969208
EXPECTED_NAME = "🏁 GARA Zanè Monte Cengio"

DESCRIPTION = """Categoria C: gara-allenamento e lavoro di squadra, senza obiettivo di risultato. È la qualità n. 2 della settimana dopo il test CP.

PERCORSO (da GPX: 119,5 km / 2078 m D+ / arrivo a 1268 m)
- km 0-48: pianura
- km 48-105: 3 giri di circuito mosso, 5 strappi per giro (475-1900 m, 2,6-5,3%)
- km 105-119,5: SALITA FINALE 14,2 km al 6,7%, +958 m

LA SALITA FINALE È LA GARA. Dura 54-60 minuti: su quella durata W' vale solo +9W di supplemento, quindi conta soltanto CP. Non è terreno da attacchi.
- km 1-2 all'8,5-9,1% → la trappola: NON strafare qui
- km 3-11 al 4,6-5,3% → il tratto dove si fa il tempo
- km 12-13 al 10,7% e 9,1% → il muro vero
- km 14-15 al 6,5% e 9,2% → arrivo

PACING SALITA: 250-265W (92-97% di CP). Il tetto teorico è 281W con W' pieno ai piedi, ma dopo 105 km non lo avrai pieno. Sui muri non scendere sotto 60 rpm: con 34x30 servono 63 rpm a 240W sul 10,7%.

CIRCUITO: gli strappi durano 1'23"-4'17", lì W' è la valuta. Tutti a CP+20W costerebbero 45 kJ contro un budget di 28 kJ — si recupera fra uno e l'altro (tau ~8 min sotto CP), ma il margine non è infinito. Non inseguire ogni sparata.

DURATA ATTESA 4h00-4h20 · TSS 230-280.
CHO 80-90 g/h → 320-390 g TOTALI: borraccia + gel ogni 20'. Non partire disidratato.

NB: watt provvisori su CP 273 stimato dalla curva 42gg. RICALIBRARE dopo il test del 29/07."""

PATCH = {"description": DESCRIPTION, "distance": 119490}


async def main(apply: bool) -> int:
    client = IntervalsClient()
    if not client.available:
        print("ERRORE: client intervals.icu non disponibile.")
        return 2
    async with HttpFetcher() as fetcher:
        client._fetcher = fetcher
        current = await client._get(f"/athlete/{ATHLETE}/events/{EVENT_ID}")
        if not current:
            print(f"ERRORE: evento {EVENT_ID} non letto. Interrotto.")
            return 3
        if current.get("name") != EXPECTED_NAME:
            print(f"ERRORE: l'evento si chiama {current.get('name')!r}, "
                  f"atteso {EXPECTED_NAME!r}. Interrotto.")
            return 3

        backup = (Path(__file__).resolve().parent.parent
                  / "data" / "private" / "race_event_backup_20260801.json")
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Backup evento originale: {backup}\n")

        print(f"── {EXPECTED_NAME} (evento {EVENT_ID}, {current.get('category')})")
        print(f"   distanza  : {current.get('distance')} → {PATCH['distance']} m")
        print(f"   descrizione: {len(current.get('description') or '')} car."
              f" → {len(DESCRIPTION)} car.\n")

        if not apply:
            print("DRY-RUN: niente scritto. Riesegui con --apply.")
            return 0

        res = await client.update_event(ATHLETE, EVENT_ID, PATCH)
        if res.ok:
            print(f"OK evento gara aggiornato (HTTP {res.status})")
            return 0
        print(f"FAIL HTTP {res.status} — {res.error}")
        return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    raise SystemExit(asyncio.run(main(ap.parse_args().apply)))
