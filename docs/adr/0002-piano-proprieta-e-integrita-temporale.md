# Il Piano: fonte di verità nostra, versionato e con blocchi eseguiti congelati

**Status:** accepted

Il Piano periodizzato è una previsione che viene riscritta (malattia, Valutazioni basse,
gare che saltano), e su di esso si fondano giudizi *a posteriori* ("questo Blocco ha
funzionato?"). Decidiamo che il sistema è la **fonte di verità** del Piano e lo **spinge su
intervals.icu** per l'esecuzione (leggendo indietro la Compliance); che il Piano è
**versionato/append-only**; e che i **Blocchi eseguiti sono congelati**, con *pianificato*
ed *eseguito* tenuti distinti.

## Considered Options

- **Piano mutabile in-place** — semplice, ma distrugge la provenienza: la memoria di
  Trasferibilità personalizzata punterebbe a uno stato sovrascritto e diventerebbe *una
  bugia archiviata*.
- **Solo nel nostro DB, senza push** — perde l'esecuzione della seduta sul dispositivo e la
  lettura automatica dell'aderenza.

## Consequences

- Più scrittura: versioni con validità temporale e snapshot immutabili dei Blocchi eseguiti.
- Va gestita una **sincronizzazione bidirezionale** con intervals.icu (push del pianificato,
  pull dell'eseguito).
- Ogni giudizio sul passato si àncora agli snapshot congelati, mai allo stato corrente
  (invariante di integrità temporale).
