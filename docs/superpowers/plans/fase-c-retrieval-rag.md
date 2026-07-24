# Piano di implementazione — Fase C: Retrieval/RAG

> Fonte: PRD `docs/specs/fase-c-retrieval-rag.md` · glossario `CONTEXT.md` · ADR `docs/adr/0005`.
> Metodo: **TDD**, **offline** (`KB_FORCE_OFFLINE=1`), riusando `textutil`, `domain`, `dedup`,
> `synthesis._direction`, `db.list_records`. Commit a ogni milestone verde. `- [ ]`/`- [x]`.

## Invarianti
- Recupera **solo Evidenza verificata** (`verification.verified` + stato `METADATA_VERIFIED`/`SYNTHESIZED`).
- **Deterministico/offline** di base; LLM/embedding = tier opzionale (graceful degradation).
- **Conflict-aware**: l'output rappresenta entrambe le Direzioni quando esistono.
- **Nessuna nuova persistenza**: legge il Pozzo dai record esistenti.

## Milestone A — Retriever core (`cyclist_kb/retrieval.py`, funzioni pure)

- [ ] **A1.** `verified_pool(db) -> List[PaperRecord]`: raccoglie i record verificati attraverso TUTTE
  le ricerche e li **deduplica** (riusa `dedup.deduplicate` / firma paper) → Pozzo unico cross-tema.
  *Verifica:* record non verificati esclusi; stesso paper in 2 ricerche → 1.
- [ ] **A2.** Pertinenza lessicale: `_idf(pool)` (document frequency dei token) + `relevance(query, rec, idf)`
  BM25-lite su titolo+abstract+affermazioni, con espansione query via `domain.SYNONYMS` e `textutil.tokens`.
  *Verifica:* studio in-tema > studio fuori-tema; token raro pesa più di comune.
- [ ] **A3.** Punteggio qualità+personalizzazione: `_quality(rec)` (confidence+methodological → ordinale),
  `_fit(rec, athlete)` (bonus `population=cycling`/`transferability=high`; malus untrained/altro sport).
  *Verifica:* a parità di tema, cycling/high prima di untrained/other.
- [ ] **A4.** Direzione: `_direction_of(rec)` riusa `agents.synthesis._direction` sul testo results/outcomes.
  *Verifica:* studio "increased" → positive; "no difference" → null.
- [ ] **A5.** `retrieve(db, query, athlete, k=8) -> List[Result]`: pool → filtro pertinenza (soglia) →
  ordina per (qualità+fit, pertinenza tiebreak) → **selezione conflict-aware** (garantisce il miglior
  "a favore" e il miglior "contro/nullo" se esistono). Ogni `Result` porta record, punteggi, segnali, direzione.
  *Verifica (TDD):* `tests/test_retrieval.py` — solo-verificati, in-tema-prima, personalizzazione,
  conflict-aware (entrambe le facce), determinismo (stessa query→stesso ordine). Verde.

## Milestone B — CLI

- [ ] **B1.** Comando `research retrieve "<query>" --athlete <id>` (thin wrapper) + `Pipeline.retrieve` o
  chiamata diretta al modulo; stampa i risultati (studio, direzione, qualità/trasferib., pertinenza).
  *Verifica (TDD):* `tests/test_cli_retrieve.py` con `CliRunner` (instradamento + output). Verde.

## Milestone C — Verifica e chiusura

- [ ] **C1.** `pytest -q` completo verde (esistenti + nuovi); pyflakes pulito; output mostrato.
- [ ] **C2.** Aggiornare ROADMAP (Fase C implementata); commit+push.
- [ ] *(dopo)* Tier LLM-rerank opzionale + endpoint API — non bloccanti.

## Checkpoint
- Requisiti+PRD+dominio fatti. Prossimo passo non verificato: **A1**.
- Default (ribaltabili): K=8; pertinenza lessicale BM25-lite fatta in casa (nessuna dipendenza);
  soglia pertinenza tarata sui test; personalizzazione mono-atleta (profilo Fase B).
