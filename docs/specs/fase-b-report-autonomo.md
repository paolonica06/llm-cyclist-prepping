# Fase B — Report del lavoro autonomo

> Prodotto durante la sessione autonoma autorizzata (implementazione notturna).
> Data: 2026-07-24. Stato: **implementazione completa e verificata offline** (66 test verdi);
> resta la **verifica live** di intervals.icu, che richiede la tua API key.

## 1. Cosa serve SPECIFICAMENTE da te

1. **API key intervals.icu** → `KB_INTERVALS_ICU_API_KEY`.
   La generi in intervals.icu: *Settings → Developer Settings* (in fondo). Mettila nel file
   `.env` alla radice del progetto:
   ```
   KB_INTERVALS_ICU_API_KEY=la_tua_chiave
   ```
   Serve **solo** per la verifica live: tutta la suite gira offline con stub, quindi il codice
   è già testato senza chiave.

2. **Il tuo `athlete_id` intervals.icu** (numerico, lo vedi nell'URL del tuo profilo) per lanciare:
   ```
   research athlete-sync <athlete_id> --oldest 2026-01-01
   ```
   Attesi in output: N serie storiche + N attività. Poi controlla il DB (o aggiungeremo un
   comando `athlete-status`).

3. **Conferma dei nomi-campo dell'API** (li ho mappati dai doc ufficiali, ma vanno visti sul
   payload reale): wellness `ctl`/`atl`/`form`→TSB, `restingHR`/`hrv`/`weight`/`sleepSecs`;
   attività `icu_training_load`(TSS)/`icu_intensity`(IF)/`start_date_local`/`moving_time`.
   Se un nome differisce, si aggiusta la mappa in `clients/intervals_icu.py` (5 minuti).

4. **Decisioni da confermare o ribaltare** (sezione 2): in particolare il nome canonico
   **"Valutazione"** (vs "test") e il **confine di fase**.

## 2. Decisioni prese in autonomia (tutte ribaltabili)

| # | Decisione | Perché | Come ribaltarla |
|---|-----------|--------|-----------------|
| 1 | Nome canonico **"Valutazione"** per la misura fisiologica (FTP/ramp/VO₂max), non "test" | "test" nel repo = pytest: collisione | «rinomina Valutazione → Test (fisiologico)»: aggiorno glossario + eventuali riferimenti |
| 2 | **Confine di fase**: Fase B = *contenitore* (schema/ingestione/metriche/test). Generazione del piano = **Fase D**, RAG = **Fase C** | Il modello va progettato ora; l'intelligenza dopo | Se vuoi già un generatore di piano minimale in Fase B, lo aggiungo |
| 3 | I campi variabili del profilo (`ftp_w`, `vo2max`, `weekly_*`) **non sono più autoritativi**: la verità è la serie storica. `AthleteProfile` resta legacy | Evitare due verità sullo stesso numero | — (è coerente col PRD) |
| 4 | **Ingestione ristretta a solo intervals.icu** (il ROADMAP citava anche .fit/CSV/Strava/Garmin) | intervals.icu è l'hub che già aggrega Strava/Garmin/.fit | «aggiungi connettore X»: è additivo |
| 5 | **Piano come aggregato** (blocchi inline nel blob del piano), non tabella blocchi separata; versioning = nuova versione di piano | Dati mono-atleta minuscoli; niente join | Si può normalizzare in una tabella `blocks` se serviranno query per-blocco |
| 6 | **Soglia di compliance = 0.8** (`DEFAULT_COMPLIANCE_THRESHOLD`) | Default ragionevole | Parametro: cambialo o passalo esplicito |
| 7 | Dato **readiness mancante** → flag `stale` sul `TimeseriesPoint` (carry-forward modellato, non applicato automaticamente) | Tracciare l'onestà del dato | La politica di riempimento la decidiamo in Fase D |
| 8 | Protocolli di Valutazione iniziali: **{ftp, ramp, vo2max}** | I più comuni | Aggiungo enum (es. `MAP`, `sprint`) su richiesta |
| 9 | **Curva di potenza**: modello + storage pronti (`MetricType.POWER_CURVE`), ma il **fetch live NON è ancora wired** (endpoint dedicato più complesso) | Priorità a wellness/fitness/attività | Lo completo quando confermi che ti serve la curva |
| 10 | `supersede` → `next_version` (puro) + `Database.supersede_plan` (transizione atomica) | Rilievo della code review | — (miglioria) |
| 11 | Piano di implementazione scritto **direttamente** (non via skill `writing-plans`) | Efficienza token | — |
| 12 | Report e piano in **`docs/`** (non `.scratch/`) | Durabilità (tua scelta prima di dormire) | — |

## 3. Cosa NON ho fatto (limiti onesti dello scope)

- **Verifica live** dell'ingestione intervals.icu (manca la key) → punto 1.
- **Wiring live della curva di potenza** (endpoint dedicato) → decisione #9.
- **Generazione del piano** (Fase D) e **RAG** (Fase C) — fuori scope Fase B.
- **UI/grafici** (Fase E).

## 4. Cosa ho consegnato

- **Modello dati** (`cyclist_kb/athlete_models.py`): Athlete, TimeseriesPoint, ActivitySummary,
  Race (A/B/C), Assessment, Prescription (supported/unsupported), EvidenceCitation (congelata),
  TrainingBlock (`freeze`), TrainingPlan (`next_version`), TransferabilityMemo (verdetto + confidenza + caveat).
- **Persistenza** (`cyclist_kb/db.py`): 7 tabelle nuove (stesso pattern blob-JSON+indici) + metodi
  Database; `supersede_plan` atomico.
- **Ingestione** (`cyclist_kb/clients/intervals_icu.py` + `agents/athlete_sync.py`): client con auth
  Basic, degradazione offline, morning sync idempotente separato dalla pipeline paper; CLI
  `research athlete-sync`.
- **Metriche + invarianti** (`cyclist_kb/athlete_metrics.py`): compliance, delta valutazioni,
  blocco eseguito; gate di citabilità (solo evidenza verificata) e congelamento immutabile.
- **Test**: 32 nuovi test (persistenza, ingestione, metriche, invarianti, CLI). **Totale 66 verdi**, pyflakes pulito.
- **Docs**: PRD, glossario `CONTEXT.md`, 4 ADR, piano di implementazione.

## 5. Come verificare tu

```bash
.venv/bin/python -m pytest -q          # atteso: 66 passed
# con la key nel .env:
research athlete-sync <athlete_id> --oldest 2026-01-01
```
