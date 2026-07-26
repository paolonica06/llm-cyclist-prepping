#!/usr/bin/env bash
# Hook SessionStart: sincronizza i dati atleta da intervals.icu a inizio sessione.
# In background e SILENZIOSO: non deve mai bloccare né far fallire l'avvio.
# La "scheda stato atleta" (hook UserPromptSubmit) leggerà i dati appena aggiornati;
# il campo "Aggiornato al" mostra la freschezza.
#
# Finestra: 60 giorni indietro (wellness/attività recenti) → 90 avanti (gare +
# pianificato del calendario). Le proiezioni CTL/ATL future non sporcano la scheda,
# che ancora "oggi" all'ultimo giorno MISURATO.

cd "$(dirname "$0")/.." 2>/dev/null || exit 0

OLDEST=$(python3 -c "import datetime;print((datetime.date.today()-datetime.timedelta(days=60)).isoformat())" 2>/dev/null) || exit 0
NEWEST=$(python3 -c "import datetime;print((datetime.date.today()+datetime.timedelta(days=90)).isoformat())" 2>/dev/null) || exit 0

PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python

"$PY" -m cyclist_kb.cli athlete-sync i215294 --oldest "$OLDEST" --newest "$NEWEST" >/dev/null 2>&1
exit 0
