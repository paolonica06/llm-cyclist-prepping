# Obiettivo del Piano: target metrico datato, gara-A opzionale

**Status:** accepted

La Fase D introduce un `CoachAgent` che genera un Piano verso un obiettivo
esplicito. Il glossario attuale definisce il Piano come «periodizzazione verso
una gara-A»; tuttavia molti atleti competitivi si allenano verso un target
fisiologico (FTP, VO₂max) senza avere una gara prioritaria imminente, e anche
quando la gara c'è, è il salto metrico — non il piazzamento — la grandezza
che il sistema può misurare e imparare a predire. Decidiamo che il **target
primario del Piano è un obiettivo metrico datato** (`MetricType` + valore
di partenza + valore target + data target), e che la gara-A è opzionale e
corroborante.

## Considered Options

- **Gara-A obbligatoria come finestra temporale** — coerente col glossario
  corrente, ma esclude atleti senza calendario gare definito e rende
  impossibile allenare su target fisiologici puri (es. atleti FTP-driven che
  gareggeranno solo in autunno ma vogliono misurare il progresso ora).
- **Solo gara-A, senza target numerico** — non trendabile: gare diverse non
  sono comparabili; il sistema non può sapere se l'obiettivo è stato
  raggiunto senza una Valutazione esplicita.

## Decision

Il modello `TrainingPlan` aggiunge quattro campi:
`target_metric_type: Optional[MetricType]`,
`target_metric_start: Optional[float]`,
`target_metric_value: Optional[float]`,
`target_metric_date: Optional[str]` (ISO YYYY-MM-DD).

Il CLI accetta `--metric/--to/--by` (e opzionalmente `--from`); se `start`
non è fornito, `CoachAgent` lo ricava dall'ultimo `Assessment` pertinente.
Il campo `target_race_id: Optional[str]` rimane e, se presente, funge da
corroborante: la data della gara può coincidere (o precedere di poco) la
`target_date`, ma non la sostituisce come trigger della periodizzazione.

La periodizzazione è **a ritroso dalla data-obiettivo**: `CoachAgent`
calcola i blocchi partendo dalla `target_date` e costruendo a ritroso
(taper → sviluppo → base), garantendo che la settimana del picco di forma
(TSB alta) cada intorno alla data-obiettivo indipendentemente dalla presenza
di una gara. Se `target_race_id` è valorizzato, `CoachAgent` può allineare
il taper alla data di gara se questa coincide con la `target_date`, oppure
segnalarlo come conflitto nei `notes` del Piano.

Il nuovo modello `MetricGoal(metric_type, target, target_date, start=None)`
è il contratto passato a `CoachAgent.run(...)` dal CLI/API; è costruito da
opzioni esplicite, senza parsing di stringhe libere.

## Consequences

- La voce «Piano» in `CONTEXT.md` va aggiornata: l'obiettivo primario è un
  target metrico datato; la gara-A diventa opzionale/corroborante; la
  periodizzazione è a ritroso dalla data-obiettivo.
- `goal_reached` e `assessment_gap_to_goal` (funzioni pure in
  `athlete_metrics.py`) determinano se il Piano è stato soddisfatto.
- La comparabilità fra Piani diversi dello stesso atleta è possibile solo se
  usano lo stesso `MetricType`; piani su metriche diverse non si sommano.
- Il Progresso (`delta fra Valutazioni`) resta la grandezza primaria; il
  piazzamento in gara non entra nel calcolo.
