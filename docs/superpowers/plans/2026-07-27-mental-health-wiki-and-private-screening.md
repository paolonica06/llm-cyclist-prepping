# Mental Health Wiki and Private Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ampliare la knowledge base con evidenza verificata su psicologia della prestazione e salute mentale degli atleti, mantenendo dati personali e screening fuori dal repository pubblico.

**Architecture:** La wiki pubblica contiene esclusivamente studi, sintesi, caveat e regole di rinvio professionale. I dati personali vivono in `data/private/mental-health/`, ignorato da Git, con consenso locale, check-in non diagnostico e area per risultati di screening prodotti o supervisionati da professionisti. I topic sono costruiti dalla pipeline quando il recupero è sufficientemente specifico; in caso contrario vengono curati manualmente da fonti primarie verificate, documentando l'eccezione.

**Tech Stack:** Markdown/Obsidian, Git, SQLite, CLI `cyclist_kb`, API bibliografiche già configurate.

## Global Constraints

- Il repository remoto è pubblico: nessun dato personale o risultato di screening può entrare in Git.
- Check-in e scale 0–10 sono monitoraggio non clinico, non screening diagnostico.
- SMHAT-1 e altri strumenti riservati ai sanitari non vengono somministrati o interpretati dall’agente.
- Un risultato positivo non è una diagnosi e richiede valutazione professionale quando indicato.
- Sintomi urgenti, rischio di autolesionismo, disturbi alimentari/RED-S sospetti o compromissione persistente richiedono stop del coaching adattivo e rinvio immediato a professionisti.
- Ogni affermazione pubblica mantiene provenienza, confidenza, trasferibilità e caveat del corpus.

---

### Task 1: Confine privacy e archivio personale locale

**Files:**
- Modify: `.gitignore`
- Create (ignored): `data/private/mental-health/README.md`
- Create (ignored): `data/private/mental-health/consent.md`
- Create (ignored): `data/private/mental-health/checkins.csv`
- Create (ignored): `data/private/mental-health/screenings/README.md`

**Interfaces:**
- Consumes: consenso esplicito dell’atleta del 2026-07-27.
- Produces: percorso locale stabile e non versionato per dati sensibili.

- [x] **Step 1: Aggiungere `data/private/` a `.gitignore`.**
- [x] **Step 2: Creare il protocollo locale con scopo, confini clinici, accesso e ritiro del consenso.**
- [x] **Step 3: Creare un check-in CSV vuoto con data, contesto, stress, fatica mentale, umore, motivazione, ansia, fiducia e note.**
- [x] **Step 4: Creare l’area screening senza copiare questionari proprietari e senza soglie diagnostiche automatiche.**
- [x] **Step 5: Verificare con `git check-ignore -v data/private/mental-health/consent.md` e `git status --short` che nessun file personale sia tracciabile.**

### Task 2: Governance pubblica e protocollo persistente degli agenti

**Files:**
- Create: `wiki/Mental Health Evidence and Safeguards.md`
- Modify: `wiki/index.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: confine privacy del Task 1 e consenso locale.
- Produces: regole pubbliche per ricerca, coaching, riconoscimento e referral.

- [x] **Step 1: Scrivere la nota pubblica con separazione performance/benessere/clinica e collegamenti ai topic correlati.**
- [x] **Step 2: Collegare la nota dall’indice senza pubblicare il consenso o i dati dell’atleta.**
- [x] **Step 3: Aggiungere a `CLAUDE.md` il protocollo salute mentale e il divieto di leggere/scrivere dati privati fuori dallo scopo autorizzato.**
- [x] **Step 4: Mantenere `AGENTS.md` allineato con regole equivalenti per Codex.**
- [x] **Step 5: Verificare strutturalmente presenza dei guardrail in entrambi i file e assenza di dati sensibili nel diff.**

### Task 3: Corpus verificato di psicologia della prestazione

**Files:**
- Create/update via pipeline: `wiki/topics/psychological-skills-training-self-talk-imagery-mindfulness-and-endurance-perfo*.md`
- Create/update via pipeline: `wiki/papers/*.md`
- Update via pipeline: `wiki/index.md`

**Interfaces:**
- Consumes: pipeline `research run`.
- Produces: sintesi verificata su self-talk, imagery, mindfulness, routine e performance endurance.

- [x] **Step 1: Eseguire `KB_GIT_AUTOCOMMIT=0 .venv/bin/python -m cyclist_kb.cli run "psychological skills training self-talk imagery mindfulness and endurance performance in competitive athletes"`.**
- [x] **Step 2: Registrare l’ID ricerca e controllare `research status`.**
- [x] **Step 3: Verificare che gli studi inclusi abbiano metadati risolti, qualità/confidenza e fonte dati esplicita.**

**Esito:** la ricerca `psychological-skills-training-se-d46615` ha prodotto 183 inclusioni
troppo eterogenee e forti rate limit durante la verifica. La pipeline è stata fermata
prima della sintesi; il topic pubblico è stato curato da quattro revisioni
sistematiche/meta-analisi con DOI/PMID verificati.

### Task 4: Corpus verificato di salute mentale e dual career

**Files:**
- Create/update via pipeline: `wiki/topics/mental-health-anxiety-depression-burnout-and-help-seeking-in-competitive-endur*.md`
- Create/update via pipeline: `wiki/topics/academic-stress-dual-career-mental-fatigue-and-training-adherence-in-compet*.md`
- Create/update via pipeline: `wiki/papers/*.md`
- Update via pipeline: `wiki/index.md`

**Interfaces:**
- Consumes: pipeline `research run` e governance del Task 2.
- Produces: sintesi su sintomi/rischi/help-seeking e su carico scolastico, fatica mentale e continuità.

- [x] **Step 1: Curare il topic salute mentale da revisioni sistematiche, consensus e strumenti IOC verificati.**
- [x] **Step 2: Curare il topic dual career/carico scolastico da revisioni verificate.**
- [x] **Step 3: Controllare provenienza, qualità, trasferibilità e presenza di caveat clinici.**
- [x] **Step 4: Collegare i topic dalla nota di governance pubblica.**

### Task 5: Verifica finale e pubblicazione del solo corpus pubblico

**Files:**
- Verify: `.gitignore`, `CLAUDE.md`, `AGENTS.md`, `wiki/`, `data/private/mental-health/`

**Interfaces:**
- Consumes: tutti i deliverable precedenti.
- Produces: corpus pubblico versionato e archivio personale locale escluso da Git.

- [x] **Step 1: Eseguire `git diff --check`.**
- [x] **Step 2: Eseguire test mirati della pipeline e della wiki.**
- [x] **Step 3: Cercare nel diff nomi, risposte, punteggi o risultati personali e confermare che siano assenti.**
- [x] **Step 4: Verificare `git check-ignore` per ogni file personale.**
- [x] **Step 5: Controllare struttura, provenienza e confidenza dei tre topic curati.**
- [x] **Step 6: Committare con messaggio italiano e fare push normale solo dopo evidenza positiva.**
