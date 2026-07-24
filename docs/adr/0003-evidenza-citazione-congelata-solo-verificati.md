# Citazione dell'evidenza congelata, senza tabella di paper canonici

**Status:** accepted

Un Blocco cita lavori del knowledge base per giustificarsi, ma nel KB un lavoro **non è
un'entità globale**: `make_record_id` include il `research_id`, quindi lo stesso lavoro in
ricerche diverse riceve id diversi. Decidiamo che la Citazione è **congelata** — fotografa
titolo, DOI/PMID, verdetto di verifica, qualità e trasferibilità dello studio dentro il
Blocco — e conserva un puntatore *soft* al record corrente; e che **non** introduciamo una
tabella di "paper canonici".

## Considered Options

- **Citare il record research-scoped** — fragile: ri-lanciare la ricerca o cambiare lo slug
  del topic orfana la citazione.
- **Introdurre un'identità canonica di paper** — schema in più il cui unico scopo (stabilità
  del riferimento) è già garantito dal congelamento.

## Consequences

- Il puntatore soft può diventare *orfano* se il record cambia o sparisce, ma lo **snapshot
  resta valido**: la validità storica non dipende dalla stabilità dell'id.
- Sono citabili **solo Evidenze verificate** (invariante di dominio, vedi `CONTEXT.md`):
  nessuna letteratura inventata o non verificata entra in un Piano.
