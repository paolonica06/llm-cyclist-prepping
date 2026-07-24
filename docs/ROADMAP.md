# ROADMAP.md — Roadmap, todo e cose fatte

> **Come funziona (fonte unica di verità).** Questo file è mantenuto **da me
> (l'agente)** e versionato in Git. È la roadmap *strategica*: fasi, cosa è fatto,
> cosa manca. Il dettaglio *tattico* del task in corso vive nel relativo piano in
> `docs/superpowers/plans/…` (con checkpoint), mentre durante l'esecuzione uso la
> task-list della sessione. A fine task faccio il **roll-up** qui.
>
> **Comandi conversazionali:** «aggiorna la roadmap», «segna X come fatto»,
> «cosa manca / qual è il prossimo passo», «apri il piano per <fase>».
> Legenda: `- [x]` fatto · `- [~]` in corso · `- [ ]` da fare.

Ultimo aggiornamento: 2026-07-24 · Test: **34 verdi** · Stato: MVP completo, in attesa di iniziare la Fase B.

---

## ✅ Fatto

- [x] **Fase 0 — MVP "backbone evidenze"** (pipeline scientifica auto-mantenuta)
  - [x] Architettura + schemi dati (Pydantic, stati, SQLite)
  - [x] 4 client bibliografici (PubMed, OpenAlex, Semantic Scholar, Crossref) + citation chasing
  - [x] Dedup (DOI→PMID→firma) con guard sui conflitti; Screening; Verification (gate); Extraction; Quality; Synthesis; Athlete Context
  - [x] CLI (`research …`) + API FastAPI + wiki Markdown versionata su Git
  - [x] Demo end-to-end su «interval training and VO2max in trained competitive cyclists»
  - [x] **34 test** verdi; pyflakes pulito
- [x] **Revisione multi-agente + fix**: 26 problemi confermati corretti (dedup, gate di verifica, crash autori, sintesi cumulativa, ecc.)
- [x] **Setup skill + guardrail**: 18 skill (livello repo), protezione Git attiva, routing autonomo delle skill, `docs/AGENT_WORKFLOW.md`

> ✅ **Committato** come base dell'audit-log (commit locali sul branch `main`).
> Push autonomo **autorizzato**; manca ancora un **remote** (nessun `origin`
> configurato) → il push sarà effettivo appena aggiungi un repository remoto.

---

## 🔨 In corso

_Nessun task attivo._ Prossimo candidato: **Fase B**.

---

## ⏳ Prossimi passi (backlog)

- [ ] **Fase A — Ampliare il corpus wiki** (esecuzione ricorrente, a bassa priorità)
  - [ ] Lanciare `research run` su più temi (periodizzazione, tapering, forza, nutrizione, recupero, caldo/altitudine…)
- [ ] **Fase B — Modello dati atleta longitudinale** ⭐ *prossimo*
  - [ ] Requisiti (grill-me) → PRD (to-spec) → dominio (domain-modeling)
  - [ ] Schema serie storiche (carico/CTL-ATL-TSB, curva di potenza, distribuzione intensità, gare, sonno/peso/HRV)
  - [ ] Ingestione da `.fit`/CSV / API (intervals.icu, Strava, Garmin)
  - [ ] Metriche derivate + test
- [ ] **Fase C — Retrieval/RAG sulla wiki** (grounding delle raccomandazioni, pesato per qualità/trasferibilità)
- [ ] **Fase D — CoachAgent + feedback loop** (analisi stato → piano/aggiustamenti citati; log esecuzione→esito)
- [ ] **Fase E — Interfaccia conversazionale** ("chiedi al preparatore") su CLI/API/GUI

---

## Convenzioni di aggiornamento

1. **Un solo posto per lo stato strategico**: questo file. Niente todo sparse.
2. **Ogni fase, prima di "fatto"**, passa i gate di `docs/AGENT_WORKFLOW.md` §4
   (test verdi + evidenza mostrata via `verification-before-completion`).
3. **Piani di dettaglio**: `writing-plans` crea `docs/superpowers/plans/<slug>.md`;
   qui in "In corso" metto solo il link + stato sintetico.
4. **Handoff**: la skill `handoff` referenzia questo file, così una nuova sessione
   riparte leggendo `ROADMAP.md` + il piano attivo.
5. **Git = audit-log del fatto**: committo i milestone (commit locale; push bloccato).
