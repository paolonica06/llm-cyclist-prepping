# Contesto: Atleta longitudinale

Il linguaggio con cui il sistema modella un singolo ciclista **nel tempo** — le sue
misure, le gare, il piano di allenamento e la memoria di ciò che ha funzionato — e il
suo confine con la pipeline di evidenze scientifiche. Copre la Fase B (vedi il PRD in
`docs/specs/fase-b-atleta-longitudinale.md`). Il linguaggio della pipeline bibliografica
vive già nel codice; qui compaiono solo i termini che l'atleta longitudinale attraversa
al confine. *(Se un domani la pipeline evidenze avrà un proprio glossario, si introdurrà
un `CONTEXT-MAP.md`; per ora un solo contesto.)*

## Language

### Atleta e misure

**Atleta**:
Il singolo ciclista tracciato dal sistema (il modello è mono-atleta), con identità
persistente. Le grandezze che variano nel tempo non gli appartengono come valori fissi:
vivono nelle Serie storiche.
_Avoid_: utente, profilo (il "profilo" è solo la parte anagrafica/qualitativa)

**Serie storica**:
Sequenza datata di misure di *una singola* grandezza dell'atleta; ogni grandezza
(Wellness, fitness CTL/ATL/TSB, FTP, Curva di potenza) è una serie a sé. È la fonte di
verità per tutto ciò che cambia nel tempo.
_Avoid_: storico, timeline

**Wellness**:
Le misure giornaliere di stato di recupero: sonno, HRV, peso, frequenza cardiaca a riposo.
_Avoid_: readiness (è l'*uso* che se ne fa, non il dato)

**Readiness**:
La prontezza dell'atleta al mattino, dedotta dalla Wellness recente (sonno, HRV) e dal
carico, che orienta la scelta della Seduta del giorno.
_Avoid_: forma (è la TSB), prontezza (informale)

**Attività**:
Una singola uscita registrata (data, durata, carico, tipo), conservata come riassunto e
ingerita dalla Piattaforma esterna.
_Avoid_: uscita, allenamento (per il dato registrato), ride

**CTL** (Chronic Training Load):
Media esponenziale a lungo termine del carico giornaliero (~42 giorni); proxy della
*fitness*. Sale durante i blocchi di accumulo.
_Avoid_: fitness (come sinonimo intercambiabile)

**ATL** (Acute Training Load):
Media esponenziale a breve termine del carico (~7 giorni); proxy della *fatica*.
_Avoid_: fatica (come sinonimo intercambiabile)

**TSB** (Training Stress Balance):
Freschezza, pari a CTL − ATL. Negativa durante l'accumulo, alta solo in taper e in gara.
Non è una grandezza da massimizzare: segue la Fase.
_Avoid_: forma, form, freschezza (come sinonimi intercambiabili)

**Curva di potenza**:
La miglior potenza media sostenibile per ciascuna durata (es. 5s, 1′, 5′, 20′, 60′),
fotografata a date successive.
_Avoid_: MMP, power profile, record di potenza

**FTP**:
La potenza alla soglia funzionale, storicizzata nel tempo: il passato va letto con l'FTP
di allora, non con quello di oggi.
_Avoid_: soglia (da sola è ambigua), threshold

**VO₂max**:
Il massimo consumo di ossigeno dell'atleta (ml·kg⁻¹·min⁻¹); uno dei protocolli di
Valutazione. Da non confondere con la potenza aerobica massimale.
_Avoid_: VO2 max, capacità aerobica (informale)

### Obiettivi e misura del progresso

**Gara**:
Evento con data e priorità A/B/C: la gara-**A** è l'obiettivo primario attorno cui si
periodizza, **B**/**C** sono intermedie o allenanti. Il suo esito è contesto qualitativo,
non una metrica di progresso (gare diverse non sono comparabili tra loro).
_Avoid_: evento, competizione; "risultato" inteso come metrica trendabile

**Valutazione**:
Il **punto di misura primario del Progresso**: una misura programmata e ripetibile della
performance o fisiologia (prova FTP, ramp/MAP, VO₂max), con una data pianificata e una
eseguita.
_Avoid_: **test** (in questo repo "test" = test software/pytest), prova, assessment

**Progresso**:
Il miglioramento misurato come *delta fra Valutazioni* nel tempo, non come piazzamento
in gara.
_Avoid_: miglioramento (generico), risultato

### Piano

**Piano**:
La periodizzazione verso una gara-A, articolata in Macrociclo → Blocco → Microciclo →
Seduta → Intervallo. Il sistema ne è la fonte di verità e lo rispecchia sulla piattaforma
esterna per l'esecuzione.
_Avoid_: programma, scheda

**Macrociclo**:
Il periodo più lungo della periodizzazione — l'intera stagione o una sua grande fase —
articolato in Blocchi.
_Avoid_: stagione (informale)

**Blocco**:
Un mesociclo di alcune settimane con uno **scopo fisiologico unico** (es. sviluppo della
VO₂max, della soglia, della base aerobica). È il livello a cui si agganciano l'Evidenza
verificata e la Trasferibilità personalizzata.
_Avoid_: mesociclo (usare "blocco"), fase

**Microciclo**:
La settimana di Sedute, l'unità tattica più breve della periodizzazione.
_Avoid_: settimana (informale)

**Seduta**:
Una singola sessione di allenamento, in una data, composta da uno o più Intervalli.
_Avoid_: workout, sessione (informale)

**Intervallo**:
L'unità atomica di una Seduta: uno sforzo a durata e intensità definite (target al watt).
_Avoid_: ripetuta, rep

**Fase** (di periodizzazione):
Il periodo e l'intento di una parte della stagione — base (accumulo), build (adattamento
specifico), peak (affinamento), taper (scarico pre-gara) — che detta l'andamento atteso
di CTL e TSB. Non è sinonimo di Blocco.
_Avoid_: periodo, blocco

**Prescrizione**:
Ciò che il Piano prescrive (una Seduta o un Intervallo) con il target al watt, marcata
**supportata** o **non supportata** a seconda che un'Evidenza verificata la sostenga.
_Avoid_: workout, target

**Pianificato / Eseguito**:
Il *pianificato* è ciò che il Piano prevede; l'*eseguito* è ciò che è realmente avvenuto,
ricostruito dalle Attività reali. I giudizi sul passato usano l'eseguito.
_Avoid_: previsto/effettivo, planned/actual

**Compliance**:
Il grado di aderenza fra pianificato ed eseguito, per Seduta o per Blocco.
_Avoid_: aderenza (informale), adherence

**Congelamento**:
Lo stato immutabile di un Blocco una volta eseguito: i suoi contenuti (target, tempi,
Citazioni) e l'FTP del tempo restano fotografati, così che i giudizi sul passato non
cambino se il Piano viene poi riscritto.
_Avoid_: snapshot (da solo), freeze, versione

### Evidenza e apprendimento

**Evidenza verificata**:
Un lavoro scientifico che ha superato il controllo d'integrità (identificatori risolti e
concordi, metadati consistenti, nessuna contraddizione critica). *Solo* questa è citabile
in un Piano.
_Avoid_: paper, studio, fonte (quando si intende specificamente il verificato)

**Citazione**:
Il legame fra un Blocco e l'Evidenza verificata che lo giustifica. È congelata (fotografia
dei dati essenziali della fonte) e conserva un riferimento al record originale per
consultazione.
_Avoid_: riferimento (da solo), link

**Trasferibilità dello studio**:
Quanto i risultati di uno studio si applicano ai ciclisti competitivi *in generale* — una
proprietà *dello studio*. (Già presente nel modello esistente come dimensione della qualità.)
_Avoid_: applicabilità

**Trasferibilità personalizzata**:
Il verdetto se l'approccio di un Blocco (giustificato da certe Citazioni) ha prodotto il
Progresso atteso *per questo atleta*, misurato via delta delle Valutazioni e sempre
accompagnato da confidenza e Confounder. Concetto **distinto** dalla Trasferibilità dello
studio.
_Avoid_: trasferibilità (da sola è ambigua), efficacia

**Confounder**:
Un fattore esterno all'allenamento (sonno scarso, stress, malattia, Blocco accorciato) che
può spiegare un cambiamento nelle Valutazioni e va esplicitato come caveat nella
Trasferibilità personalizzata.
_Avoid_: variabile confondente (usare "confounder"), rumore

### Retrieval (interrogazione del corpus)

**Retriever**:
Il "bibliotecario": data un'interrogazione e l'Atleta, restituisce i migliori studi
dell'Evidenza verificata, ordinati per Pertinenza, qualità e adattamento all'atleta. È
deterministico e **non scrive** la risposta (quella è generazione, a valle).
_Avoid_: ricerca (la "ricerca"/`Research` è l'interrogazione delle banche dati esterne, un'altra cosa), search engine

**Pozzo**:
L'insieme **unico** di tutte le Evidenze verificate attraverso *tutti* i temi, deduplicato
per identità di paper. Il Retriever cerca qui, non dentro le singole pagine-tema (che
restano artefatti sfogliabili).
_Avoid_: indice, database (è una vista logica, non una struttura di memorizzazione)

**Pertinenza**:
Quanto uno studio combacia lessicalmente con l'interrogazione (con espansione dei sinonimi
di dominio). È il criterio **primario**: uno studio fuori tema non emerge, per quanto di
qualità ("in-tema-prima").
_Avoid_: rilevanza (usare "pertinenza"), match

**Direzione dell'evidenza**:
Il verso del risultato di uno studio rispetto a un esito: *a favore*, *nullo*, *contrario*
o *misto*. Già classificata in sintesi.
_Avoid_: esito (è la grandezza), effetto

**Conflict-aware**:
Proprietà dell'output del Retriever: rappresenta **entrambe le Direzioni** dell'evidenza
(la più forte a favore *e* la più forte contro/nulla), non solo gli studi col punteggio più
alto — così i conflitti restano visibili e non si fa cherry-picking. È l'applicazione al
retrieval del principio "conflitti conservati, non riconciliati".
_Avoid_: bilanciato (non è simmetria forzata), imparziale

### Ingestione

**Morning sync**:
La sincronizzazione quotidiana (di norma mattutina, readiness-driven) dalla Piattaforma
esterna: aggiorna la Wellness recente e le Attività eseguite. È idempotente.
_Avoid_: import, fetch, sync (generico)

**Ramo mirror**:
La strategia per cui le metriche derivate (CTL/ATL/TSB, Curva di potenza) sono assunte
*già calcolate* dalla Piattaforma esterna come fonte di verità.
_Avoid_: mirror (da solo), replica

**Piattaforma esterna**:
Il servizio di analisi dell'allenamento che aggrega i dati dell'atleta dalle varie sorgenti
(dispositivo, Strava, Garmin) e fa da hub autoritativo da cui il sistema ingerisce.
[Attualmente: intervals.icu — vedi `docs/adr/0001`.]
_Avoid_: sorgente, provider
