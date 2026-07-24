# Stato PROPOSED e transizione atomica proponi-poi-approva

**Status:** accepted

Il CoachAgent genera automaticamente Piani di allenamento, ma un Piano non
deve diventare attivo senza revisione umana: un errore di parametro (target
irraggiungibile, carico eccessivo) richiederebbe un rollback difficile se il
Piano fosse già attivo. Al contempo, il sistema deve evitare che rimangano
in giro bozze orfane di Piani proposti mai approvati. Decidiamo un ciclo
proponi-poi-approva con invarianti stretti.

## Considered Options

- **Creazione diretta come ACTIVE** — inaccettabile: viola il principio di
  supervisione umana su decisioni di allenamento e rende testabile solo a
  posteriori.
- **Draft come entità separata** — duplica lo schema; un Draft non
  completato non sarebbe distinto da un Piano in bozza parziale.
- **Attivazione automatica dopo un timeout** — introduce dipendenza dal
  tempo di sistema nei test, incompatibile col vincolo offline/deterministico
  (ADR-0005, `CLAUDE.md`).

## Decision

**`PlanStatus` estende `PROPOSED`** (valore `"proposed"`), aggiunto accanto
agli stati esistenti `ACTIVE` e `SUPERSEDED`. Il ciclo di vita di un Piano è:

```
(nuovo) → PROPOSED → ACTIVE → SUPERSEDED
                ↘ SUPERSEDED   (se sostituito prima dell'approvazione)
```

**Invarianti garantiti:**

1. **Mai due ACTIVE contemporaneamente** per lo stesso atleta: `promote_plan`
   marca `SUPERSEDED` tutti gli ACTIVE correnti prima di attivare il nuovo
   Piano, in un'unica transazione SQLite.
2. **Mai auto-attivazione**: solo `Database.promote_plan` può fare la
   transizione `PROPOSED→ACTIVE`; `CoachAgent.run` crea sempre e solo
   PROPOSED.
3. **Al più un PROPOSED per atleta**: prima di salvare il nuovo PROPOSED,
   `CoachAgent.run` chiama `_supersede_open_proposals`, che marca SUPERSEDED
   tutti i PROPOSED precedenti dello stesso atleta.
4. **`coach-accept` su non-PROPOSED → errore esplicito**: `promote_plan`
   solleva `ValueError` se il Piano non è nello stato PROPOSED; il CLI lo
   cattura e restituisce un messaggio diagnostico. Non è un no-op silenzioso
   (decisione n. 4 in «Decisioni fissate»).

**`Database.promote_plan(plan_id: str) → TrainingPlan`** è un metodo
**distinto** da `supersede_plan` (che assume come input un Piano già ACTIVE
da sostituire). `promote_plan` opera in una singola transazione:
`BEGIN` → `UPDATE` tutti gli ACTIVE dell'atleta a SUPERSEDED → `UPDATE`
il PROPOSED target a ACTIVE → `COMMIT`. Se la transazione fallisce, nessuna
transizione è parziale.

**Versionamento monotono:** la `version` del nuovo PROPOSED è
`(max_version_degli_non-PROPOSED) + 1`. In assenza di piani precedenti, è 1.
Le versioni non decrescono mai; le bozze orfane non "rubano" numeri di versione
agli ACTIVE futuri.

## Consequences

- Un atleta ha sempre **al più un Piano ACTIVE** e **al più un Piano
  PROPOSED** in ogni istante.
- Il test `test_promote_plan_rejects_non_proposed` verifica la casistica di
  errore esplicito; il test `test_promote_plan_atomic_transition` verifica
  che dopo `promote_plan` esista esattamente un ACTIVE e zero ACTIVE
  precedenti.
- I Piani SUPERSEDED rimangono in DB come storico append-only (coerente con
  ADR-0002: l'integrità temporale vale anche per i Piani, non solo per i
  Blocchi congelati).
- Il gate proponi-poi-approva può essere ignorato solo da un operatore che
  chiama direttamente `promote_plan`; il CLI/API standard non offre
  scorciatoie.
