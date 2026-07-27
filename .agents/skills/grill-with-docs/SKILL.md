---
name: grill-with-docs
description: Intervista rigorosa per chiarire requisiti e design producendo nello stesso tempo glossario di dominio e ADR. Usare quando l'ambiguità riguarda anche terminologia o decisioni architetturali durevoli; annunciare la modalità e ottenere conferma prima di iniziare.
---

# Grilling con documentazione

Annuncia la modalità grilling con documentazione e attendi la conferma dell'utente.

Segui il processo di `grill-me` e usa anche `domain-modeling`. Fai una domanda alla
volta. Quando una decisione si stabilizza:

- aggiorna il glossario/contesto nel `CONTEXT.md` appropriato;
- crea o aggiorna un ADR solo per decisioni architetturali durevoli;
- registra alternative, conseguenze e questioni aperte senza inventare consenso.

Non trasformare appunti provvisori in decisioni definitive. Al termine, riepiloga i
documenti aggiornati e indica se i requisiti sono pronti per `to-spec`.
