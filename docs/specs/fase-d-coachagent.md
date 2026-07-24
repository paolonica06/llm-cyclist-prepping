# PRD — Fase D: CoachAgent + feedback loop

> Spec sintetizzata dal grilling di design (sessione 2026-07-24). Fonte di verità
> per l'implementazione. Usa il glossario in `CONTEXT.md` e rispetta gli ADR
> `0001..0005`. Consumatori a valle: `writing-plans` → `executing-plans` (TDD).
> Vocabolario: **Piano, Blocco, Microciclo, Seduta, Intervallo, Prescrizione,
> Compliance, Evidenza verificata, Citazione, Trasferibilità personalizzata,
> Confounder, Retriever, Pozzo, Conflict-aware** (definiti in `CONTEXT.md`).

## Problem Statement

Oggi il sistema sa costruire un **corpus di Evidenza verificata** (Fase A), sa
**modellare l'atleta nel tempo** (Fase B: misure, gare, valutazioni, piano
versionato, memoria di trasferibilità) e sa **interrogare il Pozzo** in modo
personalizzato e conflict-aware (Fase C: Retriever). Ma **manca il pezzo che
chiude il cerchio**: non c'è nulla che, dato lo stato dell'atleta e l'evidenza,
**costruisca e mantenga un Piano di allenamento** come farebbe un preparatore
vero — cioè periodizzando verso un obiettivo, adattandolo quando le variabili
cambiano, e **imparando** dai risultati dell'atleta.

Dal punto di vista dell'atleta (Paolo, U23 strada, FTP 329 / 4.46 W·kg⁻¹):
«Ho un obiettivo (portare l'FTP a 340), ho i miei dati storici e una base di
studi. Voglio che il sistema mi proponga un piano *motivato* — che mi dica *perché*
ogni scelta, distinguendo ciò che poggia sugli studi, ciò che poggia sui *miei*
dati, e ciò che è solo giudizio — che si **aggiorni** quando sto male o non
rispetto il carico, e che **impari** cosa funziona *per me*, senza mai spacciare
un'ipotesi per certezza né sconfinare nel medico.»

## Solution

Un **CoachAgent** che genera e mantiene un **Piano vivo** verso un **obiettivo
metrico datato**, con ogni decisione a **provenienza tracciata a tre fonti**, un
**doppio feedback loop** (adattamento veloce + apprendimento lento con gate di
compliance), consegna in modalità **proponi-poi-approva**, guardrail di sicurezza
e confine medico netti, e degradazione **offline** a pianificatore euristico.

Principio guida (contratto di citazione **A**): **l'Evidenza vincola la
strategia; i numeri li deriva lo stato dell'atleta.** Nessuno studio giustifica i
watt esatti di Paolo — quindi l'evidenza vincola le *scelte strategiche*
(distribuzione dell'intensità, stimolo del Blocco, presenza/struttura del taper) e
ognuna porta le sue Citazioni; i *numeri concreti* (target al watt, collocazione
nel Microciclo) derivano dallo stato dell'atleta con euristiche **etichettate**.

Modello a **tre fonti di provenienza**, dichiarato per *ogni* decisione (estende
il binario `Prescrizione.supportata` e riecheggia `ExtractedField.source`):

- **`studi`** — Evidenza verificata di popolazione (dal Retriever, Fase C). Cita studi.
- **`dati_atleta`** — Evidenza **N=1** dai dati longitudinali dell'atleta (Fase B:
  valutazioni, blocchi congelati, `TransferabilityMemo`). Fonte di **prima classe**,
  citata *come tale*, distinta dagli studi.
- **`euristica`** — inferenza del coach quando né studi né dati-atleta fissano la
  scelta. **Non è evidenza**: sempre etichettata, mai travestita da studio.

## User Stories

1. Come atleta, voglio dichiarare un **obiettivo metrico datato** (es. FTP 329→340 entro 8 settimane), così che il Piano abbia una struttura e un metro di successo.
2. Come atleta, voglio che il CoachAgent **periodizzi a ritroso** dalla data-obiettivo in Blocchi con scopo fisiologico unico, così da avere una progressione sensata verso il picco.
3. Come atleta, voglio che ogni scelta **strategica** del Piano (stimolo del Blocco, distribuzione dell'intensità, taper sì/no) porti le **Citazioni** all'Evidenza verificata che la sostiene, così da sapere *perché*.
4. Come atleta, voglio che i **numeri** (target al watt, durata degli Intervalli, collocazione nel Microciclo) siano derivati dalle mie zone/stato e **etichettati "euristica"**, così da non confondere il giudizio del coach con l'evidenza.
5. Come atleta, voglio che quando i **miei dati storici** informano una scelta (es. «l'ultima volta hai risposto bene a un Blocco VO₂max»), quella scelta sia marcata **`dati_atleta`** e citi le mie Valutazioni/Blocchi, così da riconoscere l'evidenza N=1.
6. Come atleta, voglio che quando l'evidenza è **in conflitto**, il Piano scelga la direzione a **maggiore confidenza/trasferibilità** *ma mi mostri il conflitto* con i link agli studi discordi, così da non subire cherry-picking.
7. Come atleta, voglio che il Piano si **aggiorni settimanalmente** (loop veloce) quando il mio stato devia (TSB molto negativo, sonno/HRV crollati, compliance bassa), riducendo/spostando il carico del Microciclo entrante.
8. Come atleta, voglio che a **fine Blocco** (loop lento) il sistema misuri se la strategia ha funzionato *per me* (delta della Valutazione) e **aggiorni la mia evidenza N=1** e la `TransferabilityMemo`.
9. Come atleta, voglio che il loop lento **non impari** da un Blocco che **non ho rispettato** (compliance < soglia): l'esito è marcato «non attribuibile» (verdetto `inconclusive` con Confounder), così da non avvelenare la mia evidenza N=1 con rumore di aderenza.
10. Come atleta, voglio che il CoachAgent generi il Piano in stato **PROPOSED** e lo attivi **solo dopo mia accettazione esplicita**, così che «ipotesi non prescrizioni» sia strutturale e non uno slogan.
11. Come atleta, voglio poter **accettare** un Piano proposto con un comando (`research coach-accept`), che lo rende `ACTIVE` facendo `supersede` del precedente in modo atomico.
12. Come atleta, voglio poter **rifiutare/ignorare** un Piano proposto senza che tocchi il mio Piano attivo.
13. Come atleta, voglio che il coach abbia un **freno di sicurezza**: se lo stato mostra sovraccarico non-funzionale (TSB molto negativo protratto, HRV/sonno crollati, calo prestazione), **declassa il carico e segnala**, invece di spingere.
14. Come atleta, voglio un **confine medico netto**: se emergono segnali che sconfinano nel medico (dolore, sintomi, sospetto RED-S/malattia), il coach **non diagnostica né prescrive**, mette un disclaimer e mi rimanda a un professionista.
15. Come atleta, voglio che ogni Piano porti un **disclaimer strutturale** (ipotesi, non prescrizione medica), sempre, non solo nei casi limite.
16. Come atleta, voglio che il Piano proposto sia **leggibile**: per ogni Blocco lo scopo, le Prescrizioni con la loro provenienza, le Citazioni, e le note di conflitto/confounder.
17. Come operatore, voglio invocare la generazione con `research coach <athlete_id>`, così da produrre un Piano proposto on-demand.
18. Come operatore, voglio invocare l'adattamento veloce con un comando dedicato (loop veloce), così da ottenere la revisione del Microciclo entrante come nuova proposta.
19. Come operatore, voglio che l'attribuzione di fine Blocco (loop lento) sia innescabile quando la Valutazione del Blocco è disponibile, producendo la `TransferabilityMemo`.
20. Come operatore, voglio che senza `ANTHROPIC_API_KEY`/con `KB_FORCE_OFFLINE=1` il CoachAgent **degradi a un pianificatore euristico** (periodizzazione a regole) invece di fallire, coerente con gli altri agenti.
21. Come operatore, voglio che il CoachAgent **riusi** i modelli di Fase B (`TrainingPlan`, `TrainingBlock`, `Prescription`, `EvidenceCitation`, `Assessment`, `TransferabilityMemo`, `ActivitySummary`) e di Fase C (`retrieve`), senza duplicare logica.
22. Come sviluppatore, voglio che l'obiettivo metrico sia rappresentato nel modello del Piano (oggi il Piano assume una **gara-A**; l'obiettivo può essere un **target metrico** senza gara), così da non forzare una gara inesistente.
23. Come sviluppatore, voglio che la provenienza a tre fonti sostituisca/estenda il binario `Prescription.supported`, così da distinguere `studi`/`dati_atleta`/`euristica`.
24. Come sviluppatore, voglio che la Citazione possa puntare **anche** a evidenza N=1 (Valutazioni/Blocchi dell'atleta), non solo a un record del Pozzo.
25. Come sviluppatore, voglio che la compliance di Blocco sia una **funzione pura** (eseguito vs pianificato) testabile offline, riusando le `ActivitySummary`.
26. Come sviluppatore, voglio che il gate di attribuzione (compliance→verdetto) sia una funzione pura, così che il loop lento sia deterministico e testabile.
27. Come atleta, voglio che quando il coach sceglie un numero dentro un **range** riportato da uno studio (es. taper 8–14 giorni), la scelta del punto sia marcata `dati_atleta` (se i miei dati la giustificano) o `euristica` (se no) — **mai** `studi`.
28. Come atleta, voglio che il Piano espliciti quando una raccomandazione è **contesa**, elencando gli studi a favore *e* contro.
29. Come operatore, voglio che le pagine/artefatti del Piano restino coerenti con l'invariante di sintesi «conflitti conservati, non riconciliati».
30. Come atleta, voglio che i Blocchi passati **congelati** non cambino quando il Piano viene riscritto (integrità temporale, ADR-0002), così che i giudizi sul passato restino stabili.

## Implementation Decisions

**Nuovo modulo / seam.** Un `CoachAgent` con il pattern trasversale degli agenti
(`run(...)` + percorso LLM/euristico, degrada mai-eccezione). Espone (nomi
indicativi, non vincolanti): generazione Piano proposto, adattamento veloce,
attribuzione di Blocco. CLI e API restano thin wrapper su `Pipeline` (nuovi
metodi `Pipeline.coach*`). La logica vive nell'agente.

**Obiettivo del Piano = target metrico datato.** Estendere `TrainingPlan` con un
obiettivo metrico (grandezza, valore-target, data-target) accanto all'esistente
`target_race_id`. L'obiettivo primario (da grilling) è il **target metrico**; la
gara-A resta opzionale. La periodizzazione va **a ritroso** dalla data-obiettivo.

**Stato PROPOSED (proponi-poi-approva).** Estendere `PlanStatus` con
`PROPOSED`. Il CoachAgent crea sempre Piani `PROPOSED`. L'attivazione
(`coach-accept`) fa la transizione atomica a `ACTIVE` con `supersede` del piano
attivo precedente (riusa `Database.supersede_plan`, che oggi assume input
`ACTIVE`: adeguare per accettare la promozione da `PROPOSED`). Un Piano `PROPOSED`
**non** è mai attivo e non fa supersede finché non accettato.

**Provenienza a tre fonti.** Introdurre un tipo di provenienza
`{studi | dati_atleta | euristica}` (enum, sul modello di `DataSource`) e
applicarlo a: (a) ogni **scelta strategica** del Blocco (stimolo, distribuzione,
taper…) e (b) ogni **Prescrizione**. La `Prescription.supported: bool` esistente
diventa/si affianca a un campo `provenance`; `supported=True` ≈ `provenance=studi`.
Regola del range (User Story 27): scegliere un punto dentro un range di uno studio
è `dati_atleta` o `euristica`, **mai** `studi`.

**Citazione N=1.** Estendere `EvidenceCitation` con un discriminante di sorgente
(`source_kind`: `study | athlete_data`) e permettere riferimenti a evidenza N=1
(id di `Assessment`/`TrainingBlock`/`TransferabilityMemo`), oltre al record del
Pozzo. Resta congelata (ADR-0003: solo Evidenza verificata è citabile *come
studio*; l'evidenza N=1 è una sorgente distinta e dichiarata).

**Integrazione Retriever (Fase C).** Per ogni scelta strategica il CoachAgent
formula un'interrogazione al `retrieve(db, query, athlete=...)` e usa l'output
**conflict-aware**: sceglie la direzione a maggiore confidenza/trasferibilità per
la decisione **ma** conserva anche gli studi della direzione opposta come
Citazioni «contese», così il Piano espone il conflitto (invariante «conflitti
conservati»).

**Doppio loop.**
- **Loop veloce (Microciclo).** Legge lo stato corrente (TSB, sonno/HRV, compliance
  parziale) e propone una **revisione del carico** del Microciclo entrante. Non
  apprende, non tocca la strategia, non aggiorna evidenza N=1. Esce come nuova
  proposta (coerente con proponi-poi-approva).
- **Loop lento (Blocco).** A Blocco eseguito + Valutazione disponibile: calcola il
  **delta** della Valutazione (es. ΔFTP) e, **passato il gate di compliance**,
  produce una `TransferabilityMemo` (verdetto `transferred | not_transferred |
  inconclusive`, con `metric_deltas` e `caveats`). La memo diventa **evidenza N=1**
  per i Piani successivi. È qui che «il coach impara Paolo».

**Gate di attribuzione (compliance).** Funzione pura: `compliance_blocco =
TSS eseguito / TSS pianificato` (da `ActivitySummary` vs `Prescription`). Se
`< 0.80` (default, configurabile per atleta) → verdetto `inconclusive` con
Confounder esplicito («compliance < soglia»), e il loop lento **non impara sulla
strategia** (semmai segnala un problema di fattibilità/carico). Sopra soglia →
verdetto attribuibile.

**Segnale di esito (loop lento).** Combinazione con priorità: (i) **Valutazione**
mirata all'obiettivo (`assessments`/delta-FTP) come segnale **primario**; (ii)
power-curve/PR e gara come **corroboranti**; il subjective (wellness/RPE) **non**
chiude il loop da solo.

**Guardrail di sicurezza + confine medico.** Funzione pura di controllo sullo
stato: sovraccarico non-funzionale (TSB molto negativo protratto, HRV/sonno
crollati, calo prestazione) → il coach **declassa il carico e segnala**, non
spinge. Segnali medici (dolore, sintomi, sospetto RED-S/malattia) → **niente
diagnosi/prescrizione**, disclaimer strutturale e rimando a professionista. Ogni
Piano porta **sempre** un disclaimer «ipotesi, non prescrizione medica».

**Degradazione offline.** Senza LLM il CoachAgent produce un Piano con un
**pianificatore euristico** (periodizzazione a regole dallo stato atleta + output
deterministico del Retriever), con provenienza `euristica`/`studi` dove applicabile
e narrativa citata ridotta. Mai un'eccezione che blocca la pipeline.

**Persistenza.** Riusa la tabella `plans` (versioning append-only) e
`transferability_memos`. Nessuna nuova tabella prevista (da confermare in
`writing-plans`); eventuali estensioni sono campi nei blob JSON esistenti.

## Testing Decisions

**Cosa rende buono un test:** verifica **comportamento esterno**, non dettagli
implementativi; **offline e deterministico** (`KB_FORCE_OFFLINE=1`, come tutta la
suite via `tests/conftest.py`); LLM stubbato con un `LLMClient` fresco per-modulo
(niente pollution del singleton `get_llm()`), come in `tests/test_llm_batching.py`
e `tests/test_reassess.py`.

**Seam (il più alto possibile, preferendo quelli esistenti):**
- **`CoachAgent.run(...)`** (generazione Piano proposto) — analogo a
  `ScreeningAgent.run`/`ExtractionAgent.run`. Test: dato un atleta seminato
  (misure, valutazioni, eventualmente gara) + un Pozzo verificato seminato,
  produce un `TrainingPlan` `PROPOSED` con Blocchi periodizzati a ritroso, ogni
  decisione con `provenance` valorizzata, Citazioni presenti per le scelte `studi`,
  disclaimer sempre presente. Ramo euristico (offline) e ramo LLM (stubbato).
- **Funzioni pure di attribuzione** (`compliance` di Blocco, gate compliance→verdetto,
  delta della Valutazione) — analoghe alle funzioni pure di `athlete_metrics`
  (prior art: `tests/test_athlete_metrics.py`). Test tabellari: sopra/sotto soglia,
  esito attribuibile vs `inconclusive` con Confounder.
- **Loop lento** (`attribuzione di Blocco → TransferabilityMemo`) — dato un Blocco
  eseguito + `ActivitySummary` (per compliance) + `Assessment` (per delta), verifica
  il verdetto e i `metric_deltas`. Prior art: `tests/test_athlete_invariants.py`,
  `tests/test_athlete_persistence.py`.
- **Invarianti chiave** (prior art `tests/test_athlete_invariants.py`):
  (1) il Piano generato è `PROPOSED` e **non** attivo finché non accettato;
  (2) `coach-accept` fa `supersede` atomico (nessun doppio attivo);
  (3) compliance < soglia ⇒ verdetto `inconclusive` (non si impara sulla strategia);
  (4) i Blocchi congelati non cambiano dopo riscrittura del Piano (ADR-0002);
  (5) le scelte `dati_atleta`/`euristica` **non** portano Citazioni di studio come se
  fossero `studi`; (6) conflitto ⇒ il Piano espone entrambe le direzioni.
- **CLI** (`research coach`, `research coach-accept`) — prior art
  `tests/test_cli_retrieve.py`, `tests/test_cli_athlete_sync.py`.

## Out of Scope

- **Generazione in linguaggio naturale ricca** della "spiegazione da coach" oltre la
  narrativa citata di base (è a valle; eventualmente Fase E conversazionale).
- **Rispecchiamento sulla piattaforma esterna** (push del Piano su intervals.icu per
  l'esecuzione): il glossario lo prevede a regime, ma non in questa Fase D.
- **Wiring live della curva di potenza** (già backlog Fase B) — usata se disponibile,
  non è compito di Fase D popolarla.
- **Ottimizzazione multi-obiettivo** (più target simultanei) — un obiettivo metrico
  primario per Piano; la gara-A resta opzionale/corroborante.
- **Auto-accettazione o auto-attivazione** dei Piani: esplicitamente esclusa
  dall'invariante proponi-poi-approva.
- **Tier LLM/embedding-rerank del Retriever** (backlog Fase C): il CoachAgent usa il
  Retriever così com'è.

## Further Notes

- **Tensione col glossario:** il Piano è definito come periodizzazione «verso una
  gara-A»; l'obiettivo primario di Fase D è un **target metrico**. Aggiornare
  `CONTEXT.md` (voce «Piano»/«Obiettivo») e valutare un **ADR-0006** su
  «Obiettivo del Piano: target metrico datato, gara-A opzionale».
- **Provenienza a tre fonti:** merita un **ADR** dedicato (estende il binario
  `Prescrizione.supportata`; è il cuore dell'onestà epistemica del coach). La
  regola-chiave: personalizzare un numero dentro un range di popolazione è
  `dati_atleta`/`euristica`, **mai** `studi` — evita di «lavare» inferenze dell'LLM
  attraverso una Citazione (stesso fallimento visto in estrazione: valori inferiti
  dal solo titolo).
- **Attrito UX del loop veloce:** con proponi-poi-approva stretto, ogni aggiustamento
  settimanale richiede accettazione. Valutare (in `writing-plans`) una tolleranza di
  auto-aggiustamento del solo *carico* entro limiti, mantenendo l'approvazione per i
  cambi di *strategia*. Da decidere: qui resta PROPOSED per coerenza con l'invariante.
- **Compliance come Confounder:** il glossario elenca già «Blocco accorciato» fra i
  Confounder e `TransferabilityVerdict.INCONCLUSIVE` esiste già — il gate di
  compliance vi mappa naturalmente.
- **Percorso implementativo suggerito:** `writing-plans` (piano con checkpoint) →
  `executing-plans`/TDD, in **sessione nuova** (seed: questo PRD + glossario + ADR).
  La generazione multi-decisione (una query Retriever per scelta strategica) è un
  buon candidato per parallelizzazione in fase di implementazione.
