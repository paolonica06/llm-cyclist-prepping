# Ingestione dei dati atleta: un solo connettore (intervals.icu), in ramo mirror

**Status:** accepted

L'atleta usa intervals.icu, che sta *a valle* di Strava/Garmin (li aggrega, insieme ai
file `.fit`) e calcola già CTL/ATL/TSB e la curva di potenza. Decidiamo di ingerire i dati
dell'atleta da **un solo connettore, intervals.icu**, in **ramo mirror** — le metriche
derivate sono ingerite *già calcolate*, non ricalcolate dal sistema — tramite un **morning
sync** idempotente.

## Considered Options

- **Ricalcolare le metriche in casa** — richiederebbe una serie giornaliera densa *senza
  buchi* e lo storico FTP per ricalcolare correttamente il carico del passato (il TSS di
  un'uscita del 2024 va calcolato con l'FTP di allora). Sproporzionato.
- **Connettere Strava/Garmin/`.fit` direttamente** — darebbe gli *stessi* dati due volte
  (sono a monte di intervals.icu) e un problema di dedup evitabile.

## Consequences

- Siamo accoppiati alle definizioni di intervals.icu (time-constant di CTL/ATL, zone): sono
  la nostra verità sui dati derivati.
- Un atleta che *non* usa intervals.icu non è supportato.
- È una **deviazione consapevole** dal ROADMAP, che per la Fase B citava anche `.fit`/CSV,
  Strava e Garmin. L'aggiunta di altri connettori in futuro resta possibile ed è additiva.
