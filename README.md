# Cyclist KB — Knowledge base scientifica ciclistica auto-mantenuta

MVP locale di una knowledge base scientifica sull'allenamento ciclistico,
mantenuta da una pipeline di agenti. **Non addestra alcun modello**: usa API di
LLM esistenti (o euristiche deterministiche offline) e recupera autonomamente
letteratura da **PubMed, OpenAlex, Semantic Scholar e Crossref**.

L'output è una **wiki Markdown interconnessa e versionata con Git**, in cui ogni
affermazione scientifica è collegata ai paper che la sostengono, evidenze e
interpretazione sono separate, e nessuna citazione non verificata entra nelle
pagine.

## Architettura della pipeline

```
create → search → screen → verify → extract → quality → synthesize → (athlete)
```

| Fase | Agente | Responsabilità |
|---|---|---|
| search | **Research** | genera query e sinonimi, interroga le 4 banche dati, salva il grezzo, fa citation chasing |
| — | **Deduplication** | deduplica per DOI → PMID → firma titolo/anno/autore, conservando la provenienza |
| screen | **Screening** | pertinenza + distinzione ciclismo / altri endurance / non allenati; motivo sempre registrato, nessuna eliminazione |
| verify | **Verification** | verifica DOI (Crossref) e PMID (PubMed), coerenza metadati, blocca i non verificati |
| extract | **Extraction** | estrae i campi strutturati; mai inventa; distingue dato da full text vs solo abstract |
| quality | **Quality** | tipo di studio, qualità metodologica, confidenza, trasferibilità (**senza citation count**) |
| synthesize | **Synthesis** | aggiorna la wiki: evidenze/interpretazione/applicazione, conserva i conflitti, collega ai paper |
| athlete | **Athlete Context** | confronta studi e profilo atleta, evidenzia differenze, formula ipotesi (non prescrizioni) |

### Stati del record

`discovered → pending_screening → {included | excluded}`, poi
`{metadata_verified | needs_review}`, `{full_text_available | abstract_only}`,
`extracted`, `synthesized`. I record esclusi o da rivedere **non vengono mai
eliminati**.

## Installazione

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # oppure: pip install -r requirements.txt
cp .env.example .env        # imposta KB_CONTACT_EMAIL (consigliato)
```

Senza `ANTHROPIC_API_KEY` la pipeline funziona comunque in **modalità euristica
offline** (deterministica). Con la chiave, gli agenti usano l'LLM e ricadono
sull'euristica in caso di errore.

## CLI

```bash
research create "interval training and VO2max in trained competitive cyclists"
research search   <research_id>
research screen   <research_id>
research verify   <research_id>
research extract  <research_id>
research quality  <research_id>
research synthesize <research_id>
research athlete  <research_id> profiles/example_athlete.yaml
research status   <research_id>
research list

# intera pipeline in un colpo (ogni fase resta comunque eseguibile a parte):
research run "interval training and VO2max in trained competitive cyclists" \
    --profile profiles/example_athlete.yaml
```

## API (prima della GUI)

```bash
uvicorn cyclist_kb.api:app --reload
# POST /research, POST /research/{id}/search, ... GET /research/{id}
```

## Demo

```bash
python scripts/demo.py
```

Esegue l'intera pipeline sul tema *«interval training and VO2max in trained
competitive cyclists»*, genera la wiki in `wiki/` e la contestualizza sul profilo
`profiles/example_athlete.yaml`.

## Test

```bash
pytest                 # tutti i test
pytest tests/test_dedup.py -q
pytest tests/test_verification.py::test_title_mismatch_flags_needs_review -q
```

## Etica del recupero

Il full text viene recuperato **solo** se disponibile via open access come testo
lecito; i PDF protetti non vengono scaricati né parsati. In assenza di full text
si usano metadati e abstract, indicando chiaramente il limite (`based_on:
abstract` nelle estrazioni).
