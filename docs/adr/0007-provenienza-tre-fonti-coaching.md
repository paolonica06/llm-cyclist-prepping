# Provenienza a tre fonti sulle decisioni di coaching

**Status:** accepted

Il CoachAgent deve giustificare ogni decisione (strategia di Blocco, numero
di watt di una Prescrizione) con una fonte tracciabile, per evitare che
l'LLM presenti stime euristiche come se fossero evidenza scientifica
(*evidence laundering*). Il sistema già distingue fonti bibliografiche
(`models.DataSource`) ma quel costrutto è bibliografico (PubMed, OpenAlex,
…) e non si adatta alle decisioni di coaching, dove le tre origini sono
concettualmente diverse: un articolo peer-reviewed, il passato individuale
dell'atleta, o un'euristica parametrica. Decidiamo di introdurre un enum
locale e separato.

## Considered Options

- **Estendere `models.DataSource`** — `DataSource` è un identificatore di
  banca-dati bibliografica (PubMed, OpenAlex, Crossref, Semantic Scholar).
  Aggiungere `HEURISTIC` o `ATHLETE_DATA` mescolerebbero due concetti
  ortogonali, inquinando le query sul corpus bibliografico.
- **Stringa libera per provenienza** — non tipizzato, non validabile; i test
  offline non possono asserire su varianti di stringa.
- **Campo booleano `supported`** — già presente (Fase B) ma binario: non
  distingue «basato su dati reali dell'atleta» da «puro parametro di
  default».

## Decision

Si aggiunge l'enum **`ProvenanceKind(str, Enum)`** in `athlete_models.py`,
**locale a quel modulo** e non importato da `models.py`:

```
ProvenanceKind.STUDY        = "study"         # Evidenza peer-reviewed verificata
ProvenanceKind.ATHLETE_DATA = "athlete_data"  # Dati reali dell'atleta (N=1)
ProvenanceKind.HEURISTIC    = "heuristic"     # Parametro/formula con default espliciti
```

`ProvenanceKind` si applica a due livelli:

1. **`TrainingBlock.provenance`** — giustifica la *strategia* del Blocco
   (es. «questi studi supportano l'HIIT per i ciclisti competitivi»).
   Può essere `STUDY` quando almeno una `EvidenceCitation` verificata
   sostiene la scelta strategica.

2. **`Prescription.provenance`** — giustifica il *numero* (watt, durata,
   ripetizioni). Vige la **regola del range anti-laundering**: un numero
   scelto all'interno di un range di popolazione (anche se derivato da uno
   studio) è `ATHLETE_DATA` o `HEURISTIC`, **mai** `STUDY`. Solo la
   *strategia* (scegliere HIIT vs Z2) può essere `STUDY`; la
   *quantificazione* (388 W per 4 minuti) è sempre adattamento individuale.

**Sincronizzazione con `supported`:** il campo `Prescription.supported: bool`
(Fase B) resta per retrocompatibilità ma diventa *derivato*: un
`@model_validator(mode="after")` impone
`supported == (provenance == ProvenanceKind.STUDY)`. Non esiste stato in
cui `supported=True` e `provenance != STUDY` o viceversa.

**Citazione N=1 (`EvidenceCitation.source_kind`):** l'Evidenza proveniente
dall'atleta stesso — le sue Valutazioni passate, i memo di Trasferibilità
personalizzata — è una fonte distinta e legittima. Si aggiunge
`EvidenceCitation.source_kind: ProvenanceKind = ProvenanceKind.STUDY` (il
default `STUDY` garantisce retrocompatibilità con le citazioni bibliografiche
esistenti). Una citazione con `source_kind=ATHLETE_DATA` non porta `doi`/`pmid`
e ha `verified=False`; non viola ADR-0003 (che restringe le citazioni *bibliografiche*
a Evidenze verificate), ma ne è un'**estensione** per un tipo di fonte
diverso. La funzione `freeze_athlete_data_citation` (in `athlete_metrics.py`)
costruisce tali citazioni in modo type-safe.

## Consequences

- L'euristica è sempre **etichettata**: nessuna Prescrizione o Blocco può
  presentarsi come fondato su studi se non lo è. Il test
  `test_coach_invariants.py` verifica che `provenance==HEURISTIC` non
  produca mai `supported=True`.
- I conflitti di evidenza (`block.conflicts: List[str]`) elencano i record
  con `direction in {negative, mixed}` — conflict-aware conservato (ADR-0005
  e `CONTEXT.md`): la provenienza non riconcilia i conflitti, li espone.
- `models.DataSource` resta invariato: i client bibliografici e il corpus
  delle Evidenze non subiscono modifiche.
- Il valore `source_kind` è persistito nel blob JSON di `EvidenceCitation`
  dentro `PaperRecord`; le citazioni esistenti (senza il campo) si
  deserializzano con il default `STUDY` — retrocompat totale.
