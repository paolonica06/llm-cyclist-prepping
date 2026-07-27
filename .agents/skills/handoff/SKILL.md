---
name: handoff
description: Compattare la conversazione e lo stato di lavoro in un documento temporaneo che permetta a un nuovo agente o a una nuova sessione di continuare. Usare quando l'utente chiede un handoff, un passaggio di consegne o la chiusura strutturata della sessione; chiedere conferma prima di terminare il flusso corrente.
---

# Handoff

Chiedi conferma prima di chiudere il flusso corrente, salvo richiesta esplicita di
handoff già presente nel messaggio.

Scrivi nella directory temporanea del sistema un documento che includa:

- obiettivo e stato effettivo;
- decisioni e vincoli ancora rilevanti;
- modifiche fatte e verifiche eseguite;
- lavoro residuo, blocchi e prossimo passo concreto;
- skill suggerite per la nuova sessione.

Non duplicare spec, piani, ADR, issue, commit o diff: referenziali con percorso o URL.
Rimuovi credenziali, segreti e dati personali non necessari. Se l'utente specifica lo
scopo della prossima sessione, calibra il documento su quello scopo.
