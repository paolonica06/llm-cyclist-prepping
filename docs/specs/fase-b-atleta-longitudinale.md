# PRD — Fase B: Modello dati atleta longitudinale

> **Stato:** bozza pronta per `domain-modeling` · **Data:** 2026-07-24 · **Fase:** B
> **Sequenza skill:** `grill-me` (fatto) → **`to-spec` (questo doc)** → `domain-modeling` → `writing-plans` → `executing-plans`
> **Riferimenti:** `docs/ROADMAP.md` (Fase B), `docs/AGENT_WORKFLOW.md` §4 (gate)

---

## Confine della fase (leggere prima di tutto)

Fase B costruisce il **contenitore**, non l'**intelligenza** che lo riempie:

- **In Fase B:** schema + persistenza delle entità longitudinali, ingestione da intervals.icu (morning sync), metriche derivate *di nostra competenza*, API di lettura/scrittura, test.
- **NON in Fase B:** la *generazione* del piano periodizzato (il CoachAgent che decide la periodizzazione → **Fase D**) e il *retrieval/RAG* che seleziona e pesa i paper (**Fase C**).

Perché allora modelliamo già piano/evidenza/memoria in Fase B? Perché le loro decisioni **strutturali** — versioning, congelamento dei blocchi eseguiti, citazioni-snapshot, gate di citabilità — sono decisioni di *modello dati*: sbagliarle ora renderebbe la futura memoria "cosa ha funzionato per me" **inaffidabile a posteriori**. Il contenitore va progettato bene adesso; l'agente che lo riempie arriva dopo.

---

## Problema (Problem Statement)

Oggi l'atleta è un **input effimero**. `AthleteProfile` (14 campi) viene caricato da YAML a runtime, usato una volta per generare una pagina di confronto studi↔profilo, e poi dimenticato: nessuna persistenza, nessun `athlete_id`, nessun timestamp, nessuna storia. Lo schema SQLite conosce solo `researches` e `records` bibliografici.

Conseguenze, dal punto di vista dell'atleta (un singolo ciclista competitivo):

- Non posso **accumulare** la mia storia (FTP, VO₂max, carico, wellness) nel tempo: ogni analisi riparte da uno snapshot statico.
- Il confronto con la letteratura mi paragona a *com'è oggi il profilo*, non a **com'ero quando** avevo quei numeri.
- Non c'è alcun **anello di ritorno**: le ipotesi di allenamento generate non vengono mai confrontate con la mia risposta reale, quindi il sistema non impara mai cosa funziona *per me*.
- Le due metà del sistema — la pipeline di evidenze (paper) e l'atleta — sono **scollegate nel tempo**.

L'obiettivo di fondo (nord, realizzato in Fase C/D) è un **coach basato su evidenze** che costruisce una periodizzazione completa verso gara, prescritta **al watt**, giustificata dalla letteratura **verificata**, e che **misura l'esito**. Nulla di tutto ciò è possibile finché l'atleta non ha un modello dati longitudinale.

---

## Soluzione (Solution)

Un **modello dati atleta longitudinale** persistito nel DB SQLite esistente, che:

1. **Rispecchia** i dati di allenamento da **intervals.icu** — un solo connettore, con **sync mattutino** readiness-driven. Le metriche derivate (CTL/ATL/TSB, curva di potenza) sono **ingerite già calcolate** (non ricalcolate da noi): *ramo mirror*.
2. Modella **gare** (con priorità **A/B/C** e date) come ancore della periodizzazione, e **test programmati** (FTP/ramp/VO₂max) come **punti di misura primari** del progresso.
3. Modella il **piano** periodizzato (macro→meso→micro→seduta→**intervallo al watt**) come **fonte di verità nel nostro DB** *e* lo **spinge su intervals.icu** per l'esecuzione (*ramo 3*). Il piano è **versionato/append-only**; i **blocchi eseguiti sono congelati**; **pianificato** e **eseguito** sono distinti.
4. Lega ogni **blocco** ai **paper verificati** che lo giustificano (grana **per meso-ciclo**), con **citazione congelata** (snapshot) + **puntatore soft** al record KB corrente. Le prescrizioni senza studio 1:1 sono marcate **"non supportate"**.
5. Persiste una **memoria di trasferibilità personalizzata**: blocco-eseguito → delta dei test → verdetto ("per *me* ha/non ha trasferito"), **con confidenza e caveat** sui confounder.

Fase B consegna questo contenitore + l'ingestione + le metriche derivate di sua competenza + i test. Fase C/D lo interrogano.

---

## User Stories

**Identità e profilo**
1. Come atleta, voglio un'**identità persistente** nel sistema, così che i miei dati storici si accumulino invece di ripartire da zero a ogni sessione.
2. Come atleta, voglio che il profilo distingua ciò che è **stabile** (disciplina, categoria, obiettivi, storia) da ciò che **varia nel tempo** (FTP, VO₂max, carico), così che non esistano due verità in conflitto sullo stesso numero.
3. Come atleta, voglio che le metriche variabili non abbiano un valore "autoritativo" bloccato nel profilo, ma siano **derivate dall'ultima misura**, così da non dover aggiornare a mano il profilo a ogni cambiamento.

**Ingestione (intervals.icu, morning sync)**
4. Come atleta, voglio collegare **un solo servizio** (intervals.icu) e che il sistema ne rispecchi i miei dati, così da non dover configurare Strava e Garmin separatamente (sono già a monte di intervals.icu).
5. Come atleta, voglio un **sync mattutino** che aggiorni sonno/HRV/peso/HR-riposo della notte, così che le decisioni di oggi si basino sul mio stato attuale.
6. Come atleta, voglio che il sync sia **idempotente**, così che rilanciarlo non duplichi attività o misure.
7. Come atleta, voglio che se intervals.icu è irraggiungibile il sistema **degradi senza crash** (nessun dato nuovo, ma nessuna eccezione che blocchi tutto), così da poter riprovare più tardi.
8. Come atleta, voglio che il sistema **non** ingerisca gli stream secondo-per-secondo, così che il DB resti leggero e veloce.

**Serie storiche**
9. Come atleta, voglio che **CTL/ATL/TSB** siano archiviate **così come le calcola intervals.icu**, così che i numeri coincidano con ciò che vedo sulla piattaforma.
10. Come atleta, voglio uno **storico dell'FTP/soglia** nel tempo, così che i dati passati siano interpretati con l'FTP che avevo *allora*, non con quello di oggi.
11. Come atleta, voglio la mia **curva di potenza** registrata come snapshot datati, così da vedere come cambiano i miei record a durate chiave (5s, 1', 5', 20', 60').
12. Come atleta, voglio le mie **attività come riassunti** (data, durata, TSS, IF, kJ, tipo), così da avere il log senza il peso dei dati grezzi.

**Gare**
13. Come atleta, voglio registrare le **gare con data e priorità A/B/C**, così che la periodizzazione si costruisca attorno agli obiettivi (tapering verso le gare-A).
14. Come atleta, voglio poter annotare il **risultato** di una gara come **contesto qualitativo**, sapendo che il progresso vero si misura sui *test*, non sul piazzamento (le gare non sono comparabili tra loro).

**Test programmati**
15. Come atleta, voglio pianificare **test** (FTP/ramp/VO₂max) a date fisse, così da avere **punti di misura oggettivi** del progresso.
16. Come atleta, voglio che i risultati dei test siano **collegati al blocco** che li precede, così da poter attribuire il miglioramento al lavoro svolto.
17. Come atleta, voglio distinguere la **data pianificata** dalla **data effettiva** di un test, così che gli slittamenti non falsino l'analisi.

**Piano**
18. Come atleta, voglio un piano **periodizzato** macro→meso→micro fino alla singola **seduta con intervalli al watt**, così che l'allenamento sia prescritto in modo concreto.
19. Come atleta, voglio che il piano sia la **fonte di verità** nel sistema e venga **spinto su intervals.icu** per l'esecuzione, così da eseguirlo sul dispositivo e leggere indietro l'aderenza.
20. Come atleta, voglio che **ri-pianificare crei una nuova versione** senza cancellare la precedente, così da non perdere la storia di cosa avevo previsto e perché.
21. Come atleta, voglio che i **blocchi già eseguiti siano congelati** (watt/date/evidenza immutabili), così che la memoria di cosa ho fatto sia affidabile.
22. Come atleta, voglio che il sistema distingua **pianificato vs eseguito** (l'eseguito ricavato dalla compliance con le attività reali), così che i giudizi si basino sulla realtà, non sulle intenzioni.
23. Come atleta, voglio che ogni prescrizione al watt sia marcata **"supportata" o "non supportata"** dalla letteratura, così da sapere cosa è evidence-based e cosa è mestiere del coach.

**Evidenza**
24. Come atleta, voglio che ogni **blocco dichiari i paper verificati** che lo giustificano, così che "rispetta la letteratura" sia verificabile e non uno slogan.
25. Come atleta, voglio che le citazioni di un blocco eseguito siano **congelate** (snapshot di titolo/DOI/verdetto/qualità/trasferibilità), così che restino valide anche se la KB cambia o una ricerca viene rilanciata.
26. Come atleta, voglio un **puntatore soft** dalla citazione congelata al record KB corrente, così da poter navigare alla versione aggiornata quando serve.
27. Come atleta, voglio che il sistema possa citare **solo** paper già verificati dalla pipeline (`METADATA_VERIFIED`/`SYNTHESIZED`, `verified=true`), così da non introdurre mai letteratura non controllata in un piano.

**Memoria / trasferibilità**
28. Come atleta, voglio che, a fine blocco, il sistema salvi se l'approccio ha **funzionato per me** (delta dei test rilevanti), così da imparare cosa mi si adatta.
29. Come atleta, voglio che quel verdetto porti una **confidenza e i confounder** (sonno, stress, malattia, durata ridotta), così da non rileggerlo tra un anno come una verità assoluta.
30. Come atleta, voglio che la memoria sia **ancorata agli snapshot congelati** (blocco + citazioni + FTP del tempo), così che non cambi retroattivamente se aggiorno il piano o l'FTP.

**Consumatori a valle (Fase C/D)**
31. Come **CoachAgent** (Fase D), voglio interrogare lo **stato longitudinale** dell'atleta (fitness corrente, curva di potenza, ultimi test, gare imminenti), così da generare un piano fondato su dati reali.
32. Come CoachAgent, voglio leggere la **memoria di trasferibilità personalizzata**, così da pesare l'evidenza in base a cosa ha già funzionato per *questo* atleta.
33. Come **motore RAG** (Fase C), voglio che i paper citabili siano solo quelli verificati, così che il grounding delle raccomandazioni resti affidabile.

**Operatività**
34. Come atleta, voglio che tutto stia nel **DB SQLite esistente** e segua le convenzioni del progetto (rigenerabile/versionabile), così da non introdurre nuova infrastruttura.
35. Come atleta, voglio che la **chiave API** intervals.icu sia configurata via variabile d'ambiente come le altre credenziali, così da non committarla mai.

---

## Criteri di accettazione (gate §4)

- **Persistenza:** ogni nuova entità fa round-trip Pydantic ↔ SQLite (scrittura → rilettura identica) con test verdi; query per stato/versione/atleta funzionano.
- **Ingestione:** `IntervalsClient` **degrada a vuoto offline** (nessuna eccezione); il morning-sync è **idempotente** (un secondo rilancio non crea duplicati) — dimostrato da test con client stubbato.
- **Gate di citabilità:** citare un record **non verificato** è rifiutato/escluso — test dedicato che lo prova.
- **Integrità temporale:** ri-pianificare crea una **nuova versione**; modificare il piano corrente **non altera** lo snapshot del blocco eseguito — test dedicato.
- **Metriche derivate:** compliance e delta-test sono **funzioni pure** testate in isolamento (offline).
- **Non-ricalcolo:** asserzione/test che CTL/ATL/TSB provengono **dall'ingestione**, non da un nostro calcolo.
- **Regressione:** `pytest` verde inclusi i nuovi test; **nessuna regressione** sui 34 test esistenti; pyflakes pulito.
- **Evidenza mostrata:** output di `pytest -q` riportato (principio `verification-before-completion`) prima di dichiarare la fase chiusa.

---

## Decisioni implementative

**Persistenza — estendere, non normalizzare.**
- Si estende il pattern esistente **"blob JSON + colonne indicizzate"** (Pydantic `model_dump_json()` in colonna `data`, colonne sparse indicizzate per le query frequenti).
- Nuove tabelle, ciascuna con metodi `Database` paralleli (`create_*/save_*/get_*/list_*`): **athletes**, **timeseries** (wellness + fitness + curva-potenza + storico-FTP, discriminati da `metric_type` + `date`), **races**, **tests** (risultati test programmati), **plans** (identità + versione + validità + albero di periodizzazione nel blob), **blocks** (meso-cicli — tabella separata, indicizzata per `plan_id`/`version`/stato, per interrogare i blocchi *eseguiti congelati*), **evidence_citations**, **transferability_memo**.
- **Nessun framework di migrazione:** `CREATE TABLE IF NOT EXISTS` append-only. Le **FK sono documentazione** (SQLite ha FK OFF di default) e si impongono a livello applicativo.

**Modelli Pydantic nuovi.**
- `Athlete` (evolve `AthleteProfile`), `WellnessPoint`, `FitnessPoint` (CTL/ATL/TSB), `ActivitySummary`, `PowerCurvePoint`, `FtpHistoryPoint` (o un `TimeseriesPoint` generico con `metric_type`), `Race` (con priorità A/B/C), `Test`/`TestResult`, `TrainingPlan`, `TrainingBlock` (+ `Prescription`/`Interval` con target-watt e flag `supported`), `EvidenceCitation` (snapshot + soft ref), `TransferabilityMemo` (con `confidence`/`caveats`). Si riusano gli enum esistenti (`QualityLevel`, `DataSource`) dove sensato.

**Riuso di `AthleteProfile`.**
- Mantenuto per **identità + contesto qualitativo** (name, sex, discipline, category, level, goals, history, constraints, notes). I campi **variabili** (`ftp_w`, `ftp_w_kg`, `vo2max`, `weekly_hours`, `weekly_tss`) **cessano di essere autoritativi**: la verità diventa la serie storica; un eventuale "snapshot corrente" è una **vista derivata** dall'ultima misura/test. (Non si rompe il modello esistente; si documenta che quei campi sono legacy/derivati.)

**Ingestione — seam separato dalla pipeline paper.**
- `IntervalsClient` (nuovo, nel layer `clients/`) **riusa solo `HttpFetcher`** (retry/backoff, header User-Agent+mailto) e il pattern `Settings` per il segreto (`KB_INTERVALS_ICU_API_KEY`), con **degradazione a vuoto/None su errore** come gli altri client.
- **Contratto diverso dai client bibliografici:** i metodi async ritornano i **modelli-atleta** (wellness/fitness/attività/curva-potenza/FTP), **non** `PaperRecord`. I dati intervals.icu **non attraversano** `create→search→screen→…→synthesize`.
- **Entry point morning-sync** separato: nuovo comando CLI (es. `research athlete-sync <athlete_id>`) + metodo dedicato (su `Pipeline` o agente standalone), **idempotente** (upsert per `(athlete_id, date)` / id attività).

**Gate di citabilità (invariante duro).**
- Una guard riusa il concetto del Verification gate esistente: accetta solo record con `verification.verified == True` e stato in `{METADATA_VERIFIED, SYNTHESIZED}`. Tutto il resto non è citabile in un piano.

**Congelamento e versioning.**
- Le versioni del piano hanno **validità temporale** (append-only). Alla transizione **"blocco → eseguito"** si materializza uno **snapshot immutabile** del blocco (prescrizioni + citazioni + FTP del tempo). Nessuna mutazione in-place di ciò che è congelato.

**Snapshot della citazione + identità paper.**
- `EvidenceCitation` **fotografa** titolo, DOI/PMID, verdetto di verifica, qualità metodologica e trasferibilità del paper, **più** un `record_id` soft (puntatore best-effort). *Nota:* `make_record_id` include `research_id`, quindi lo stesso paper in ricerche diverse ha id diversi; **poiché la citazione è congelata**, la sua validità **non dipende** dalla stabilità dell'id (fotografa DOI/PMID/titolo). Per questo **non si introduce (ora)** una tabella di "paper canonici": il congelamento risolve la fragilità (esito della decisione Q8, ramo 3).

**Metriche derivate (di nostra competenza).**
- Funzioni **pure** in un modulo dedicato: `compliance(planned, actual)`, `test_delta(series)`, `derive_executed_block(planned_block, activities)`. Testabili in isolamento. **CTL/ATL/TSB non sono nostre** (ingerite).

**Config.**
- Aggiungere `intervals_icu_api_key: Optional[str] = None` a `Settings` (env `KB_INTERVALS_ICU_API_KEY`), documentata nel docstring accanto alle altre credenziali.

---

## Decisioni di test

**Cosa rende buono un test qui:** verifica il **comportamento esterno** — lo stato del DB dopo un'operazione, l'output di una funzione pura, il rifiuto di un input non valido — **non** i dettagli implementativi. Deterministico e **offline** (`KB_FORCE_OFFLINE=1` già impostato globalmente in `conftest.py`). Nessun accesso di rete reale.

**Seam (confermati con l'utente):** il **più alto possibile** — `agent.run()` / `Database` / **funzioni pure**. **Nessun** seam a livello `Pipeline` (non esiste `test_pipeline.py`) né client-only.

**Moduli testati e prior art:**
- **Ingestione** → livello `agent.run()`, **stub dei metodi del client sull'istanza** (niente `respx`), poi asserzioni sullo stato del DB. *Prior art:* `test_verification.py` (agente async network-coupled, `_stub` che rimpiazza `client.method`). Casi: successo, rete-giù → degradazione a vuoto, **idempotenza** (secondo rilancio senza duplicati).
- **Entità/persistenza** → seed nel DB temporaneo + `list_*`/`get_*` + asserzioni su round-trip, query per stato/versione, aggregazione. *Prior art:* `test_synthesis_cumulative.py` (`_seed_research`, asserzioni su dedup/cumulatività).
- **Metriche derivate** → funzioni pure con input/output deterministici. *Prior art:* `test_dedup.py`, `test_textutil.py`.
- **Gate citabilità** e **congelamento/versioning** → test comportamentali dedicati (rifiuto di record non verificati; immutabilità dello snapshot dopo ri-pianificazione).

**Setup DB nei test:** `Database(path=tmp_path/"kb.sqlite3")` per test (fixture `tmp_path`), helper locali (`_db`, `_seed_*`, `_stub_*`, `_run`) come nel resto della suite — **niente** fixture globali oltre alle env di `conftest.py`.

---

## Fuori scope

- La **generazione intelligente** del piano (il CoachAgent che decide la periodizzazione) → **Fase D**.
- Il **retrieval/RAG** che seleziona e pesa i paper → **Fase C**.
- Connettori **Strava/Garmin diretti** (sono sorgenti *a monte* di intervals.icu).
- **In-ride live** / telemetria in tempo reale durante l'uscita.
- **Stream** secondo-per-secondo / dati grezzi `.fit` (rivalutabili se emergerà un dato reperibile *solo* lì).
- **Multi-atleta / roster** (il modello è **mono-atleta**).
- **Ricalcolo** proprio di CTL/ATL/TSB (ingerite da intervals.icu).
- **Time-series DB** dedicato (resta SQLite).
- **Interfaccia / visualizzazioni** (grafici, timeline) → **Fase E**.

---

## Note aggiuntive

**Deviazione consapevole dal ROADMAP.** La voce Fase B *"Ingestione da `.fit`/CSV / API (intervals.icu, Strava, Garmin)"* è **ristretta a solo intervals.icu**: essendo l'hub che già aggrega Strava/Garmin (e gli upload `.fit`), un connettore separato darebbe gli **stessi dati due volte** + un problema di dedup evitabile. Il ROADMAP va aggiornato di conseguenza.

**Invarianti trasversali (da promuovere ad ADR in `domain-modeling`):**
- **I1** — Citabilità solo su evidenza **verificata**.
- **I2** — Ogni giudizio sul passato è **ancorato a snapshot congelati**.
- **I3** — Funzione obiettivo **temporale** (CTL cresce in build; TSB alta solo in taper/gara), **non** massimizzazione simultanea. *(Vincolo di Fase D; qui rilevante perché il modello deve saper rappresentare fasi + segnali nel tempo.)*
- **I4/I5** — Un solo connettore (intervals.icu), **ramo mirror**: metriche derivate ingerite, **mai** ricalcolate.

**Open items da risolvere in `domain-modeling` / durante l'implementazione:**
- Campi esatti degli endpoint intervals.icu (wellness / activities / power-curve) e gestione auth.
- **Politica dati mancanti** nella readiness mattutina (niente HRV oggi → fallback? ultima nota? skip?).
- **Catalogo protocolli** dei test fisiologici (FTP20, ramp/MAP, VO₂max lab…) e relative unità.
- **Collisione terminologica "test"**: test-software (pytest) vs test-fisiologico (entità di dominio) → voce di glossario in `CONTEXT.md`.
- Definizioni adottate da intervals.icu (time-constant CTL≈42g / ATL≈7g, zone) da citare come riferimento nel glossario.
- **Soglia di compliance**: quale % di aderenza pianificato-vs-eseguito conta come "eseguito" vs "saltato".

**Prossimo passo:** `domain-modeling` (glossario + ADR per I1–I5 e per le decisioni strutturali: ramo-mirror, ramo-3 piano, congelamento, gate citabilità), poi `writing-plans`.
