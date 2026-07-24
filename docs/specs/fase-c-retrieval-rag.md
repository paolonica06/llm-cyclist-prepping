# PRD — Fase C: Retrieval/RAG sulla wiki

> **Stato:** bozza pronta per `domain-modeling` · **Data:** 2026-07-24 · **Fase:** C
> **Sequenza skill:** `grill-me` (fatto) → **`to-spec` (questo doc)** → `domain-modeling` → `writing-plans` → `executing-plans`
> **Riferimenti:** `docs/ROADMAP.md` (Fase C), `docs/AGENT_WORKFLOW.md` §4 (gate), PRD Fase B (`docs/specs/fase-b-atleta-longitudinale.md`)

---

## Confine della fase (leggere prima di tutto)

Fase C costruisce **il retriever** — la **R** di RAG — non l'intero RAG.

- **In Fase C:** dato un *quesito* + l'atleta, restituire l'**evidenza verificata rilevante, pesata e onesta**. Deterministico, offline, testabile.
- **NON in Fase C:** la **generazione** della risposta discorsiva citata (la "AG"). Quella la fa l'operatore nel loop (Claude Code interattivo), oppure Claude Code headless (backend già costruito), oppure il **CoachAgent (Fase D)**. Il retriever è il deliverable; la generazione è un layer sottile sopra.

Perché così: il vincolo offline-first del progetto (test senza rete né LLM) impone che il cuore sia **deterministico**. La generazione, che richiede un LLM, resta un layer opzionale/esterno.

---

## Problema (Problem Statement)

Il corpus esiste (18 temi, 360+ studi verificati) ma è **carta statica**: non lo si può *interrogare*. Dal punto di vista dell'atleta/coach:

- Quando serve **fondare una decisione** ("cosa dice l'evidenza su X, *per me*?"), non c'è modo di tirare fuori gli studi giusti, **pesati per qualità** e per **quanto si trasferiscono a me**, vedendo **entrambe le facce**.
- L'`AthleteContextAgent` di oggi prende *tutti* i paper sintetizzati di *una* singola ricerca e li confronta alla cieca: nessuna ricerca **cross-tema**, nessun peso di qualità/trasferibilità, nessuna gestione dei conflitti.
- Le domande vere di un coach **attraversano i temi** (nutrizione + intensità, carico + recupero): un archivio a scaffali separati non basta.

Senza un retriever, la Fase D (CoachAgent) non ha come **radicare** le raccomandazioni nell'evidenza.

---

## Soluzione (Solution)

Un **retriever deterministico** sul pozzo di evidenza verificata. Dato `(query, atleta)` restituisce i migliori studi verificati:

1. **in-tema-prima** — filtra/pesa per pertinenza lessicale al quesito (BM25/TF-IDF con espansione sinonimi), così uno studio fuori tema per quanto eccellente non emerge;
2. **poi per qualità** — `confidence_level` + `methodological_quality`;
3. **personalizzato** — spinge in alto `population_type = cycling` e `transferability_to_competitive_cyclists = high` (e penalizza untrained/altri sport) in base al profilo atleta;
4. **onesto (conflict-aware)** — rappresenta **entrambe le direzioni** dell'evidenza (la più forte a favore *e* la più forte contro/nulla), non solo i top-K per punteggio.

Il tutto **offline e deterministico**; un tier **LLM/embedding opzionale** (riordino semantico) si attiva solo se l'LLM è disponibile, con degradazione graziosa. La **generazione** della risposta citata avviene sopra (operatore / Claude Code / Fase D).

---

## User Stories

**Interrogazione**
1. Come coach (o Fase D), voglio dare al retriever un **quesito + l'atleta** e ricevere gli studi verificati più rilevanti, così da radicare una raccomandazione nell'evidenza.
2. Come coach, voglio che l'ingresso primario sia **guidato dallo stato/piano dell'atleta** (il bisogno genera la query), così che il retrieval nasca da *cosa sto per fare*, non da domande a caso.
3. Come atleta, voglio poter fare anche una **domanda libera** ("come miglioro la tenuta oltre le 4h?") come modalità secondaria.
4. Come coach, voglio che la ricerca lavori sul **pozzo unico** di tutti gli studi verificati (cross-tema), così che una domanda su "fueling in un blocco VO₂max" peschi da più temi insieme.

**Pertinenza (in-tema-prima)**
5. Come coach, voglio che gli studi **fuori tema siano esclusi/declassati**, così da ricevere risposte pertinenti e non solo studi che fanno colpo.
6. Come coach, voglio che la pertinenza usi i **sinonimi di dominio** (es. "HIIT" ≈ "interval training"), così che la query trovi anche formulazioni diverse.
7. Come coach, voglio che la pertinenza guardi **titolo, abstract e affermazioni** dello studio, così da non mancare match rilevanti.

**Qualità e personalizzazione**
8. Come coach, voglio che a parità di tema gli studi a **confidenza/qualità metodologica più alta** vengano prima, così da fidarmi di più dei primi risultati.
9. Come atleta (ciclista competitivo su strada), voglio che gli studi su **veri ciclisti allenati** e ad **alta trasferibilità** siano spinti in alto, e quelli su sedentari/altri sport in basso, così che ciò che vedo si applichi a me.
10. Come coach, voglio che i dati da **full text** siano leggermente preferiti a quelli da solo abstract, a parità di resto, per maggiore affidabilità.

**Onestà (conflict-aware)**
11. Come coach, voglio che l'output rappresenti **entrambe le facce** dell'evidenza (la più forte a favore e la più forte contro/nulla), così da non farmi ingannare da una selezione a senso unico.
12. Come atleta, voglio vedere quando l'evidenza è **contrastante** su un esito, così da sapere che una conclusione è incerta.
13. Come coach, voglio che i conflitti siano **conservati, non appianati** (coerente con come il corpus li preserva già).

**Invariante di affidabilità**
14. Come atleta, voglio che il retriever restituisca **solo evidenza verificata**, così che nessuna citazione non controllata entri in una raccomandazione.
15. Come sviluppatore, voglio che "solo verificato" sia un **invariante di codice**, non una buona intenzione.

**Output**
16. Come coach, voglio un numero **ragionevole di studi** (top-K), non centinaia, così da poterli usare per generare una risposta concisa.
17. Come layer di generazione (io / Claude Code / Fase D), voglio che ogni studio restituito porti **affermazione, punteggi di qualità/trasferibilità, direzione e citazione**, così da poter scrivere una risposta fondata e citata.
18. Come coach, voglio ricevere anche **perché** uno studio è stato incluso (segnali di ranking), così da capire l'ordine.

**Offline / determinismo**
19. Come sviluppatore, voglio che il retriever **base** sia deterministico e offline (nessuna rete/LLM), così che i test siano riproducibili (stessa query → stesso ordine).
20. Come sviluppatore, voglio un tier **opzionale** di riordino semantico (embedding/LLM) attivo **solo se l'LLM è disponibile**, con fallback al lessicale — come il pattern già usato in screening/qualità.

**Interfaccia / consumatori**
21. Come utente CLI, voglio `research retrieve "<query>" --athlete <id>`, così da interrogare il corpus dal terminale.
22. Come `AthleteContextAgent` (esistente) e **CoachAgent (Fase D)**, voglio chiamare il retriever come funzione, così da radicare i miei output.
23. Come sviluppatore, voglio che il retriever **non introduca nuova persistenza**: legge il pozzo dai record esistenti (`db.list_records`).

---

## Criteri di accettazione (gate §4)

- **Determinismo/offline:** stessa `(query, atleta, corpus)` → **stessa lista ordinata**, senza rete né LLM (test verdi con `KB_FORCE_OFFLINE=1`).
- **Solo-verificati:** nessun record non verificato compare mai nell'output — test dedicato che semina record non verificati e verifica l'esclusione.
- **In-tema-prima:** uno studio ad alta qualità ma fuori tema **non** supera uno pertinente — test dedicato.
- **Personalizzazione:** a parità di tema/qualità, `population=cycling`/`transferability=high` viene **prima** di untrained/altro sport — test dedicato.
- **Conflict-aware:** con evidenza mista su un esito, l'output include **sia** la direzione positiva **sia** quella negativa/nulla — test dedicato.
- **CLI:** `research retrieve` instrada al retriever e formatta l'output (test `CliRunner`).
- **Regressione:** `pytest` verde (tutti i test esistenti + nuovi); pyflakes pulito.

---

## Implementation Decisions

**Modulo e interfaccia.**
- Nuovo modulo `cyclist_kb/retrieval.py` di **funzioni pure/deterministiche**. Interfaccia concettuale: `retrieve(query, athlete, k) -> lista ordinata di risultati`, dove ogni risultato incapsula il `PaperRecord`, il punteggio, i segnali di ranking e la **direzione** dell'evidenza.
- Nessuna nuova persistenza: il pozzo è ottenuto dai record esistenti via `Database` (tutti i record **verificati** attraverso tutte le ricerche → dedup per identità di paper come già fa la sintesi cumulativa).

**Pozzo unico (cross-tema).**
- La ricerca lavora su **tutti** i `PaperRecord` verificati (stato `METADATA_VERIFIED`/`SYNTHESIZED` con `verification.verified`), non limitata a un topic. Le pagine-tema restano artefatti sfogliabili; la **fonte autoritativa** del retrieval è il DB.

**Ranking (composito, deterministico).**
1. **Pertinenza lessicale** come filtro/peso dominante ("in-tema-prima"): tokenizzazione via `textutil.tokens`, espansione query con `domain.SYNONYMS`, punteggio BM25 o TF-IDF su titolo+abstract+affermazioni. Sotto una soglia di pertinenza il record è escluso.
2. **Qualità:** `confidence_level` + `methodological_quality` (mappati a pesi ordinali).
3. **Personalizzazione:** bonus per `population_type = CYCLING` e `transferability_to_competitive_cyclists = HIGH`; malus per `UNTRAINED`/`ENDURANCE_OTHER`. Guidata dal profilo `Athlete` (Fase B).
4. **Fonte dato:** piccolo bonus `full_text` vs `abstract` (`Extraction.based_on`).

**Onestà (conflict-aware).**
- Riusa la classificazione di **direzione** già nel progetto (`agents/synthesis._direction`: `positive`/`null`/`negative`/`mixed`). La selezione dei top-K **garantisce la presenza di entrambe le direzioni** quando esistono (almeno il miglior "a favore" e il miglior "contro/nullo"), invece di prendere solo i top per punteggio.

**Invariante — solo verificato.**
- Un filtro-guard (riusa la filosofia del Verification gate) esclude qualunque record non verificato *prima* del ranking.

**Tier LLM opzionale (graceful degradation).**
- Base lessicale sempre attiva e testabile offline. Se `llm.get_llm().available`, un **riordino semantico opzionale** (embedding o rerank) può raffinare i top-N lessicali; se non disponibile o fallisce, si resta al lessicale — stesso pattern di screening/qualità. Configurabile (default: off/base).

**Interfaccia utente.**
- Comando CLI `research retrieve "<query>" --athlete <id>` (thin wrapper sul modulo). Eventuale endpoint API in seguito. Consumatori applicativi: `AthleteContextAgent` e il futuro `CoachAgent`.

**Ingresso guidato dall'atleta.**
- Il retriever riceve una **stringa** query + `athlete_id`. La costruzione *intelligente* della query dallo stato/piano dell'atleta è responsabilità del **chiamante (Fase D)**; Fase C fornisce l'interrogazione, non l'intelligenza che la formula.

---

## Testing Decisions

**Cosa rende buono un test qui:** verifica il **comportamento esterno** — l'**ordine** e la **composizione** della lista restituita a fronte di un corpus noto — non i dettagli implementativi. Deterministico e **offline** (`KB_FORCE_OFFLINE=1` già globale). Nessun accesso reale a rete/LLM.

**Seam (confermati con l'utente):**
- **Primario — funzioni pure del retriever:** semino `PaperRecord` verificati in un DB `tmp` con qualità/popolazione/direzione controllate, chiamo il ranking, **asserisco l'ordine e la presenza delle due facce**. *Prior art:* `test_synthesis_cumulative.py` (seed + query + asserzioni), `test_dedup.py` (funzioni pure).
- **Sottile — CLI:** `research retrieve` via `CliRunner` (instradamento + formattazione). *Prior art:* `tests/test_cli_athlete_sync.py`.
- **Tier LLM opzionale:** stubbato sull'istanza `llm` (come `test_llm_batching.py`), verificando che il fallback lessicale regga.
- **Nessun** seam a livello `Pipeline`.

**Casi chiave:** solo-verificati (esclusione dei non verificati); in-tema-prima (fuori-tema non supera in-tema); personalizzazione (cycling/high prima di untrained/other); conflict-aware (entrambe le direzioni presenti); determinismo (stessa query → stesso ordine).

---

## Out of Scope

- La **generazione** della risposta discorsiva citata (operatore / Claude Code headless / **Fase D**).
- **Embedding come default** (solo tier opzionale; il default è lessicale deterministico).
- Il **CoachAgent** che costruisce la query dallo stato/piano (**Fase D**).
- **Multi-atleta** (mono-atleta: profilo Fase B).
- **Re-ranking LLM come default** (solo opzionale, off di default).
- Endpoint API/GUI dedicati (eventuali; il deliverable è modulo + CLI).

---

## Further Notes

**Invarianti (da promuovere ad ADR in `domain-modeling`):**
- **Solo evidenza verificata** è recuperabile/citabile.
- **Conflitti conservati** (rappresentare entrambe le facce, mai appianare/cherry-pickare).
- **Base deterministica offline**; LLM/embedding solo come tier opzionale con degradazione graziosa.

**Open items da risolvere in `domain-modeling` / `writing-plans`:**
- Formula esatta di combinazione dei pesi (pertinenza vs qualità vs trasferibilità) e le soglie.
- Valore di **K** (default ~8-10) e come garantire le due facce dentro K.
- **BM25** (dipendenza `rank-bm25` pure-python) vs **TF-IDF fatto in casa** con `textutil.tokens` (nessuna dipendenza). Preferenza: minimizzare le dipendenze salvo guadagno chiaro.
- Come derivare la "query dallo stato atleta" quando arriverà la Fase D (contratto).
- Glossario (`CONTEXT.md`): *retriever, pozzo (corpus pool), pertinenza/relevance, conflict-aware, direzione dell'evidenza*.

**Prossimo passo:** `domain-modeling` (glossario + ADR per gli invarianti), poi `writing-plans`.
