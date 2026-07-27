# AGENTS.md

Istruzioni persistenti per Codex in questo repository.

## Fonti operative

- Prima di lavorare, leggi per intero `CLAUDE.md`: le regole di progetto, il protocollo
  coaching, i comandi, l'architettura e i vincoli descritti lì valgono anche per Codex.
- Per il routing delle skill e i gate tra fasi, usa anche `docs/AGENT_WORKFLOW.md`.
- Se una personalizzazione condivisa cambia, mantieni allineati `CLAUDE.md`, questo file,
  `.claude/skills/` e `.agents/skills/`. Le istruzioni specifiche per Codex in questo file
  prevalgono solo quando le superfici dei due agenti differiscono.

## Protocollo atleta vincolante

Per qualsiasi domanda decisionale di Paolo (`athlete_id=i215294`) su allenamento,
recupero, gara o stato di forma, non rispondere dal solo piano o per buon senso.
Applica nell'ordine il protocollo completo di `CLAUDE.md`:

1. trend misurati degli ultimi ~14 giorni da `data/kb.sqlite3`;
2. calendario reale (`planned_workouts` + `races`) confrontato con `activities`;
3. evidenza verificata pertinente in `wiki/topics/`, con confidenza e caveat;
4. storico completo e watchlist boom-bust/ramp-dig;
5. report strategici e piano atleta.

Verifica sempre nel DB baseline e soglie prima di citarle. Distingui «obbligato dai
dati» da «scelta migliore» e marca le affermazioni come `studi`, `dati_atleta` o
`euristica`. Se i dati contraddicono una risposta precedente, correggila esplicitamente.
Sintomi o sospetto RED-S richiedono stop e professionista.

Prima di creare o modificare un piano, leggi il calendario intervals.icu già ingerito:
qui si fa pull/mirror, mai push cieco sopra un piano esistente. Verifica volume reale e
gare; se una gara manca, chiedi data, tipo, priorità e percorso.

## Protocollo salute mentale e privacy

Il repository remoto e `wiki/` sono pubblici: pubblica soltanto evidenza generale e
sintesi anonime. Dati personali, check-in, sintomi e screening di Paolo vivono solo in
`data/private/mental-health/`, ignorato da Git; non copiarli in wiki, commit, issue, log,
report versionati o ricerche bibliografiche.

Tratta i check-in 0–10 come segnali non clinici e longitudinali, mai come diagnosi o gate
automatico di allenamento. Uno screening positivo richiede contesto e, quando indicato,
valutazione professionale; non somministrare o interpretare strumenti riservati ai
sanitari come IOC SMHAT2 (successore di SMHAT-1). Sintomi persistenti, compromissione,
disturbi alimentari/RED-S, ansia/depressione clinica o dipendenze sospette richiedono
professionista. Rischio di autolesionismo/suicidio, psicosi o grave compromissione
richiedono stop del coaching adattivo e assistenza urgente. Registra consenso e revoca
soltanto nel percorso privato.

## Routing autonomo delle skill

Scegli proattivamente la skill in base all'intento, senza aspettare che l'utente ne
ricordi il nome. Le skill locali Codex sono in `.agents/skills/`; PDF e scoperta skill
usano le skill native già installate.

- requisiti vaghi/design da affinare: `grill-me`, oppure `grill-with-docs` se servono
  anche glossario e ADR;
- requisiti chiari da formalizzare: `to-spec`;
- terminologia o decisioni di dominio: `domain-modeling`;
- task multi-step: `writing-plans`; piano scritto da eseguire: `executing-plans`;
- feature o bugfix: `test-driven-development`;
- bug, test rossi o comportamento inatteso: `systematic-debugging`;
- prima di dichiarare completato: `verification-before-completion`;
- feature completata o pre-merge: `requesting-code-review`, poi
  `receiving-code-review`;
- ricerca esplorativa: `ai-research-explore`; dettaglio puntuale di un paper:
  `paper-context-resolver`;
- note della wiki: `obsidian-vault`;
- chiusura/passaggio di consegne: `handoff`;
- domanda «esiste una skill per...?» : `find-skills`.

Chiedi conferma prima di avviare grilling, handoff, pubblicazione di una spec su tracker
o `ai-research-explore`. Annuncia l'uso della skill richiesta. Non combinare skill
alternative o fasi dipendenti in parallelo: intervista → spec → piano → esecuzione;
requesting review → receiving review.

## Disciplina di implementazione

- Feature, bugfix e cambi di comportamento: test prima, osservarlo fallire, poi modifica
  minima e test verde. Per una pura configurazione/documentazione, usa una verifica
  strutturale equivalente.
- Per i bug trova la causa radice prima del fix.
- Non dichiarare «fatto», «risolto» o «passa» senza una verifica fresca e leggibile.
- Usa i comandi e i vincoli architetturali documentati in `CLAUDE.md`.
- Dopo `research reassess`, controlla nel DB `screening.assessed_by`,
  `extraction.extracted_by` e `quality.assessed_by`; riesegui i topic con fallback
  euristici finché il corpus richiesto è uniforme.

## Git e sicurezza

L'utente autorizza commit ai milestone verificati e push normali senza una richiesta
ripetuta. Usa messaggi di commit in italiano e non inventare trailer di attribuzione.
Non pubblicare bozze o modifiche non verificate.

Sono vietati senza conferma esplicita: force-push, `reset --hard`, `git clean -f/-fd`,
`branch -D`, `checkout .` e `restore .`. L'hook Codex in `.codex/hooks.json` applica
questo guardrail alle shell call; trattalo come difesa aggiuntiva, non come unica
protezione.

Quando usi agenti paralleli, limita il fan-out a sottotask davvero indipendenti e usa il
modello più efficiente disponibile per il tipo di lavoro; riserva il ragionamento più
costoso ai punti di sintesi o architettura.

## Relazione con EatYourCarbs

Se il task riguarda l'integrazione nutrizione, `llm_cyclist` è il blueprint N=1 e
EatYourCarbs è l'app multi-tenant autonoma. I corpora non si mescolano; l'unico ponte
runtime previsto esporta verso questo progetto segnali energetici neutri, Paolo-only,
opzionali e spenti di default. Prima di cambiare quel confine, leggi
`~/Documents/EatYourCarbs/docs/NUTRITION_INTELLIGENCE_SPEC.md` e la policy atleta di EYC.
