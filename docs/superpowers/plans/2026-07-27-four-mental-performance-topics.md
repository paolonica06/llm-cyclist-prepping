# Four Mental Performance Topics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ampliare la wiki con quattro topic prioritari e verificati su pressione competitiva, perfezionismo/burnout, motivazione/clima e identità atletica.

**Architecture:** Ogni topic è una nota pubblica autonoma in `wiki/topics/`, curata da revisioni sistematiche, meta-analisi o review quadro con DOI/PMID risolti. Le note distinguono associazioni da causalità, separano performance da salute mentale e contengono confidenza, trasferibilità, applicazioni prudenti e collegamenti alle note esistenti. Nessun dato personale entra nella wiki.

**Tech Stack:** Markdown/Obsidian, fonti primarie PubMed/PMC/editori, Git, test strutturali locali.

## Global Constraints

- Non pubblicare dati, punteggi, sintomi o risultati personali dell'atleta.
- Non trasformare costrutti psicologici o screening in diagnosi.
- Etichettare le affermazioni applicative come `studi`, `dati_atleta` o `euristica`.
- Mantenere risultati nulli, eterogeneità, rischio di bias e limiti di trasferibilità.
- Preferire revisioni sistematiche/meta-analisi; usare review narrative solo come quadro.
- Non usare “mental toughness” senza definizione operativa.
- Collegare ogni nuova nota alla governance e ad almeno due topic correlati.

---

### Task 1: Ansia competitiva, pressione e choking

**Files:**
- Create: `wiki/topics/competitive-anxiety-pressure-and-choking.md`

**Interfaces:**
- Consumes: `wiki/topics/psychological-skills-and-endurance-performance.md`
- Produces: sintesi su ansia cognitiva/somatica, pressione, choking e routine pre-performance

- [x] **Step 1:** Verificare metadati e risultati di Li et al. 2026 (`10.1186/s40798-026-01007-y`), Zeng et al. 2026 (`10.1016/j.psychsport.2026.103130`), Niering et al. 2023 (`10.3390/bs13110910`) e Reinebo et al. 2024 (`10.1007/s40279-023-01931-z`).
- [x] **Step 2:** Scrivere evidenze, risultati contrastanti, interpretazione e applicazione prudente a test/gara.
- [x] **Step 3:** Verificare presenza di confidenza, trasferibilità e distinzione tra riduzione dell'ansia e miglioramento prestativo.

### Task 2: Perfezionismo, burnout e allenamento compulsivo

**Files:**
- Create: `wiki/topics/perfectionism-burnout-and-compulsive-training.md`

**Interfaces:**
- Consumes: `wiki/topics/dual-career-academic-stress-and-mental-fatigue.md`, `wiki/topics/training-load-monitoring-and-overtraining-in-endurance-cyclists.md`
- Produces: distinzione tra strivings/concerns, burnout, compulsive exercise e confini clinici

- [x] **Step 1:** Verificare Yang et al. 2023 (`10.3390/healthcare11101417`), Hill e Curran 2016 (`10.1177/1088868315596286`), Wilczyńska et al. 2022 (`10.3390/ijerph191710662`), Gustafsson et al. 2017 (`10.1016/j.copsyc.2017.05.002`) e la meta-analisi perfectionism/compulsive exercise (`PMID 39820893`).
- [x] **Step 2:** Separare burnout psicologico, maladattamento da carico, overtraining, esercizio compulsivo e disturbi alimentari/RED-S.
- [x] **Step 3:** Inserire early warning non diagnostici e referral per compromissione persistente o sospetto clinico.

### Task 3: Motivazione, obiettivi e clima motivazionale

**Files:**
- Create: `wiki/topics/motivation-goal-setting-and-motivational-climate.md`

**Interfaces:**
- Consumes: `wiki/topics/dual-career-academic-stress-and-mental-fatigue.md`
- Produces: sintesi su clima mastery/ego, autonomia, bisogni psicologici e goal setting

- [x] **Step 1:** Verificare Lochbaum e Sisneros 2024 sul benessere (`10.3390/ejihpe14040064`) e sulla performance (`10.3390/sports12110299`), Raabe et al. 2019 (`10.1123/jsep.2019-0026`) e Xu et al. 2025 (`10.1002/ijop.70044`).
- [x] **Step 2:** Distinguere qualità della motivazione, quantità della motivazione e outcome prestativo.
- [x] **Step 3:** Tradurre in principi osservabili senza prescrivere uno stile universale di coaching.

### Task 4: Identità atletica, autostima e transizioni

**Files:**
- Create: `wiki/topics/athletic-identity-self-worth-and-transitions.md`

**Interfaces:**
- Consumes: `wiki/topics/dual-career-academic-stress-and-mental-fatigue.md`, `wiki/topics/mental-health-in-competitive-athletes.md`
- Produces: sintesi su identità atletica, identity foreclosure, infortunio, ritiro e valore personale

- [x] **Step 1:** Verificare Chun et al. 2023 (`10.3390/sports11100203`), la review sugli atleti ≤22 anni (`PMID 34299786`), Di Rocco et al. 2025 (`10.3390/sports13120438`) e Furie et al. 2023 (`10.1007/s12178-023-09830-6`).
- [x] **Step 2:** Conservare la doppia natura dell'identità atletica: appartenenza/continuità e vulnerabilità quando esclusiva.
- [x] **Step 3:** Collegare identità, dual career, infortunio e transizioni senza inferenze diagnostiche.

### Task 5: Integrazione e verifica

**Files:**
- Modify: `wiki/index.md`
- Modify: `wiki/Mental Health Evidence and Safeguards.md`
- Modify: `wiki/topics/psychological-skills-and-endurance-performance.md`
- Modify: `wiki/topics/dual-career-academic-stress-and-mental-fatigue.md`

**Interfaces:**
- Consumes: i quattro topic completati
- Produces: navigazione bidirezionale e corpus pubblico verificato

- [x] **Step 1:** Aggiungere i quattro topic all'indice e alla nota di governance.
- [x] **Step 2:** Aggiungere collegamenti correlati dalle note esistenti senza duplicare le sintesi.
- [x] **Step 3:** Eseguire un controllo automatico dei link relativi delle note coinvolte.
- [x] **Step 4:** Eseguire `git diff --check` e la suite completa `.venv/bin/python -m pytest -q`.
- [x] **Step 5:** Verificare che `git ls-files data/private` sia vuoto e che il diff non contenga dati personali.
- [x] **Step 6:** Committare in italiano e fare push normale solo dopo verifiche positive.
