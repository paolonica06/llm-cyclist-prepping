# ROADMAP.md — Roadmap, todo e cose fatte

> **Come funziona (fonte unica di verità).** Questo file è mantenuto **da me
> (l'agente)** e versionato in Git. È la roadmap *strategica*: fasi, cosa è fatto,
> cosa manca. Il dettaglio *tattico* del task in corso vive nel relativo piano in
> `docs/superpowers/plans/…` (con checkpoint), mentre durante l'esecuzione uso la
> task-list della sessione. A fine task faccio il **roll-up** qui.
>
> **Comandi conversazionali:** «aggiorna la roadmap», «segna X come fatto»,
> «cosa manca / qual è il prossimo passo», «apri il piano per <fase>».
> Legenda: `- [x]` fatto · `- [~]` in corso · `- [ ]` da fare.

Ultimo aggiornamento: 2026-07-24 · Test: **89 verdi** · Stato: **Fase B live ok** · **Fase A** corpus 18 temi + arricchimento LLM notturno + comando **`reassess`** (ri-arricchisce senza rifare search/verify) · **Fase C retriever IMPLEMENTATO** (deterministico, validato live).

---

## ✅ Fatto

- [x] **Fase 0 — MVP "backbone evidenze"** (pipeline scientifica auto-mantenuta)
  - [x] Architettura + schemi dati (Pydantic, stati, SQLite)
  - [x] 4 client bibliografici (PubMed, OpenAlex, Semantic Scholar, Crossref) + citation chasing
  - [x] Dedup (DOI→PMID→firma) con guard sui conflitti; Screening; Verification (gate); Extraction; Quality; Synthesis; Athlete Context
  - [x] CLI (`research …`) + API FastAPI + wiki Markdown versionata su Git
  - [x] Demo end-to-end su «interval training and VO2max in trained competitive cyclists»
  - [x] **34 test** verdi; pyflakes pulito
- [x] **Revisione multi-agente + fix**: 26 problemi confermati corretti (dedup, gate di verifica, crash autori, sintesi cumulativa, ecc.)
- [x] **Setup skill + guardrail**: 18 skill (livello repo), protezione Git attiva, routing autonomo delle skill, `docs/AGENT_WORKFLOW.md`

> ✅ **Committato e pushato** su `origin`
> (github.com/paolonica06/llm-cyclist-prepping), branch `main`. Push autonomo
> attivo: da qui in poi committo e pusho a ogni fase chiusa.

---

## 🔨 In corso

- [~] **Fase B — Modello dati atleta longitudinale** — *implementazione completa, verifica live pendente*
  - Requisiti → PRD → dominio → piano → **implementazione + code review**: fatti. Artefatti:
    [PRD](specs/fase-b-atleta-longitudinale.md) · [glossario](../CONTEXT.md) · [ADR](adr/) ·
    [piano](superpowers/plans/fase-b-atleta-longitudinale.md) ·
    **[report autonomo](specs/fase-b-report-autonomo.md)**.
  - Consegnato: modello dati (`athlete_models.py`) + 7 tabelle SQLite + ingestione intervals.icu
    (morning sync idempotente, separato dalla pipeline paper) + metriche derivate + invarianti
    (gate citabilità solo-verificati, congelamento immutabile). **66 test verdi**, pyflakes pulito.
  - **Verifica live FATTA** (athlete i215294: 1216 serie storiche + 148 attività; mappatura confermata
    campo-per-campo; bug TSB trovato e corretto — derivata come identità CTL−ATL). Resta opzionale il
    **wiring della curva di potenza** e alcuni campi wellness non mappati (readiness/rampRate/vo2max).
- [~] **Fase A — Corpus wiki** — 18 temi costruiti (euristica, 360 studi verificati); **arricchimento LLM
  notturno** in corso (Action `enrich-corpus`, backend Claude Code + Codex, batching, registro `enriched.txt`).
  Comando **`research reassess <id>`**: ri-esegue *solo* gli step LLM (screening→extract→quality→synthesize)
  sui record già verificati, **senza** rifare search/verify (niente rate-limiting bibliografico; sblocca Codex locale).
- [~] **Fase C — Retrieval/RAG** — requisiti (`grill-me`) + PRD (`to-spec`) fatti:
  [PRD](specs/fase-c-retrieval-rag.md). **Prossimo:** `domain-modeling` → `writing-plans` → implementazione.
  Retriever deterministico offline: in-tema-prima, qualità, personalizzato, **conflict-aware**, solo verificati,
  **pozzo unico cross-tema**; generazione = operatore/Claude Code/Fase D (non è il deliverable).

---

## ⏳ Prossimi passi (backlog)

- [~] **Fase A — Corpus wiki** — 18 temi (2 batch) → 360 studi verificati; arricchimento LLM notturno a blocchi
  - [x] Backend LLM Claude Code (`claude -p`, Sonnet) + Codex (`codex exec`) con **batching** (N record/chiamata)
  - [x] Action `enrich-corpus` notturna con registro `enriched.txt` (avanza sui temi non fatti)
  - [x] Comando **`reassess`**: ri-arricchimento LLM sui record verificati senza search/verify (estrazione scopata
    al pool → niente fetch OA né token sprecati sui needs_review); 5 test; verificato live sul corpus reale
- [~] **Fase B — Modello dati atleta longitudinale** → dettaglio in [PRD](specs/fase-b-atleta-longitudinale.md) · [report](specs/fase-b-report-autonomo.md)
  - [x] Requisiti (`grill-me`) → PRD (`to-spec`) → dominio (`domain-modeling`) → piano (`writing-plans`)
  - [x] Schema serie storiche + piano versionato/congelato + memoria trasferibilità
  - [x] Ingestione da **API intervals.icu** (morning sync) — *offline-tested; verifica live pendente*
  - [x] Metriche derivate (compliance, delta-test) + test (**67 verdi**)
  - [x] Verifica live con API key (sync reale ok; fix TSB=CTL−ATL)
  - [ ] *(opzionale)* wiring curva di potenza + campi wellness extra
- [~] **Fase C — Retrieval/RAG sulla wiki** → [PRD](specs/fase-c-retrieval-rag.md) · [piano](superpowers/plans/fase-c-retrieval-rag.md)
  - [x] Requisiti (`grill-me`) → PRD (`to-spec`) → dominio (`domain-modeling`, ADR-0005) → piano (`writing-plans`)
  - [x] **`retrieval.py` implementato**: pozzo unico verificato, pertinenza BM25-lite in-tema-prima, qualità+personalizzazione, conflict-aware; CLI `research retrieve`. 7 test; **84 verdi**; validato live sul corpus reale
  - [ ] *(dopo)* tier LLM/embedding-rerank opzionale + endpoint API
- [ ] **Fase D — CoachAgent + feedback loop** (analisi stato → piano/aggiustamenti citati; log esecuzione→esito)
- [ ] **Fase E — Interfaccia conversazionale** ("chiedi al preparatore") su CLI/API/GUI

---

## Convenzioni di aggiornamento

1. **Un solo posto per lo stato strategico**: questo file. Niente todo sparse.
2. **Ogni fase, prima di "fatto"**, passa i gate di `docs/AGENT_WORKFLOW.md` §4
   (test verdi + evidenza mostrata via `verification-before-completion`).
3. **Piani di dettaglio**: `writing-plans` crea `docs/superpowers/plans/<slug>.md`;
   qui in "In corso" metto solo il link + stato sintetico.
4. **Handoff**: la skill `handoff` referenzia questo file, così una nuova sessione
   riparte leggendo `ROADMAP.md` + il piano attivo.
5. **Git = audit-log del fatto**: committo i milestone (commit locale; push bloccato).
