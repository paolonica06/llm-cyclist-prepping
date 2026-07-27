---
name: to-spec
description: Trasformare requisiti già chiariti e conversazione corrente in una spec o PRD verificabile, senza riaprire un'intervista. Usare quando il cosa è definito e va formalizzato; chiedere conferma prima di pubblicare su tracker o sistemi esterni.
---

# Dalla conversazione alla spec

Non intervistare di nuovo l'utente. Esplora il repository quanto basta per allineare
termini, ADR, vincoli e seam di test esistenti.

Scrivi la spec in `docs/specs/` salvo diversa convenzione del progetto, includendo:

- problema e risultato atteso dal punto di vista dell'utente;
- ambito incluso ed escluso;
- user story e casi limite;
- decisioni già prese, invarianti e dipendenze;
- criteri di accettazione osservabili;
- strategia di test al seam più alto praticabile;
- rischi e questioni realmente ancora aperte.

Usa il vocabolario di `CONTEXT.md` e non inventare decisioni mancanti. La creazione del
file locale è parte della skill; prima di pubblicare su issue tracker, Notion o altri
sistemi esterni, chiedi conferma.
