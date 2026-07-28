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

DESCRIPTION = """OBIETTIVO: squadra e gruppo. Nessun risultato personale, nessun cronometro. Non guardare chi ti passa.

PERCORSO (da GPX: 119,5 km / 2078 m D+ / arrivo a 1268 m, punto-a-punto)
- km 0-48: pianura
- km 48-105: 3 giri di circuito mosso, 5 strappi per giro (475-1900 m, 2,6-5,3%)
- km 105-119,5: salita finale 14,2 km al 6,7%, +958 m

CIRCUITO — LAVORA LIBERAMENTE. Simulato il consumo di W' sui 15 strappi tutti a CP+60W con i 4' di respiro reali: oscilla fra 43% e 67%, non si accumula (tau 8,9 min a 180W recupera il 36% per intervallo). Non c'è un budget da razionare.
Il lavoro in pianura costa ZERO W' perché è sotto CP: tirare a 250-270W sul piano è il modo più utile alla squadra al costo più basso. Fai il motore lì.

SALITA FINALE — il costo non dipende da come la fai: 200W = 74' e 46 TSS, 255W = 59' e 59 TSS. Solo 13 TSS di differenza. Quindi scegli sullo stimolo, non sul costo.
Target: 240-255W (88-93% di CP) a sensazione, come LAVORO non come gara — 55-60' continui su CP sono esattamente lo stimolo che serve al blocco d'autunno. Se arrivi ai piedi cotto dal lavoro di squadra, sali a 200-220W: sono 9 TSS, non è un problema.
- km 1-2 all'8,5-9,1% → LA TRAPPOLA: parti a 230-240W e sali, non inseguire
- km 3-11 al 4,6-5,3% → tratto regolare
- km 12-13 al 10,7% e 9,1% → il muro
- km 14-15 al 6,5% e 9,2% → arrivo
Rapporti: sui muri non scendere sotto 60 rpm. Con 34x30 a 240W sul 10,7% sei a 63 rpm; con 34x28 a 58 rpm. Se hai un 30 o 32, montalo.

LE 3 COSE CHE CONTANO PIÙ DEI WATT
1. CHO 320-390 g TOTALI (80-90 g/h): mangia ogni 20' DAL KM 5, non quando hai fame. La salita arriva dopo 3h15, cioè quando finisce il glicogeno.
2. Punto-a-punto: arrivo a 1268 m, +1091 m netti. Piano per il rientro + qualcosa di caldo in cima.
3. Non partire disidratato.

DURATA ATTESA 4h00-4h20 · TSS 195-230.
NB: watt su CP 273 stimato dalla curva 42gg. Ricalibrare dopo il test del 29/07."""

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
