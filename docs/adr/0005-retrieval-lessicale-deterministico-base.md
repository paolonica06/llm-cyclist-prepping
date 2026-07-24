# Retrieval lessicale deterministico come base; embedding/LLM solo tier opzionale

**Status:** accepted

La Fase C aggiunge un Retriever sull'Evidenza verificata. La scelta ovvia per un RAG
sarebbe un indice di **embedding** (vector DB). Decidiamo invece che la **base** del
Retriever è **lessicale e deterministica** (BM25 / TF-IDF con espansione dei sinonimi di
dominio), e che l'eventuale **riordino semantico** via embedding/LLM è un **tier opzionale**
attivo solo se l'LLM è disponibile, con degradazione graziosa al lessicale.

## Considered Options

- **Embedding / vector DB come base** — qualità semantica migliore, ma richiede un modello
  (rete/LLM), **rompe il vincolo offline-first** del progetto (i test girano con
  `KB_FORCE_OFFLINE=1`, senza rete né LLM), introduce dipendenze ML pesanti e non-determinismo.

## Consequences

- Il Retriever è **riproducibile** (stessa query → stesso ordine) e **testabile offline**,
  coerente col resto della pipeline.
- La qualità è lessicale: i sinonimi di dominio mitigano, ma la comprensione semantica fine
  arriva solo col tier opzionale (quando c'è un LLM).
- Il Retriever recupera **solo Evidenza verificata** ed è **conflict-aware** (rappresenta
  entrambe le Direzioni dell'evidenza) — vedi `CONTEXT.md`.
