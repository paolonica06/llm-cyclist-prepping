# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Protocollo decisioni atleta (coaching) — REGOLA VINCOLANTE

**Trigger.** Quando l'utente (Paolo, atleta `i215294`) pone una domanda decisionale su
allenamento/recupero/gara — es. «mi posso riposare?», «cosa faccio oggi?», «salto o
no?», «reggo questo carico?», «come sto?» — **non** rispondere dal solo piano scritto né
con un'opinione da buon senso. Prima di rispondere esegui SEMPRE, in quest'ordine, e
fonda la risposta su tutto:

1. **Dati misurati** — interroga `data/kb.sqlite3` → `athlete_timeseries` (athlete_id
   `i215294`), metric_type `ctl/atl/tsb/hrv/resting_hr/sleep`(sec)/`weight/power_curve`:
   **trend ultimi ~14 giorni**, non l'ultimo punto. Confronta con le baseline recenti
   (HRV 54,4 ± 9,7 · RHR 50,6 ± 2,3 · alert SWC HRV < 48 · sonno target ≥ 7,5 h) —
   ma **verifica i valori nel DB, non citarli a memoria** (possono cambiare).
2. **Pianificato vs fatto** — il *pianificato* è il **calendario intervals.icu**, ingerito
   in `planned_workouts` (workout con target watt/carico) e `races` (gare `RACE_*` con
   priorità) via `athlete-sync` (`fetch_events`). NON è il piano interno generico. Confronta
   con `activities` (`load`=TSS, `moving_time_s`, `intensity`=IF% su 0-100): cosa era previsto
   vs cosa ha *davvero* fatto. Non assumere che il piano sia stato eseguito.
3. **Evidenza verificata** — `wiki/topics/*.md` pertinenti (HRV-guided, sleep-recovery,
   training-load/overtraining, tapering, ecc.), citando **confidenza e caveat**; niente
   affermazioni non ancorate.
4. **Storico → pattern distruttivi** — analizza lo storico completo (952+ gg) per firme
   ricorrenti e loro *early-warning*; **segnala se il momento attuale assomiglia a una
   firma di rischio nota** (boom-bust ~ogni 4-5 mesi, collisione esami mag-giu/nov-dic,
   firma ramp-dig: ramp 28g > +12/15 CTL · TSB<−25 per >7-10 gg · ACWR>1,5). Watchlist
   completa nella memory `paolo-destructive-patterns`.
5. **Contesto strategico** — `data/report_analisi_atleta_*.md` + piano in `wiki/athlete/`.

**Regole di risposta.** (a) Distingui sempre **«sei costretto a X dai dati»** da **«X è
la scelta migliore»**. (b) Marca la provenienza come fa il piano: `studi` (evidenza) /
`dati_atleta` (N=1) / `euristica` (giudizio). (c) Se una tua affermazione precedente è
contraddetta dai dati, **correggila esplicitamente**. (d) Confine medico: sintomi/RED-S
sospetto → stop + professionista, non un aggiustamento di piano.

**Quando costruisci o modifichi un piano/microciclo — REGOLA VINCOLANTE (errori già commessi).**
1. **Leggi PRIMA il calendario intervals.icu** (`planned_workouts` + `races`, o `fetch_events`):
   gare *e* pianificato vivono lì, non nel nostro DB di default. Esiste già un piano dettagliato
   sul calendario — **NON pianificare né pushare alla cieca sopra**. Su intervals.icu si fa
   pull, non push cieco (ramo mirror).
2. **Non sottostimare il volume.** Verifica le ore/TSS settimanali reali nel DB: i carichi veri di
   Paolo sono **~14-16 h/sett** (le 18 h lo rompono). Non prescrivere ~10 h "di recupero" se i
   dati mostrano che regge di più.
3. **Chiedi le gare** (data, tipo, priorità A/B/C, percorso) se non sono nel calendario/DB: una
   gara cambia struttura e taper. Non trasformare un giorno-gara in "lunga endurance".
Dettaglio in memory `paolo-volume-and-race-calendar`.

## Routing autonomo delle skill (selezione proattiva)

**Seleziona e invoca proattivamente la skill migliore in base all'intento, senza
attendere che l'utente la nomini.** Le skill sono installate in `.claude/skills/`;
il dettaglio operativo è in `docs/AGENT_WORKFLOW.md`. Mappa intento → skill:

- Requisiti vaghi / design da affinare → **grill-me** (o **grill-with-docs** se servono
  ADR/glossario). *Annuncia* l'ingresso in modalità grilling prima di iniziare.
- Requisiti chiari da formalizzare → **to-spec** (produce PRD/spec).
- Terminologia/decisioni di dominio → **domain-modeling**.
- Task multi-step da pianificare → **writing-plans**; eseguire un piano scritto → **executing-plans**.
- Implementare feature/bugfix → **test-driven-development** (test prima).
- Bug / test rossi / comportamento inatteso → **systematic-debugging** (root-cause prima dei fix).
- Sto per dichiarare "fatto/passa/risolto" → **verification-before-completion** (evidenza prima).
- Feature completata / pre-merge → **requesting-code-review** → **receiving-code-review**.
- Ricerca/esplorazione letteratura → **ai-research-explore**; dettaglio specifico di un paper → **paper-context-resolver**.
- File/attività PDF → **pdf**. Note nella wiki → **obsidian-vault** (ripuntata a `wiki/`).
- Fine sessione / passaggio di consegne → **handoff**. «Esiste una skill per…?» → **find-skills** (solo scoperta).

**Conferma prima di invocare** (azioni pesanti/interattive/outward): grilling
(intervista lunga), `handoff` (chiusura sessione), `to-spec`/pubblicazione su tracker,
`ai-research-explore` (rete verso API pubbliche + import dinamici). Per tutto il resto,
invoca direttamente quando l'intento è chiaro.

**Non usare insieme** (sequenziali, non simultanee): grill-me ⟂ grill-with-docs;
intervista → to-spec; to-spec (COSA) → writing-plans (COME) → executing-plans;
requesting → receiving code review; ai-research-explore ⟂ paper-context-resolver.
Vedi `docs/AGENT_WORKFLOW.md` §2 e §4 per gate e dettagli.

## Comandi

```bash
# Ambiente (Python 3.9+; le dipendenze sono già in .venv se presente)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                      # installa il pacchetto + console script `research`

# Test
pytest                                # tutta la suite (config in pyproject.toml)
pytest tests/test_dedup.py -q         # un singolo file
pytest tests/test_verification.py::test_title_mismatch_flags_needs_review   # un singolo test

# Pipeline (CLI). Ogni fase è eseguibile a sé; `run` le concatena.
research run "interval training and VO2max in trained competitive cyclists" --profile profiles/example_athlete.yaml
research create "<topic>" ; research search <id> ; research screen <id> ; research verify <id>
research extract <id> ; research quality <id> ; research synthesize <id> ; research athlete <id> <profile.yaml>
research reassess <id>                # ri-arricchisce (screen→extract→quality→synth) i verificati SENZA search/verify
research status <id>                  # conteggio record per stato
python -m cyclist_kb.cli --help       # equivalente se il console script non è installato

# Demo end-to-end (interroga le API reali, genera la wiki)
python scripts/demo.py

# API HTTP
uvicorn cyclist_kb.api:app --reload
```

Modalità offline: senza `ANTHROPIC_API_KEY` (o con `KB_FORCE_OFFLINE=1`) ogni agente
usa euristiche deterministiche invece dell'LLM. I test girano sempre offline
(`tests/conftest.py` imposta `KB_FORCE_OFFLINE=1`).

## Architettura

Pipeline multi-agente a stati. Il flusso è
`create → search → screen → verify → extract → quality → synthesize → (athlete)`,
orchestrato da `cyclist_kb/pipeline.py` (classe `Pipeline`). CLI (`cli.py`) e API
(`api.py`) sono thin wrapper sopra `Pipeline`; **la logica vive negli agenti**, non
nelle interfacce.

**Contratto condiviso.** Tutto ruota attorno a `models.py`:
- `RecordState` è la macchina a stati; `PaperRecord` è il documento che l'attraversa
  accumulando risultati (`screening`, `verification`, `extraction`, `quality`) senza
  perderli. Gli agenti leggono/scrivono record via `db.Database` (SQLite: ogni record
  è un blob JSON di `PaperRecord` + colonne indicizzate `state/doi/pmid`).
- `make_record_id(research_id, doi, pmid, title)` genera l'id stabile; include il
  `research_id` per evitare collisioni globali nella tabella `records`.

**Pattern trasversale degli agenti** (`agents/*.py`): ognuno ha `run(research)` e un
metodo privato che sceglie fra percorso **LLM** (`llm.get_llm().complete_json(...)`) e
**euristico** (fallback deterministico). Se l'LLM non è disponibile o fallisce, si
degrada all'euristica — mai un'eccezione che blocca la pipeline. Le euristiche
attingono al vocabolario di dominio in `domain.py` (sinonimi, marcatori di
popolazione/disegno) e alle utility di `textutil.py` (normalizzazione titoli, chiave
primo autore, similarità).

**Punti di accoppiamento non ovvi** (richiedono di leggere più file):
- Il **Deduplication Layer** (`dedup.py`) è una funzione pura invocata *dentro*
  `ResearchAgent`, non una fase CLI separata. Fonde per DOI→PMID→firma
  (titolo+anno+primo autore, con fallback fuzzy) e **unisce `source_dbs`**: la
  provenienza multi-fonte di un record dipende interamente da questo merge.
- La **verifica è un gate stringente**: `_decide` richiede che ogni identificatore
  *presente* risolva (un DOI/PMID irrisolvibile → `NEEDS_REVIEW`), che DOI e PMID non
  puntino a lavori diversi (`_cross_check`), e almeno un `title_match` positivo
  confrontato contro **entrambe** le fonti (`_compare_to`/`_aggregate`). Solo
  `METADATA_VERIFIED` prosegue verso `EXTRACTED`→`SYNTHESIZED`; `SynthesisAgent`
  ri-filtra su `verification.verified`. Per il rate-limiting delle API il numero di
  verificati varia di run in run (i non risolti finiscono, correttamente, in review).
- Gli stati `full_text_available`/`abstract_only` sono persistiti nel campo
  `PaperRecord.content_availability` (l'estrazione tenta il full text solo da OA
  non-PDF; vedi `extraction._prepare_source`), mentre lo stato di lifecycle avanza a
  `EXTRACTED`. La provenienza per-campo è in `ExtractedField.source`
  (`metadata`/`abstract`/`full_text`/`not_available`).
- La **dedup ha un guard gerarchico** (`dedup._strong_conflict`): due record con DOI (o
  PMID) forti ma *in conflitto* non vengono mai fusi a uno stadio più debole.
- `QualityAgent` **non deve** usare il conteggio citazioni come misura di qualità
  (vincolo esplicito): valuta campione/controllo/randomizzazione/durata/misure/
  trasferibilità.
- `SynthesisAgent` **non sovrascrive** silenziosamente: la pagina di un topic è
  **cumulativa** su tutte le ricerche con lo stesso slug (`_cumulative_records`, che
  passa i record verificati da `deduplicate`), così una nuova ricerca accumula anziché
  cancellare le evidenze precedenti; mantiene i risultati contrastanti, appende una
  "Cronologia aggiornamenti" e committa su Git (`wiki.commit`, con `status` scopato al
  path wiki). Le pagine sono interconnesse: `index.md → topics/<slug>.md →
  papers/<id>.md` (indice deduplicato per slug).

**Client bibliografici** (`clients/`): `PubMedClient`, `OpenAlexClient`,
`SemanticScholarClient`, `CrossrefClient`, tutti con `search(query, limit,
research_id) -> List[PaperRecord]` e degradazione a lista vuota su errore (via
`clients/base.HttpFetcher`, che gestisce retry/backoff e User-Agent+mailto della
"polite pool"). Crossref e PubMed espongono anche lookup singolo
(`fetch_by_doi`/`fetch_summary`) usati dalla verifica; OpenAlex `fetch_by_id` e le
`references` alimentano il citation chasing.

## Config

`config.py` (`get_settings()`, singleton) legge variabili `KB_*` da ambiente/`.env`.
Rilevanti: `KB_CONTACT_EMAIL` (cortesia verso le API), `KB_FORCE_OFFLINE`,
`KB_RESULTS_PER_SOURCE`, `KB_CITATION_CHASE_*`, `KB_GIT_AUTOCOMMIT`. `ensure_dirs()`
crea `data/`, `data/raw/`, `wiki/{topics,papers,athlete}`, `profiles/`.
`data/kb.sqlite3` e `data/raw/` sono rigenerabili e git-ignored; `wiki/` è
intenzionalmente versionata.
