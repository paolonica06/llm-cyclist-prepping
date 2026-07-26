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

Ultimo aggiornamento: 2026-07-26 · Test: **178 verdi** · Stato: **backlog roadmap chiuso (Fasi A–E)**.
Fase B: campi wellness `readiness/rampRate/vo2max` ingeriti (curva di potenza già wired).
Fase C: endpoint API `/retrieve` + tier LLM-rerank opzionale (degrada offline).
Fase D: endpoint API coach + narrativa "da preparatore" (LLM+euristica) + verifica live su i215294 (run→accept→adapt).
Fase E: interfaccia conversazionale «chiedi al preparatore» su **CLI** (`research ask`), **API** (`POST /ask`) e **GUI web** (`GET /`), ancorata a dati+piano+evidenza con provenienza marcata; snapshot `as_of` che esclude le proiezioni future.

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

- _(nessuna fase aperta: backlog roadmap chiuso il 2026-07-26)._ Restano solo idee di
  evoluzione oltre la roadmap originale (vedi "Oltre la roadmap" in fondo).

---

## ⏳ Prossimi passi (backlog)

- [x] **Fase A — Corpus wiki** — 18 temi; **318 record synthesized 100% LLM**; comando `reassess`.
- [x] **Fase B — Modello dati atleta longitudinale** → [PRD](specs/fase-b-atleta-longitudinale.md) · [report](specs/fase-b-report-autonomo.md)
  - [x] Schema serie storiche + piano versionato/congelato + memoria trasferibilità
  - [x] Ingestione **API intervals.icu** (morning sync) + verifica live (fix TSB=CTL−ATL)
  - [x] **Curva di potenza** (multi-periodo + per-attività) wired
  - [x] **Campi wellness** `readiness`/`rampRate`/`vo2max` ingeriti (loop generico `_parse_daily`)
- [x] **Fase C — Retrieval/RAG sulla wiki** → [PRD](specs/fase-c-retrieval-rag.md) · [piano](superpowers/plans/fase-c-retrieval-rag.md)
  - [x] `retrieval.py`: pozzo verificato, BM25-lite in-tema-prima, qualità+personalizzazione, conflict-aware; CLI `research retrieve`
  - [x] **Tier LLM-rerank opzionale** (`rerank=True`/`--rerank`): riordino semantico sopra il lessicale, `_sort_key` unica preserva il conflict-aware, degrada all'identità offline
  - [x] **Endpoint API** `POST /retrieve`
- [x] **Fase D — CoachAgent + feedback loop** → **[PRD](specs/fase-d-coachagent.md)** · **[piano](superpowers/plans/fase-d-coachagent.md)** · ADR [0006](adr/0006-obiettivo-piano-target-metrico-datato.md)/[0007](adr/0007-provenienza-tre-fonti-coaching.md)/[0008](adr/0008-stato-proposed-transizione-atomica.md)
  - [x] Schema provenienza 3-fonti, `PlanStatus.PROPOSED`, obiettivo metrico datato, `promote_plan` atomico
  - [x] `CoachAgent` (`run`/`accept`/`assess_block`/`adapt_microcycle`) + Retriever conflict-aware + CLI
  - [x] **Verifica live** con atleta seminato i215294 (run→accept→adapt sul pozzo reale)
  - [x] **Endpoint API coach** (`/coach/{id}`, `/coach/accept`, `/coach/adapt`, `/coach/assess`, `GET /coach/plans`, `/coach/memos`)
  - [x] **Narrativa coach ricca** (`TrainingPlan.narrative`): ramo LLM `complete_text` + fallback euristico, provenienza marcata
- [x] **Fase E — Interfaccia conversazionale** ("chiedi al preparatore") su CLI/API/GUI
  - [x] `agents/conversation.py` `CoachChatAgent.ask()`: dati misurati + piano + evidenza → risposta NL, LLM+euristica
  - [x] `llm.complete_text` (output libero) + snapshot `as_of` (esclude le proiezioni future)
  - [x] CLI `research ask`, endpoint `POST /ask`, **GUI web** vanilla (`GET /`, `cyclist_kb/web/chat.html`)

---

## 🌱 Oltre la roadmap (idee, non impegnate)

- Fix del `_last_value`/loop-veloce del CoachAgent affinché legga lo stato "a oggi"
  e non la **proiezione futura** di intervals.icu (stesso tema risolto in Fase E per lo
  snapshot; il coach ha però il vincolo di design "no `date.today()`").
- Tier embedding-rerank vero (oltre l'LLM-scoring) + endpoint API per `ask` con storia/sessione.
- Narrativa coach in streaming; autenticazione della GUI se esposta fuori da localhost.

---

## Convenzioni di aggiornamento

1. **Un solo posto per lo stato strategico**: questo file. Niente todo sparse.
2. **Ogni fase, prima di "fatto"**, passa i gate di `docs/AGENT_WORKFLOW.md` §4
   (test verdi + evidenza mostrata via `verification-before-completion`).
3. **Piani di dettaglio**: `writing-plans` crea `docs/superpowers/plans/<slug>.md`;
   qui in "In corso" metto solo il link + stato sintetico.
4. **Handoff**: la skill `handoff` referenzia questo file, così una nuova sessione
   riparte leggendo `ROADMAP.md` + il piano attivo.
5. **Git = audit-log del fatto**: committo e pusho i milestone (push autonomo autorizzato;
   force-push/reset restano bloccati).
