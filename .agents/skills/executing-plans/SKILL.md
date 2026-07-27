---
name: executing-plans
description: Eseguire un piano di implementazione già scritto, con revisione iniziale, avanzamento per task, test, checkpoint e verifica finale. Usare quando l'utente chiede di implementare o continuare un piano presente nel repository.
---

# Esecuzione di un piano

Annuncia che stai usando `executing-plans`.

1. Leggi tutto il piano e i file di contesto che cita.
2. Confrontalo con lo stato corrente del repository e segnala subito solo i blocchi o le
   incongruenze che cambiano materialmente l'esecuzione.
3. Trasforma i task del piano in una lista di avanzamento; mantieni un solo task attivo.
4. Per ogni task:
   - applica TDD quando cambia comportamento;
   - implementa il minimo necessario;
   - esegui le verifiche previste;
   - aggiorna lo stato solo dopo evidenza positiva.
5. Usa agenti paralleli soltanto per sottotask indipendenti e con confini chiari.
6. Prima di chiudere, usa `verification-before-completion`; per feature sostanziali usa
   anche `requesting-code-review` e valuta il feedback con `receiving-code-review`.

Non dichiarare completo un piano parzialmente eseguito. Se una scelta dell'utente è
indispensabile, consegna stato, evidenza e domanda precisa.
