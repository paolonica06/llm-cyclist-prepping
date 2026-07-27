# AGENT_WORKFLOW.md — Flusso di lavoro conversazionale con le skill

Questo documento descrive come pilotare il progetto **solo tramite conversazione**
usando le skill installate a livello di repository (`.claude/skills/` per Claude,
`.agents/skills/` per Codex). Non è
necessario modificare manualmente codice, configurazioni o architettura: si
impartiscono comandi in linguaggio naturale e l'agente invoca la skill giusta.

Provenienza e integrità delle skill sono tracciate in `skills-lock.json` (hash per
ogni skill sorgente Claude). Le versioni Codex compatibili sono linkate alla stessa
sorgente quando possibile; i workflow incompatibili sono adattati localmente.
Ambito di installazione: **project**.

---

## 1. Skill per fase

| Fase | Skill | Comando conversazionale (esempi) |
|---|---|---|
| Comprensione requisiti | `grill-me` (o `grill-with-docs`) | «Interrogami a fondo sui requisiti di X» |
| Creazione PRD | `to-spec` (produce spec in stile PRD) | «Trasforma questa conversazione in un PRD» |
| Specifica tecnica | `to-spec` + `grill-with-docs` (per ADR) | «Scrivi la specifica tecnica e registra le decisioni» |
| Modellazione del dominio | `domain-modeling` | «Modella il dominio / definisci il linguaggio ubiquo» |
| Pianificazione implementazione | `writing-plans` | «Scrivi un piano di implementazione per X» |
| Esecuzione controllata del piano | `executing-plans` | «Esegui il piano con checkpoint di revisione» |
| Ricerca/esplorazione paper | `ai-research-explore` | «Esplora la letteratura su X» |
| Risoluzione dettagli di un paper | `paper-context-resolver` | «Risolvi lo split/protocollo di valutazione del paper Y» |
| Analisi di PDF | `pdf` | «Estrai testo/tabelle da questo PDF» |
| Organizzazione wiki Markdown/Obsidian | `obsidian-vault` (ripuntata a `wiki/`) | «Cerca/crea una nota nella wiki» |
| Test-driven development | `test-driven-development` | «Implementa X in TDD» |
| Debugging sistematico | `systematic-debugging` | «Debugga in modo sistematico il bug Y» |
| Verifica prima del completamento | `verification-before-completion` | «Verifica prima di dichiarare completo» |
| Revisione indipendente del codice | `requesting-code-review` → `receiving-code-review` | «Richiedi una code review» / «Analizza i rilievi della review» |
| Protezioni Git | hook Claude + Codex già configurati | (attivi di default; vedi §5) |
| Handoff tra sessioni | `handoff` | «Prepara un handoff per la prossima sessione» |
| Scoperta nuove skill | `find-skills` | «Esiste una skill per X?» |

**Nota PRD:** non esiste una skill `to-prd`; `to-spec` è descritta come "PRD-style
spec" e copre questa fase. **`ubiquitous-language` è stata esclusa** (deprecata):
la sostituisce `domain-modeling`.

---

## 2. Skill da NON usare contemporaneamente

- **`grill-me` ⟂ `grill-with-docs`**: entrambe avviano un'intervista di grilling.
  Usane **una sola** per sessione (`grill-with-docs` = `grill-me` + produzione di
  ADR/glossario via `domain-modeling`).
- **`grill-with-docs` ⟂ `domain-modeling` (separata)**: `grill-with-docs` invoca già
  `domain-modeling`; non lanciarle in parallelo (ridondante).
- **`grill-me`/interviste ⟂ `to-spec`**: prima si *interroga* (requisiti), **poi** si
  sintetizza con `to-spec`. Non sintetizzare a intervista aperta.
- **`to-spec` (il COSA) ⟂ `writing-plans` (il COME)**: sono fasi sequenziali. La spec
  descrive requisiti/comportamento; il piano descrive i passi di implementazione.
  Non confonderle né eseguirle insieme.
- **`writing-plans` → `executing-plans`**: non eseguire un piano che non esiste. Prima
  scrivere il piano, poi eseguirlo.
- **`test-driven-development` ⟂ `systematic-debugging`**: TDD guida lo sviluppo
  (red→green→refactor); il debugging sistematico si attiva **quando** un test/comportamento
  fallisce. Non usarli come cornici concorrenti sullo stesso passo.
- **`requesting-code-review` → `receiving-code-review`**: sequenziali (richiedi → ricevi),
  mai simultanee.
- **`ai-research-explore` ⟂ `paper-context-resolver`**: la prima è esplorazione ampia;
  la seconda risolve un dettaglio specifico durante una riproduzione. Modalità diverse.

---

## 3. Comandi conversazionali (cheat-sheet)

Puoi impartire questi comandi in linguaggio naturale; l'agente invocherà la skill
corrispondente (oppure indica esplicitamente il nome, es. «usa `domain-modeling`»).

- **Requisiti**: «Interrogami sui requisiti di …», «Fammi le domande scomode su …»
- **PRD / Spec**: «Genera il PRD», «Trasforma la conversazione in specifica»
- **Dominio**: «Modella il dominio», «Definisci il linguaggio ubiquo / glossario»
- **Piano**: «Scrivi il piano di implementazione», «Pianifica X passo-passo»
- **Esecuzione**: «Esegui il piano», «Procedi con checkpoint di revisione»
- **Ricerca paper**: «Esplora la letteratura su …», «Trova e valuta paper su …»
- **Dettaglio paper**: «Risolvi il protocollo/valutazione del paper …»
- **PDF**: «Analizza/estrai da questo PDF», «Compila questo modulo PDF»
- **Wiki**: «Cerca nella wiki …», «Crea una nota wiki su …»
- **TDD**: «Implementa … in TDD»
- **Debug**: «Debugga sistematicamente …»
- **Verifica**: «Verifica prima di chiudere», «Dimostra che passa»
- **Review**: «Richiedi una code review», «Valuta i rilievi della review»
- **Handoff**: «Prepara un handoff»
- **Scoperta skill**: «Esiste una skill per …?»

---

## 4. Controlli obbligatori prima di chiudere una fase (gate)

Nessuna fase è "fatta" senza il suo gate. L'agente deve **mostrare l'evidenza**, non
solo dichiararlo (principio di `verification-before-completion`).

- **Requisiti**: intervista conclusa senza ambiguità aperte; assunzioni esplicitate.
  Se `grill-with-docs`: `CONTEXT.md` aggiornato.
- **PRD/Spec**: documento con obiettivi, criteri di accettazione e out-of-scope;
  salvato in `docs/specs/` (o nel percorso esplicitamente richiesto). Pubblicazione
  su tracker solo dopo conferma.
- **Dominio**: glossario (`CONTEXT.md`) senza termini ambigui non risolti; decisioni
  chiave registrate come ADR (`docs/adr/`).
- **Piano**: file di piano prodotto (es. `docs/superpowers/plans/…`) con passi atomici
  e **criterio di verifica per ogni passo**.
- **Esecuzione**: per ogni passo, TDD seguito (test prima); al termine, `pytest` verde
  e (dove pertinente) la demo eseguita — **con output mostrato**.
- **Verifica**: comandi di verifica realmente eseguiti (`.venv/bin/python -m pytest -q`,
  `python scripts/demo.py`) e output riportato. Nessuna affermazione di successo senza prova.
- **Code review**: `requesting-code-review` ha eseguito un revisore **read-only**; i
  rilievi sono stati triagiati con `receiving-code-review`; i problemi confermati corretti;
  test ancora verdi.
- **Ricerca scientifica**: fonti verificate (DOI/PMID), nessuna citazione inventata
  (coerente con il Verification Agent del progetto). Distinguere full text vs abstract.

---

## 5. Git: autonomia di push + protezione sulle operazioni irreversibili

**Autorizzazione permanente**: l'utente ha autorizzato l'agente a **committare e
pushare in autonomia** durante la conversazione (nessuna conferma per-commit/push).
L'agente gestisce Git da sé: commit ai milestone e push dopo modifiche verificate.

Lo script condiviso `.claude/hooks/block-dangerous-git.sh` è attivato da
`.claude/settings.json` per Claude e da `.codex/hooks.json` per Codex. **Blocca solo
le operazioni irreversibili**:

`git reset --hard`, `git clean -f`/`-fd`, `git branch -D`, `git checkout .`,
`git restore .`, e il **force-push** (`push --force` / `--force-with-lease`).

Conseguenze pratiche:
- **`git push` normale è CONSENTITO** (autonomo); i comandi sicuri (`status`, `add`,
  `commit`, `log`, `diff`, `pull`, `fetch`) passano.
- Per annullare modifiche **usa la forma per-file**: `git restore <file>` /
  `git checkout -- <file>` (la forma con `.` è bloccata di proposito).
- Un **force-push** avverrà solo su tua richiesta esplicita (bloccato di default).
- L'hook fa match sulla *stringa*: un comando che contiene `reset --hard`/`push --force`
  in un echo/commento viene comunque bloccato (falso positivo innocuo → riformula).

Per allentare/inasprire: chiedi «modifica i pattern del git guardrail» (l'agente
edita `.claude/hooks/block-dangerous-git.sh`).

---

## 6. Recupero del progetto dopo un errore

1. **Fotografa lo stato**: «mostra `git status` e `git diff`». La wiki è versionata su
   Git: `git log -- wiki/` e `git show <rev>:wiki/...` recuperano versioni precedenti.
2. **Root-cause, non pezze**: attiva `systematic-debugging` («debugga sistematicamente …»)
   prima di proporre fix.
3. **Annulla modifiche non committate** (per-file, vedi §5): `git restore <file>`.
   Torna a un commit: `git checkout <rev> -- <file>` (per-file, consentito).
4. **Dati rigenerabili del progetto**: `data/kb.sqlite3` e `data/raw/` sono ricostruibili
   → si possono cancellare e rilanciare la pipeline (`research run "…"`). La wiki è
   l'output versionato: non cancellarla, semmai ripristinala da Git.
5. **Skill che si comporta male**: per Claude, rimuovi/reinstalla dalla provenienza in
   `skills-lock.json`; per Codex, correggi o rimuovi l'adattatore/link corrispondente
   in `.agents/skills/`.
6. **Chiudi con la verifica**: prima di dichiarare risolto, gate di §4 (test verdi +
   output mostrato).

---

## 7. Creare un handoff per una nuova sessione

1. Chiedi: «**Prepara un handoff**» → la skill `handoff` compatta la conversazione in un
   documento di passaggio, **redigendo** chiavi/segreti/PII, salvato nella cartella
   temporanea del sistema (fuori dal repo).
2. Porta con te anche il contesto durevole del repo: `CLAUDE.md` (architettura),
   `AGENTS.md` (istruzioni Codex), `docs/AGENT_WORKFLOW.md` (questo file), e — se in
   corso — il file di piano in `docs/superpowers/plans/` con i checkpoint di
   `executing-plans`.
3. Nella nuova sessione: apri con «**Riprendi da questo handoff**» e incolla/indica il
   documento; poi «continua il piano da dove eravamo».
4. Se il lavoro è a metà di un piano, `executing-plans` mantiene i checkpoint: riprendi
   dal primo passo non verificato.

---

## 8. Note di sicurezza (dalla revisione pre-installazione)

- **`find-skills`**: usala solo per **scoprire** skill. Regola adottata: **mai** installare
  con `-y -g` (globale, silenzioso) senza prima mostrarti l'esito della revisione.
- **`ai-research-explore`**: effettua chiamate a **API pubbliche** (arXiv, doi.org, GitHub)
  senza autenticazione né telemetria; legge chiavi di provider a pagamento **solo se
  impostate** (implementazione stub: non invia nulla); crea git-worktree e cartelle di
  output nel repo; `execution_feasibility.py` **importa dinamicamente** moduli del repo
  bersaglio (possibili side-effect). Usala con consapevolezza di questi comportamenti.
- **`pdf`**: alla prima esecuzione può installare librerie note (pypdf, pdfplumber,
  poppler…), tutte locali e senza rete.
- **`to-spec` / handoff**: scrivono in locale (`docs/specs/`, cartella temp).
  La pubblicazione su un issue tracker esterno avviene solo dopo conferma e usa
  l'eventuale connettore già configurato.

---

## 9. Inventario skill sorgente (18)

| Skill | Fonte | Rischio |
|---|---|---|
| find-skills | vercel-labs/skills | medium (guida install) |
| grill-me | mattpocock/skills | low |
| grill-with-docs | mattpocock/skills | low |
| to-spec | mattpocock/skills | low |
| domain-modeling | mattpocock/skills | low |
| obsidian-vault | mattpocock/skills (ripuntata a `wiki/`) | low (adattata) |
| git-guardrails-claude-code | mattpocock/skills | medium (hook, intenzionale) |
| handoff | mattpocock/skills | low |
| writing-plans | obra/superpowers | low |
| executing-plans | obra/superpowers | low |
| test-driven-development | obra/superpowers | low |
| systematic-debugging | obra/superpowers | low |
| verification-before-completion | obra/superpowers | low |
| requesting-code-review | obra/superpowers | low |
| receiving-code-review | obra/superpowers | low |
| ai-research-explore | lllllllama/rigorpilot-skills | medium (rete/import dinamici) |
| paper-context-resolver | lllllllama/rigorpilot-skills | low |
| pdf | anthropics/skills | low |

**Esclusa:** `ubiquitous-language` (deprecata, sostituita da `domain-modeling`).

Codex espone 15 skill di progetto: riusa 10 sorgenti compatibili, adatta localmente
`grill-me`, `grill-with-docs`, `to-spec`, `executing-plans` e `handoff`, e usa le
installazioni native per `pdf` e `find-skills`. `git-guardrails-claude-code` non viene
esposto come skill Codex perché il guardrail è già configurato direttamente negli hook.
