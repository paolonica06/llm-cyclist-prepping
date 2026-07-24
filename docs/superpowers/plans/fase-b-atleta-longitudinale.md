# Piano di implementazione — Fase B: modello dati atleta longitudinale

> Fonte: PRD `docs/specs/fase-b-atleta-longitudinale.md` · glossario `CONTEXT.md` · ADR `docs/adr/0001..0004`.
> Metodo: **TDD** (test prima), **offline** (`KB_FORCE_OFFLINE=1` già globale in `tests/conftest.py`),
> estendendo i pattern esistenti (`Database` blob-JSON+indici; client via `HttpFetcher`; stub sull'istanza).
> Commit+push a ogni milestone verde. Legenda: `- [ ]` da fare · `- [x]` fatto e verificato.

## Vincoli invarianti (da rispettare in ogni passo)
- Citabile **solo** evidenza verificata (`RecordState.METADATA_VERIFIED`/`SYNTHESIZED` + `verification.verified`).
- Metriche CTL/ATL/TSB **ingerite**, mai ricalcolate.
- Giudizi sul passato ancorati a **snapshot congelati**. Mono-atleta. Resta su **SQLite**.
- Dati intervals.icu **non** passano dalla pipeline paper: entità proprie, entry-point separato.

---

## Milestone A — Modello dati e persistenza

- [ ] **A1.** Nuovo modulo `cyclist_kb/athlete_models.py` con enum + modelli Pydantic:
  `MetricType` (sleep/hrv/weight/resting_hr/ctl/atl/tsb/ftp/power_curve), `RacePriority` (A/B/C),
  `AssessmentProtocol` (ftp/ramp/vo2max), `BlockState` (planned/executed/frozen),
  `PlanStatus` (active/superseded), `TransferabilityVerdict` (transferred/not_transferred/inconclusive);
  modelli `Athlete`, `TimeseriesPoint`, `Race`, `Assessment`, `Prescription`, `EvidenceCitation`,
  `TrainingBlock`, `TrainingPlan`, `TransferabilityMemo`.
  *Verifica:* `python -c "import cyclist_kb.athlete_models"` senza errori; pyflakes pulito.
- [ ] **A2.** Estendere `SCHEMA` in `db.py` con tabelle `athletes`, `athlete_timeseries`, `races`,
  `assessments`, `plans`, `blocks`, `transferability_memos` (blob-JSON + colonne indicizzate;
  citazioni congelate *dentro* il blob del blocco → nessuna tabella citazioni separata).
  *Verifica:* creare una `Database(tmp)` non solleva; le tabelle esistono (`sqlite_master`).
- [ ] **A3.** Metodi `Database` paralleli: athlete CRUD; `add_timeseries_point`/`list_timeseries`
  (upsert idempotente su `(athlete_id, metric_type, date)`); race CRUD; assessment upsert/list;
  plan create/get/list/`supersede`; block upsert/get/list; memo upsert/list.
  *Verifica (TDD):* `tests/test_athlete_persistence.py` — round-trip di ogni entità, idempotenza
  della serie storica, query per atleta/stato/versione. `pytest -q` verde.

## Milestone B — Ingestione intervals.icu (offline-tested)

- [ ] **B1.** `Settings.intervals_icu_api_key: Optional[str]` (`KB_INTERVALS_ICU_API_KEY`);
  piccola estensione `HttpFetcher.get_json(..., headers=None)` per l'auth Basic.
  *Verifica:* import ok; test esistenti ancora verdi.
- [ ] **B2.** `cyclist_kb/clients/intervals_icu.py` — `IntervalsClient(fetcher=None)` che riusa
  `HttpFetcher` + auth Basic dalla key; metodi `fetch_wellness/fetch_activities/fetch_fitness/
  fetch_power_curve`. **Se manca la key o offline → ritorna liste vuote** (nessuna eccezione).
  *Verifica (TDD):* `tests/test_intervals_client.py` — senza key ritorna `[]`; con fetcher stub
  normalizza il payload nei modelli. Verde.
- [ ] **B3.** `cyclist_kb/agents/athlete_sync.py` — `AthleteSyncAgent(db).run(athlete_id)` idempotente
  (upsert serie storiche); CLI `research athlete-sync <id>` + `Pipeline.sync_athlete`. Separato dalla
  pipeline paper.
  *Verifica (TDD):* `tests/test_athlete_sync.py` — stub client, doppio run → nessun duplicato;
  offline (no key) → no-op pulito. Verde.

## Milestone C — Metriche derivate + invarianti

- [ ] **C1.** `cyclist_kb/athlete_metrics.py` (funzioni pure): `compliance(planned, executed)`,
  `test_delta(assessments)`, `derive_executed_block(planned_block, activities)`.
  *Verifica (TDD):* `tests/test_athlete_metrics.py` casi noti in/out. Verde.
- [ ] **C2.** Gate citabilità + congelamento: `citable_evidence(record) -> bool`,
  `freeze_citation(record) -> EvidenceCitation` (rifiuta i non verificati), `TrainingBlock.freeze(...)`,
  `TrainingPlan.supersede(...)`.
  *Verifica (TDD):* `tests/test_athlete_invariants.py` — gate rifiuta non verificati; ri-pianificare non
  muta lo snapshot congelato; verdetto di trasferibilità porta confidenza/caveat. Verde.

## Milestone D — Verifica e chiusura

- [ ] **D1.** `pytest -q` completo verde (34 esistenti + nuovi) con output mostrato; pyflakes pulito.
- [ ] **D2.** Code review (multi-agente) sui nuovi file; fix dei problemi confermati; test ancora verdi.
- [ ] **D3.** Aggiornare `docs/ROADMAP.md` (sotto-task Fase B) e stato PRD; `docs/specs/fase-b-report-autonomo.md`
  (input richiesti all'utente + decisioni autonome). Commit+push finale.

---

## Checkpoint / stato
- **Milestone A, B, C, D: FATTE e verificate offline** (66 test verdi, pyflakes pulito, code review
  applicata). Unico passo aperto: **verifica live intervals.icu** (serve `KB_INTERVALS_ICU_API_KEY`)
  + wiring della curva di potenza. Vedi `docs/specs/fase-b-report-autonomo.md`.
- Decisioni autonome su open item (default, ribaltabili — dettaglio nel report D3):
  soglia compliance = 80% del carico/durata pianificati; dato readiness mancante = si usa l'ultimo
  disponibile con flag `stale`; protocolli test iniziali = {ftp, ramp, vo2max}; termine canonico
  "Valutazione" (non "test").
