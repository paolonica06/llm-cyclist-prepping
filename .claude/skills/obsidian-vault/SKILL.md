---
name: obsidian-vault
description: Search, create, and manage notes in the project's Markdown/Obsidian wiki with wikilinks and index notes. Use when the user wants to find, create, or organize notes in the wiki.
---

# Obsidian Vault (adattata al progetto)

> Adattamento locale: il percorso originale hardcoded dell'autore
> (`/mnt/d/Obsidian Vault/AI Research/`) è stato ripuntato alla wiki Markdown
> di questo repository. La wiki è versionata da Git e generata/aggiornata dagli
> agenti della pipeline (Synthesis/Athlete).

## Vault location

`wiki/` (radice del repository)

Struttura: `wiki/index.md`, `wiki/topics/`, `wiki/papers/`, `wiki/athlete/`.

## Naming conventions

- **Index notes**: aggregano argomenti correlati (es. `index.md`, indici per area)
- **Title case** per i titoli delle note dove sensato
- Le sottocartelle esistenti (`topics/`, `papers/`, `athlete/`) sono create dagli
  agenti; per note libere usare link e index note invece di nuove cartelle

## Linking

- Sintassi Obsidian `[[wikilinks]]`: `[[Note Title]]` (compatibile con Markdown
  standard; le pagine generate usano anche link relativi `[testo](percorso.md)`)
- Le note collegano in fondo le note correlate/dipendenze
- Le index note sono elenchi di `[[wikilinks]]`

## Workflows

### Search for notes

```bash
# Per nome file
find "wiki/" -name "*.md" | grep -i "keyword"

# Per contenuto
grep -rl "keyword" "wiki/" --include="*.md"
```

Oppure usare direttamente i tool Grep/Glob sul percorso `wiki/`.

### Create a new note

1. Nome file in **Title Case**
2. Scrivere il contenuto come unità di conoscenza
3. Aggiungere `[[wikilinks]]` alle note correlate in fondo
4. Non sovrascrivere pagine generate dagli agenti (`topics/`, `papers/`,
   `athlete/`) senza motivo: sono rigenerate dalla pipeline

### Find related notes

```bash
grep -rl "\\[\\[Note Title\\]\\]" "wiki/"
```

### Find index notes

```bash
find "wiki/" -iname "*index*"
```
