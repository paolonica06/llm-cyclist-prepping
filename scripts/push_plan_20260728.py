#!/usr/bin/env python3
"""Push mirato sul calendario intervals.icu — microciclo 28/07-30/07 2026.

Sposta il TEST CP dal 28/07 al 29/07 mantenendo il volume settimanale invariato, e
ricalibra i target del test sulla curva di potenza reale a 42 giorni (il calendario
li aveva tarati sullo storico assoluto).

NON è un push cieco, per costruzione:
  1. rilegge gli eventi live e verifica che il nome corrisponda a quello atteso
     (se il calendario è cambiato dopo il nostro sync, si ferma);
  2. salva il payload originale su file, così il rollback è possibile;
  3. stampa il diff e, senza `--apply`, non scrive nulla.

    python scripts/push_plan_20260728.py             # dry-run: mostra il diff
    python scripts/push_plan_20260728.py --apply     # scrive su intervals.icu
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

TEST_DESCRIPTION = """Protocollo da RIPETERE IDENTICO il 25/8 e il 28/9: stessa bici, stesso power meter, stesso recupero, stesso ordine degli sforzi. Target ricalibrati sulla curva 42 giorni reale (3' 430W, 12' 308W) e sul fit CP 269-276W / W' 27-29 kJ, NON sullo storico assoluto.

3': partire a 435W, non sprintare ai blocchi. 12': partire a 305W e salire, mai uscire a 320+.

- 25m 140-230W intensity=warmup

3x
- 40s 300-320W
- 3m 130-150W intensity=rest

- 8m 140-170W intensity=rest

- 3m 425-435W

- 30m 130-170W intensity=rest

- 12m 305-315W

- 10m 120W intensity=cooldown"""

# (data, id evento, nome atteso ORA sul calendario, patch da applicare)
CHANGES = [
    (
        "2026-07-28",
        124970692,
        "🎯 TEST CP 3'+12' (all-out) → FTP reale",
        {
            "name": "🟢 Z2 endurance 1h50 (pre-test)",
            "description": "Giorno pre-test: Z2 pulita, nessuno spunto, nessuna salita forzata. Serve il volume, non lo stimolo.\n\n- 110m 195-225W",
            "moving_time": 6600,
        },
    ),
    (
        "2026-07-29",
        124969205,
        "🟢 Z2 endurance 2h30",
        {
            "name": "🎯 TEST CP 3'+12' → CP/W' reali",
            "description": TEST_DESCRIPTION,
            "moving_time": 5940,
        },
    ),
    (
        "2026-07-30",
        124969206,
        "🟢 Z2 endurance 2h30",
        {
            "name": "🟢 Z2 endurance 3h05",
            "description": "Recupera i 40' spostati da martedì: il volume settimanale resta quello pianificato.\n\n- 185m 195-235W",
            "moving_time": 11100,
        },
    ),
]

# In data/private/ (git-ignored): il backup contiene il calendario personale
# dell'atleta e il repository remoto è pubblico.
BACKUP = (Path(__file__).resolve().parent.parent
          / "data" / "private" / "calendar_backup_20260728.json")


async def main(apply: bool) -> int:
    client = IntervalsClient()
    if not client.available:
        print("ERRORE: client intervals.icu non disponibile (key mancante o offline).")
        return 2

    async with HttpFetcher() as fetcher:
        client._fetcher = fetcher
        live = await client._get(
            f"/athlete/{ATHLETE}/events", {"oldest": "2026-07-28", "newest": "2026-07-30"}
        )
        if not live:
            print("ERRORE: nessun evento letto dal calendario. Interrotto.")
            return 2
        by_id = {int(e["id"]): e for e in live if e.get("id") is not None}

        # 1. Verifica di sicurezza: il calendario è ancora quello che abbiamo letto?
        planned = []
        for date, event_id, expected_name, patch in CHANGES:
            current = by_id.get(int(event_id))
            if current is None:
                print(f"ERRORE {date}: evento {event_id} non trovato sul calendario. Interrotto.")
                return 3
            if current.get("name") != expected_name:
                print(f"ERRORE {date}: evento {event_id} si chiama ora "
                      f"{current.get('name')!r}, atteso {expected_name!r}.\n"
                      "Il calendario è cambiato dopo il sync: rileggilo prima di scrivere.")
                return 3
            planned.append((date, event_id, current, patch))

        # 2. Backup prima di qualunque scrittura.
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(
            json.dumps([c for _, _, c, _ in planned], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"Backup dei 3 eventi originali: {BACKUP}\n")

        # 3. Diff.
        for date, event_id, current, patch in planned:
            print(f"── {date}  (evento {event_id})")
            print(f"   nome    : {current.get('name')}")
            print(f"          → {patch['name']}")
            print(f"   durata  : {(current.get('moving_time') or 0) / 60:.0f}m"
                  f" → {patch['moving_time'] / 60:.0f}m")
            print(f"   descr.  : {(current.get('description') or '')[:60]!r}…")
            print(f"          → {patch['description'][:60]!r}…\n")

        if not apply:
            print("DRY-RUN: niente è stato scritto. Riesegui con --apply per inviare.")
            return 0

        # 4. Scrittura.
        failed = 0
        for date, event_id, _current, patch in planned:
            res = await client.update_event(ATHLETE, event_id, patch)
            if res.ok:
                print(f"OK   {date} evento {event_id} aggiornato (HTTP {res.status})")
            else:
                failed += 1
                print(f"FAIL {date} evento {event_id}: HTTP {res.status} — {res.error}")
        if failed:
            print(f"\n{failed} scrittura/e fallita/e. Rollback manuale da {BACKUP}.")
            return 1
        print("\nTutti gli eventi aggiornati. Rilancia athlete-sync per riallineare il DB.")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Scrive davvero su intervals.icu.")
    raise SystemExit(asyncio.run(main(ap.parse_args().apply)))
