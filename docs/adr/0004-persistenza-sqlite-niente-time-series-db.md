# Persistenza su SQLite esteso, niente time-series DB

**Status:** accepted

Le Serie storiche dell'atleta sono dati time-series, per cui verrebbe naturale un database
dedicato (InfluxDB, TimescaleDB). Decidiamo invece di **restare su SQLite** (il DB esistente),
estendendo il pattern già in uso "blob JSON + colonne indicizzate" con nuove tabelle e i
relativi metodi `Database`.

## Considered Options

- **Time-series DB dedicato** — infrastruttura sproporzionata: i volumi mono-atleta sono
  minuscoli (centinaia di righe l'anno) e in Ramo mirror ingeriamo metriche *già calcolate*,
  quindi non serve un motore di aggregazione ad alte prestazioni.

## Consequences

- Coerenza col resto del sistema (stesso pattern di `researches`/`records`).
- Se un domani si passasse a **multi-atleta** o a **serie ad alta frequenza** (stream
  secondo-per-secondo), la scelta andrebbe rivista.
