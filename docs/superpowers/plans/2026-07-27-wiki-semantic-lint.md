# Wiki Semantic Lint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere un comando Python deterministico che valida struttura, collegamenti, marker manuali, provenienza e privacy della wiki, integrato nella suite pytest e in GitHub Actions.

**Architecture:** La logica vive in `cyclist_kb/wiki_lint.py` ed espone risultati strutturati; `scripts/lint_wiki.py` è un wrapper sottile con exit code da CLI. Il lint usa solo la standard library, analizza tutti i Markdown per struttura e link, ma limita le regole di stile alle superfici curate per non fallire sul whitespace degli abstract generati. Un test sul repository rende il lint parte della suite ordinaria.

**Tech Stack:** Python 3.9+, `pathlib`, `re`, `urllib.parse`, `argparse`, pytest, Markdown/Obsidian, GitHub Actions.

## Global Constraints

- Nessuna dipendenza Node/npm o nuova dipendenza runtime.
- Non modificare né includere nei commit `wiki/Senza nome.base` e `wiki/Senza nome.canvas`.
- Non leggere o pubblicare dati sotto `data/private/`.
- Il lint deve essere offline, deterministico e terminare con exit code `0` senza errori, `1` con errori di corpus, `2` per root inesistente.
- Ogni errore deve avere formato stabile `percorso:linea: CODICE messaggio`.
- Controllare tutti i `wiki/**/*.md`; ignorare formati Obsidian non Markdown.
- Le regole di provenienza si applicano alle note con intestazione `Corpus curato manualmente`, non alle pagine generate dalla pipeline.
- Le regole di stile non devono segnalare il whitespace storico dentro `wiki/papers/`.

---

### Task 1: Motore del lint e ciclo TDD

**Files:**
- Create: `cyclist_kb/wiki_lint.py`
- Create: `scripts/lint_wiki.py`
- Create: `tests/test_wiki_lint.py`

**Interfaces:**
- Produces: `LintIssue(path: Path, line: int, code: str, message: str)`
- Produces: `lint_wiki(root: Path) -> list[LintIssue]`
- Produces: `main(argv: Sequence[str] | None = None) -> int`

- [x] **Step 1: Scrivere il primo test CLI rosso**

Il test crea una wiki temporanea con `index.md` che collega `topics/missing.md`, esegue
`python scripts/lint_wiki.py --root <wiki>` e richiede exit code `1` e una diagnostica
contenente `WIKI001`.

- [x] **Step 2: Eseguire il test e osservare il fallimento corretto**

Run: `.venv/bin/python -m pytest tests/test_wiki_lint.py::test_cli_reports_missing_relative_link -q`

Expected: FAIL perché `scripts/lint_wiki.py` non esiste ancora.

- [x] **Step 3: Implementare il minimo per link relativi e CLI**

Riconoscere link Markdown locali verso `.md`, decodificare `%20`, risolverli rispetto
al file sorgente e produrre `WIKI001` se il target manca. Il wrapper aggiunge la radice
del repository a `sys.path` come gli altri script locali e chiama `main()`.

- [x] **Step 4: Rendere verde il primo test**

Run: `.venv/bin/python -m pytest tests/test_wiki_lint.py::test_cli_reports_missing_relative_link -q`

Expected: PASS.

- [x] **Step 5: Aggiungere test rossi per le altre regole**

I test devono esercitare file reali in una directory temporanea e verificare:

```python
assert "WIKI002" in codes  # wikilink irrisolto o ambiguo
assert "WIKI003" in codes  # marker MANUAL non accoppiato/mismatched/duplicato
assert "WIKI004" in codes  # target duplicato nell'indice
assert "WIKI005" in codes  # DOI/PMID non canonico o malformato
assert "WIKI006" in codes  # raccomandazione curata senza [studi]/[euristica]/[dati_atleta]
assert "WIKI007" in codes  # identificatore privato o prefisso di segreto
assert "WIKI008" in codes  # tabella con numero di colonne incoerente
assert "WIKI009" in codes  # H1 mancante/duplicato o salto di livello heading
assert "WIKI010" in codes  # tab/trailing whitespace fuori da wiki/papers
```

- [x] **Step 6: Osservare i test fallire per regole mancanti**

Run: `.venv/bin/python -m pytest tests/test_wiki_lint.py -q`

Expected: i test nuovi falliscono perché il motore implementa soltanto `WIKI001`.

- [x] **Step 7: Implementare le regole minime**

Usare funzioni pure per scansione link, wikilink, marker, identificatori, tabelle,
heading e sezioni operative. Ordinare i risultati per percorso, linea e codice.
Riconoscere come sezioni operative curate i titoli contenenti `Applicazione` o
`Principi osservabili`; ogni item numerato deve iniziare con
`**[studi]**`, `**[euristica]**` o `**[dati_atleta]**`.

- [x] **Step 8: Rendere verde il test file**

Run: `.venv/bin/python -m pytest tests/test_wiki_lint.py -q`

Expected: tutti i test del lint passano.

- [x] **Step 9: Committare il motore verificato**

```bash
git add cyclist_kb/wiki_lint.py scripts/lint_wiki.py tests/test_wiki_lint.py
git commit -m "Aggiunge il lint semantico della wiki"
```

### Task 2: Portare il corpus reale a lint verde

**Files:**
- Modify: `tests/test_wiki_lint.py`
- Modify: `wiki/topics/competitive-anxiety-pressure-and-choking.md`
- Modify: `wiki/topics/motivation-goal-setting-and-motivational-climate.md`
- Modify: `wiki/topics/athletic-identity-self-worth-and-transitions.md`
- Modify: `wiki/topics/psychological-skills-and-endurance-performance.md`

**Interfaces:**
- Consumes: `lint_wiki(root)`
- Produces: un gate pytest sul corpus reale e raccomandazioni curate con provenienza esplicita

- [x] **Step 1: Aggiungere il test d'integrazione sul repository**

```python
def test_repository_wiki_passes_lint():
    issues = lint_wiki(REPO_ROOT / "wiki")
    assert issues == [], "\n".join(issue.format(REPO_ROOT) for issue in issues)
```

- [x] **Step 2: Osservare la baseline rossa**

Run: `.venv/bin/python -m pytest tests/test_wiki_lint.py::test_repository_wiki_passes_lint -q`

Expected: FAIL con `WIKI006` sulle 21 raccomandazioni curate storiche senza etichetta;
eventuali altri errori reali vengono corretti solo se la regola è valida e non rumorosa.

- [x] **Step 3: Aggiungere la provenienza alle raccomandazioni**

Prefissare gli item operativi delle quattro note con `**[euristica]**`, mantenendo
testo e significato invariati. Non introdurre `dati_atleta` nella wiki pubblica.

- [x] **Step 4: Rendere verde corpus e CLI**

Run:

```bash
.venv/bin/python scripts/lint_wiki.py
.venv/bin/python -m pytest tests/test_wiki_lint.py -q
```

Expected: `Wiki lint: OK` e tutti i test del lint passano.

- [x] **Step 5: Committare il corpus conforme**

```bash
git add tests/test_wiki_lint.py wiki/topics
git commit -m "Allinea le note curate al lint wiki"
```

### Task 3: Documentazione e automazione CI

**Files:**
- Modify: `README.md`
- Create: `.github/workflows/wiki-lint.yml`
- Modify: `.github/workflows/enrich-corpus.yml`

**Interfaces:**
- Consumes: `python scripts/lint_wiki.py`
- Produces: comando documentato, controllo su push/PR e gate prima del commit notturno della wiki

- [x] **Step 1: Documentare il comando**

Aggiungere in `README.md` una sezione breve sotto `Test`:

```bash
python scripts/lint_wiki.py
```

con elenco delle famiglie di controlli e nota che `wiki/papers/` è esclusa soltanto
dalle regole di whitespace, non da link/struttura.

- [x] **Step 2: Aggiungere il workflow dedicato**

Creare `wiki-lint.yml` su `push` e `pull_request` limitati a `wiki/**`,
`cyclist_kb/wiki_lint.py`, `scripts/lint_wiki.py`, `tests/test_wiki_lint.py` e ai
workflow stessi. Usare Python 3.11, installare `.[test]`, eseguire CLI e test mirati.

- [x] **Step 3: Proteggere l'arricchimento notturno**

In `enrich-corpus.yml`, dopo l'arricchimento e prima del commit, eseguire:

```yaml
- name: Verifica la wiki
  run: python scripts/lint_wiki.py
```

- [x] **Step 4: Verificare YAML e diff**

Run:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import yaml
for path in Path(".github/workflows").glob("*.yml"):
    yaml.safe_load(path.read_text(encoding="utf-8"))
print("Workflow YAML validi")
PY
git diff --check
```

Expected: workflow parseabili e nessun errore di whitespace.

### Task 4: Verifica, review e pubblicazione

**Files:**
- Modify: `docs/superpowers/plans/2026-07-27-wiki-semantic-lint.md`

**Interfaces:**
- Consumes: tutti i deliverable precedenti
- Produces: feature verificata, revisionata e pubblicata

- [x] **Step 1: Eseguire i gate finali**

Run:

```bash
.venv/bin/python scripts/lint_wiki.py
.venv/bin/python -m pytest -q
git diff --check
git ls-files data/private
```

Expected: lint OK, suite completa verde, nessun errore diff e nessun file privato tracciato.

- [x] **Step 2: Richiedere e ricevere code review**

Revisionare il range dall'ultimo commit su `origin/main`, correggere ogni rilievo
Critical/Important confermato e rieseguire i gate.

- [x] **Step 3: Marcare il piano completato**

Mettere `[x]` soltanto sui passi con evidenza positiva.

- [x] **Step 4: Committare e pubblicare**

```bash
git add README.md .github cyclist_kb scripts tests wiki/topics docs/superpowers/plans/2026-07-27-wiki-semantic-lint.md
git commit -m "Integra il lint wiki nei controlli automatici"
git push
```

Expected: `origin/main` allineato a `HEAD`; i file Obsidian non tracciati restano esclusi.
