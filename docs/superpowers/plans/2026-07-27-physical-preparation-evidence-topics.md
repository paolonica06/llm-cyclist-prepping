# Physical Preparation Evidence Topics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ampliare la wiki pubblica con quattro topic verificati su test CP, warm-up, torque training e infortuni da sovraccarico, aggiornando inoltre la sintesi sulla forza pesante.

**Architecture:** Le nuove note sono sintesi manuali autonome in `wiki/topics/`, costruite da fonti PubMed verificate e collegate al corpus esistente. Ogni nota separa risultati, interpretazione e applicazione prudente, esplicita confidenza e trasferibilità e marca le affermazioni operative come `studi` o `euristica`. L'aggiornamento della forza pesante integra la meta-analisi 2026 senza riscrivere o cancellare la sintesi cumulativa già generata.

**Tech Stack:** Markdown/Obsidian, fonti primarie PubMed/PMC/editori, shell POSIX per controlli strutturali, pytest, Git.

## Global Constraints

- Il pacchetto riguarda esclusivamente il corpus: non modificare piano atleta o calendario.
- Non pubblicare dati personali, risultati individuali, sintomi o screening dell'atleta.
- Conservare risultati nulli, eterogeneità, rischio di bias, confidenza e trasferibilità ai ciclisti allenati.
- Marcare le affermazioni operative come `studi`, `dati_atleta` o `euristica`; non usare `dati_atleta` in queste note generali.
- Non equiparare CP a FTP, EP a CP, WEP a W′, bassa cadenza a forza in palestra o bike fitting a prevenzione causalmente dimostrata.
- Usare DOI e PMID risolti; distinguere dati da abstract e full text.
- Collegare ogni nuova nota all'indice e ad almeno due topic pertinenti.
- Per la modifica della pagina generata sulla forza, aggiungere un'integrazione manuale chiaramente delimitata senza alterare il conteggio degli studi della pipeline.

---

### Task 1: Critical Power, W′ e validità dei test

**Files:**
- Create: `wiki/topics/critical-power-w-prime-and-test-validity.md`

**Interfaces:**
- Consumes: `wiki/papers/4081090101b05813.md`, `wiki/papers/519907d964835c9d.md`, `wiki/papers/bc8b0eceee35118c.md`
- Produces: sintesi su CP/W′, scelta del modello, protocolli multi-duration e 3-min all-out, errore di misura e prescrizione prudente

- [x] **Step 1: Verificare il controllo strutturale iniziale**

Run: `test -f wiki/topics/critical-power-w-prime-and-test-validity.md`

Expected: FAIL perché la nota non esiste ancora.

- [x] **Step 2: Scrivere la nota da fonti verificate**

Includere Quittmann e Piehl 2026 (`10.1007/s00421-026-06356-w`, PMID `42479066`), Chorley e Lamb 2020 (`10.3390/sports8090123`, PMID `32899777`), Karsten et al. 2015 (`10.1007/s00421-014-3001-z`, PMID `25260244`) e Bouillod et al. 2022 (`10.3390/s22010386`, PMID `35009945`).

Riportare esplicitamente: EP affidabile ma mediamente superiore a CP; WEP non è una stima accurata di W′; familiarizzazione e incoraggiamento sono necessari; il modello e le durate scelte cambiano la stima; validità del misuratore e condizioni di prova contribuiscono all'errore.

- [x] **Step 3: Verificare contenuti e collegamenti**

Run: `rg -n "EP|WEP|familiarizzazione|errore|Confidenza|Trasferibilità|\\[studi\\]|\\[euristica\\]|https://doi.org/10.1007/s00421-026-06356-w" wiki/topics/critical-power-w-prime-and-test-validity.md`

Expected: tutte le distinzioni e la fonte principale sono presenti.

- [x] **Step 4: Committare il topic verificato**

```bash
git add wiki/topics/critical-power-w-prime-and-test-validity.md
git commit -m "Aggiunge evidenze su CP e validità dei test"
```

### Task 2: Warm-up, priming e attivazione pre-test o gara

**Files:**
- Create: `wiki/topics/warm-up-priming-and-pre-event-activation.md`

**Interfaces:**
- Consumes: `wiki/topics/tapering-strategies-before-endurance-cycling-competitions.md`, `wiki/topics/repeated-sprint-ability-and-intermittent-high-intensity-performance-in-endurance.md`
- Produces: distinzione tra warm-up generale, openers/priming ravvicinato e PAPE

- [x] **Step 1: Verificare il controllo strutturale iniziale**

Run: `test -f wiki/topics/warm-up-priming-and-pre-event-activation.md`

Expected: FAIL perché la nota non esiste ancora.

- [x] **Step 2: Scrivere la nota da fonti verificate**

Includere Fradkin et al. 2010 (`10.1519/JSC.0b013e3181c643a0`, PMID `19996770`), Vasconcelos et al. 2024 (`10.1249/MSS.0000000000003308`, PMID `37796168`), McIntyre e Kilding 2015 (`10.1080/02640414.2014.960882`, PMID `25357090`) e Zheng et al. 2026 (`10.1186/s13102-026-01758-x`, PMID `42226251`).

Separare: beneficio generale del warm-up; effetto PAPE molto piccolo e di certezza molto bassa sull'endurance; possibili effetti sull'esplosività non automaticamente trasferibili alla cronometro; rischio che un priming all-out peggiori la prestazione per fatica residua.

- [x] **Step 3: Verificare contenuti e collegamenti**

Run: `rg -n "warm-up generale|PAPE|openers|fatica residua|Confidenza|Trasferibilità|\\[studi\\]|\\[euristica\\]" wiki/topics/warm-up-priming-and-pre-event-activation.md`

Expected: i tre concetti sono distinti e i caveat sono presenti.

- [x] **Step 4: Committare il topic verificato**

```bash
git add wiki/topics/warm-up-priming-and-pre-event-activation.md
git commit -m "Aggiunge evidenze su warm-up e priming"
```

### Task 3: Torque training, bassa cadenza e forza specifica

**Files:**
- Create: `wiki/topics/torque-training-low-cadence-and-cycling-specific-strength.md`

**Interfaces:**
- Consumes: `wiki/papers/4b0b456dc6f6aceb.md`, `wiki/topics/concurrent-strength-training-and-endurance-cycling-performance.md`
- Produces: sintesi che distingue cadenza, torque, intensità relativa e forza massima

- [x] **Step 1: Verificare il controllo strutturale iniziale**

Run: `test -f wiki/topics/torque-training-low-cadence-and-cycling-specific-strength.md`

Expected: FAIL perché la nota non esiste ancora.

- [x] **Step 2: Scrivere la nota da fonti verificate**

Includere Hansen e Rønnestad 2017 (`10.1123/ijspp.2016-0574`, PMID `28095074`), de Pablos et al. 2026 (`10.1111/sms.70294`, PMID `42076918`) e Kristoffersen et al. 2014 (`10.3389/fphys.2014.00034`).

Conservare: assenza di evidenza forte nella revisione; eterogeneità dei protocolli; risultato favorevole del singolo RCT 2026 per il braccio high-load senza superiorità statisticamente dimostrata sul low-load; nessuna equivalenza automatica con la forza pesante in palestra.

- [x] **Step 3: Verificare contenuti e collegamenti**

Run: `rg -n "cadenza|torque|intensità relativa|forza pesante|singolo RCT|Confidenza|Trasferibilità|\\[studi\\]|\\[euristica\\]" wiki/topics/torque-training-low-cadence-and-cycling-specific-strength.md`

Expected: concetti, gerarchia dell'evidenza e limiti sono espliciti.

- [x] **Step 4: Committare il topic verificato**

```bash
git add wiki/topics/torque-training-low-cadence-and-cycling-specific-strength.md
git commit -m "Aggiunge evidenze sul torque training"
```

### Task 4: Aggiornamento sulla forza pesante

**Files:**
- Modify: `wiki/topics/concurrent-strength-training-and-endurance-cycling-performance.md`

**Interfaces:**
- Consumes: meta-analisi Llanos-Lagos et al. 2026 (`10.1007/s00421-025-05883-2`, PMID `40632222`)
- Produces: integrazione manuale delimitata su efficienza, potenza anaerobica, performance e risultati nulli

- [x] **Step 1: Verificare che la fonte non sia già integrata**

Run: `rg -n "10.1007/s00421-025-05883-2|40632222" wiki/topics/concurrent-strength-training-and-endurance-cycling-performance.md`

Expected: FAIL senza risultati.

- [x] **Step 2: Aggiungere l'integrazione manuale**

Inserire una sezione distinta prima di `Cronologia aggiornamenti`, senza cambiare il conteggio pipeline di 11 studi. Riportare 17 studi/262 partecipanti, effetti favorevoli su efficienza (`ES=0,353`), potenza anaerobica (`ES=0,560`) e performance (`ES=0,463`), risultati non significativi su VO₂max, pVO₂max, MMSS e capacità anaerobica e certezza GRADE bassa.

- [x] **Step 3: Verificare risultati positivi e nulli**

Run: `rg -n "ES=0,353|ES=0,560|ES=0,463|pVO₂max|MMSS|certezza.*bassa|10.1007/s00421-025-05883-2" wiki/topics/concurrent-strength-training-and-endurance-cycling-performance.md`

Expected: effetti, nulli, certezza e DOI sono presenti.

- [x] **Step 4: Committare l'aggiornamento verificato**

```bash
git add wiki/topics/concurrent-strength-training-and-endurance-cycling-performance.md
git commit -m "Aggiorna le evidenze sulla forza pesante"
```

### Task 5: Infortuni da sovraccarico, dolore e bike fitting

**Files:**
- Create: `wiki/topics/cycling-overuse-injuries-pain-and-bike-fitting.md`

**Interfaces:**
- Consumes: `wiki/topics/training-load-monitoring-and-overtraining-in-endurance-cyclists.md`
- Produces: sintesi su associazioni con carico, biomeccanica, fitting e confine medico

- [x] **Step 1: Verificare il controllo strutturale iniziale**

Run: `test -f wiki/topics/cycling-overuse-injuries-pain-and-bike-fitting.md`

Expected: FAIL perché la nota non esiste ancora.

- [x] **Step 2: Scrivere la nota da fonti verificate**

Includere Visentini et al. 2022 (`10.1016/j.jsams.2021.12.008`, PMID `35151569`), Bini e Bini 2018 (`10.2147/OAJSM.S136653`, PMID `29872355`), Johnston et al. 2017 (`10.26603/ijspt20171023`, PMID `29234554`) e Barrajón et al. 2026 (`10.7759/cureus.101718`, PMID `41705012`).

Separare associazione da causalità, rischio da sintomo, comfort da prevenzione. Riportare che solo 3/18 studi della review principale avevano basso rischio di bias, che il carico ha evidenza associativa moderata e che molte misure tradizionali di fitting non hanno relazione dimostrata con dolore/infortunio. Presentare la review 2026 sulla lombalgia come segnale promettente ma basato su soli tre studi eterogenei.

- [x] **Step 3: Inserire il confine medico**

Indicare valutazione professionale in caso di trauma, dolore severo o progressivo, gonfiore importante, deficit neurologici, sintomi sistemici, dolore notturno persistente o compromissione funzionale; non fornire diagnosi né correzioni universali di fitting.

- [x] **Step 4: Verificare contenuti e collegamenti**

Run: `rg -n "3/18|associazione|causalità|comfort|prevenzione|professionista|Confidenza|Trasferibilità|\\[studi\\]|\\[euristica\\]" wiki/topics/cycling-overuse-injuries-pain-and-bike-fitting.md`

Expected: limiti causali, confine medico e classificazione dell'evidenza sono presenti.

- [x] **Step 5: Committare il topic verificato**

```bash
git add wiki/topics/cycling-overuse-injuries-pain-and-bike-fitting.md
git commit -m "Aggiunge evidenze su sovraccarico e bike fitting"
```

### Task 6: Integrazione, controlli strutturali e pubblicazione

**Files:**
- Modify: `wiki/index.md`
- Modify: le cinque note del pacchetto per eventuali link bidirezionali
- Modify: `docs/superpowers/plans/2026-07-27-physical-preparation-evidence-topics.md`

**Interfaces:**
- Consumes: i deliverable dei task 1-5
- Produces: navigazione coerente, piano tracciato e corpus pubblico verificato

- [x] **Step 1: Collegare le note**

Aggiungere i quattro nuovi topic a `wiki/index.md` e verificare almeno due collegamenti pertinenti per ciascuna nuova nota. Aggiungere link bidirezionali solo dove migliorano la navigazione, senza duplicare le sintesi.

- [x] **Step 2: Marcare i task completati**

Sostituire con `[x]` le checkbox dei passi effettivamente verificati in questo piano.

- [x] **Step 3: Controllare i link relativi**

Run:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import re

paths = [Path("wiki/index.md"), *Path("wiki/topics").glob("*.md")]
missing = []
for path in paths:
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]+)?)\)", text):
        raw = target.split("#", 1)[0].replace("%20", " ")
        resolved = (path.parent / raw).resolve()
        if not resolved.exists():
            missing.append(f"{path}: {target}")
if missing:
    raise SystemExit("\n".join(missing))
print(f"Link relativi verificati in {len(paths)} file")
PY
```

Expected: `Link relativi verificati` e nessun percorso mancante.

- [x] **Step 4: Controllare fonti, privacy e formato**

Run:

```bash
rg -n "10.1007/s00421-026-06356-w|10.1249/MSS.0000000000003308|10.1111/sms.70294|10.1007/s00421-025-05883-2|10.1016/j.jsams.2021.12.008" wiki/topics
git ls-files data/private
git diff --check
```

Expected: i cinque DOI chiave compaiono; `git ls-files data/private` non produce output; `git diff --check` non produce errori.

- [x] **Step 5: Eseguire la suite completa**

Run: `.venv/bin/python -m pytest -q`

Expected: tutti i test passano.

- [x] **Step 6: Verificare il diff finale**

Run: `git status --short && git diff --stat HEAD && git diff HEAD -- wiki docs/superpowers/plans/2026-07-27-physical-preparation-evidence-topics.md`

Expected: solo piano, indice e note scientifiche previste; nessun dato personale o modifica al piano atleta.

### Task 7: Durabilità della rigenerazione e pubblicazione

**Files:**
- Modify: `cyclist_kb/wiki.py`
- Modify: `cyclist_kb/agents/synthesis.py`
- Create: `tests/test_wiki_manual_blocks.py`
- Modify: `wiki/index.md`
- Modify: `wiki/topics/concurrent-strength-training-and-endurance-cycling-performance.md`
- Modify: le quattro nuove note del pacchetto

**Interfaces:**
- Consumes: i blocchi curati creati nei task precedenti e il feedback della review
- Produces: contratto di preservazione dei blocchi manuali e corpus pronto alla pubblicazione

- [x] **Step 1: Scrivere e osservare fallire i test di regressione**

Run: `.venv/bin/python -m pytest tests/test_wiki_manual_blocks.py -q`

Expected prima del fix: 2 FAIL, perché indice e pagina topic perdono i blocchi manuali.

- [x] **Step 2: Implementare il contratto minimo di preservazione**

Estrarre i blocchi delimitati da `<!-- BEGIN MANUAL: nome -->` e
`<!-- END MANUAL: nome -->`; preservare `index-preamble`, `index-topics` e i blocchi
con prefisso `topic-` nelle rigenerazioni.

- [x] **Step 3: Delimitare i blocchi curati e completare la provenienza**

Aggiungere i marker all'indice e all'integrazione sulla forza; etichettare ogni
raccomandazione applicativa come `[studi]` o `[euristica]`; aggiungere `Fonte dati`
per studio dove abstract e full text erano mescolati.

- [x] **Step 4: Riverificare test mirati, suite, link, privacy e diff**

Run:

```bash
.venv/bin/python -m pytest tests/test_wiki_manual_blocks.py -q
.venv/bin/python -m pytest -q
git diff --check
```

Expected: test mirati e suite completi verdi; nessun errore di formato.

- [x] **Step 5: Committare il follow-up della review**

```bash
git add cyclist_kb tests wiki docs/superpowers/plans/2026-07-27-physical-preparation-evidence-topics.md
git commit -m "Preserva le integrazioni curate della wiki"
```

- [ ] **Step 6: Pubblicare**

```bash
git push
```

Expected: push normale su `origin/main` completato senza errori.
