"""Client intervals.icu — ingestione dei dati atleta (Fase B).

A differenza dei client bibliografici, **non** restituisce `PaperRecord`: produce
modelli-atleta (serie storiche, attività). Riusa `HttpFetcher` (retry/backoff) e
**degrada a liste vuote** quando manca la key o si è offline — mai un'eccezione.

Auth: HTTP Basic con username `API_KEY` e password = `KB_INTERVALS_ICU_API_KEY`.

NB (verifica live): i nomi dei campi dell'endpoint `/wellness` e `/activities`
(`ctl`, `atl`, `form`, `restingHR`, `hrv`, `weight`, `sleepSecs`,
`icu_training_load`, `icu_intensity`, `start_date_local`) seguono l'API pubblica
di intervals.icu e vanno confermati con una chiamata reale (serve la key).
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from ..athlete_models import (ActivitySummary, MetricType, Race, RacePriority,
                              TimeseriesPoint, make_activity_id, make_race_id)
from ..config import get_settings
from .base import HttpFetcher, WriteResult

BASE = "https://intervals.icu/api/v1"

# Curva di potenza: periodi richiesti (recenti → assoluti) e tipi di attività.
# `type` accetta un solo valore per chiamata, quindi outdoor+indoor = due chiamate.
POWER_CURVE_WINDOWS = "42d,90d,365d,all"
POWER_CURVE_TYPES = ("Ride", "VirtualRide")

# Categoria evento intervals.icu → priorità gara. Le gare vivono sul CALENDARIO
# (/events), non su /activities: senza ingerirle il sistema pianifica alla cieca.
_RACE_CATEGORY = {
    "RACE_A": RacePriority.A,
    "RACE_B": RacePriority.B,
    "RACE_C": RacePriority.C,
}

# Campo dell'endpoint wellness → nostra grandezza (MetricType).
# `readiness`/`rampRate`/`vo2max` sono esposti dal payload /wellness ma erano
# dichiarati nel modello senza essere ingeriti: raccolti dal loop generico di
# `_parse_daily` come le altre grandezze (nessun parsing dedicato necessario).
_WELLNESS_FIELDS = {
    "sleepSecs": MetricType.SLEEP,
    "hrv": MetricType.HRV,
    "weight": MetricType.WEIGHT,
    "restingHR": MetricType.RESTING_HR,
    "readiness": MetricType.READINESS,
    "rampRate": MetricType.RAMP_RATE,
    "vo2max": MetricType.VO2MAX,
}
_FITNESS_FIELDS = {
    "ctl": MetricType.CTL,
    "atl": MetricType.ATL,
}
# NB: l'endpoint /wellness NON espone la TSB ("form" non esiste nel payload).
# La TSB è l'identità aritmetica CTL - ATL (così la calcola intervals.icu per la
# "Form") — derivarla NON viola il ramo mirror: non è un ricalcolo con costanti
# di tempo, è la definizione applicata ai valori già ingeriti. Vedi _parse_daily.


class IntervalsClient:
    source = "intervals_icu"

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        self._fetcher = fetcher
        self._api_key = get_settings().intervals_icu_api_key

    @property
    def available(self) -> bool:
        return bool(self._api_key) and not get_settings().force_offline

    def _auth_headers(self) -> Dict[str, str]:
        token = base64.b64encode(f"API_KEY:{self._api_key}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        if not self.available:
            return None
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            return await fetcher.get_json(f"{BASE}{path}", params=params,
                                          headers=self._auth_headers())
        finally:
            if own:
                await fetcher.__aexit__()

    async def fetch_daily(self, athlete_id: str, oldest: Optional[str] = None,
                          newest: Optional[str] = None) -> List[TimeseriesPoint]:
        """Serie giornaliere wellness + fitness (CTL/ATL/TSB) dall'endpoint /wellness."""
        params: Dict[str, Any] = {}
        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest
        data = await self._get(f"/athlete/{athlete_id}/wellness", params or None)
        return _parse_daily(athlete_id, data)

    async def fetch_activities(self, athlete_id: str, oldest: Optional[str] = None,
                               newest: Optional[str] = None) -> List[ActivitySummary]:
        """Riassunti delle attività (no stream grezzi)."""
        params: Dict[str, Any] = {}
        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest
        data = await self._get(f"/athlete/{athlete_id}/activities", params or None)
        return _parse_activities(athlete_id, data)

    async def fetch_power_curve(
        self, athlete_id: str,
        windows: str = POWER_CURVE_WINDOWS,
        sport: str = "Ride",
    ) -> List[TimeseriesPoint]:
        """Curva di potenza mean-max **già calcolata** da intervals.icu (ramo mirror).

        Endpoint `/athlete/{id}/power-curves` → `{list: [curva...], activities: {...}}`.
        NON scarichiamo i watt grezzi né ricalcoliamo mean-max in casa (ADR-0001): la
        curva è una metrica derivata che la piattaforma calcola a monte.

        - **Periodi** (`windows`, es. "42d,90d,365d,all"): l'endpoint torna una curva per
          spec, così distinguiamo i best **recenti** ("42 days") dagli **assoluti**
          ("All time", che parte dal 1986).
        - **Sport, non tipo**: verificato dal vivo che `type` raggruppa per *sport* —
          `Ride`/`VirtualRide` restituiscono la **stessa** curva cycling, che **già
          combina indoor + outdoor**. Non esiste una curva outdoor-only vs indoor-only,
          quindi una sola chiamata (`sport="Ride"`) è sufficiente e completa.

        Ritorna `[point]` (un solo punto POWER_CURVE, come lista per uniformità col
        morning sync) oppure `[]` (offline/no-key/nessun dato).
        """
        data = await self._get(
            f"/athlete/{athlete_id}/power-curves", {"type": sport, "curves": windows})
        periods = _parse_power_curve_list(data)
        point = _build_power_curve_point(athlete_id, periods)
        return [point] if point else []

    async def fetch_events(self, athlete_id: str, oldest: Optional[str] = None,
                           newest: Optional[str] = None):
        """Ingesta il **calendario** intervals.icu (`/events`): gare + pianificato.

        Il calendario è la fonte di verità di intervals.icu per ciò che è *programmato*
        (gare `RACE_*`, allenamenti `WORKOUT` con watt/target). Non ingerirlo è la causa
        del "pianificare alla cieca": gare e piano non stanno in `/activities`.

        Ritorna `(races, planned)` dove `races` sono `Race` e `planned` sono dict
        leggeri dei workout programmati. Offline/no-key → `([], [])`.
        """
        params: Dict[str, Any] = {}
        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest
        data = await self._get(f"/athlete/{athlete_id}/events", params or None)
        return _parse_events(athlete_id, data)

    async def fetch_activity_power_curve(self, activity_external_id: str) -> Optional[Dict[str, Any]]:
        """Curva mean-max della **singola** attività (già calcolata da intervals.icu).

        Endpoint `/activity/{id}/power-curve` → `{secs, values, watts_per_kg, ...}`.
        `None` se offline/no-key o se l'attività non ha potenza (nessun power meter).
        """
        data = await self._get(f"/activity/{activity_external_id}/power-curve")
        return _parse_activity_power_curve(data)

    async def fetch_activity_intervals(self, activity_external_id: str) -> Optional[List[Dict[str, Any]]]:
        """Lap/intervalli auto-rilevati di una singola attività (segmentati da intervals.icu).

        Endpoint `/activity/{id}/intervals` → `{icu_intervals: [...]}`. A differenza
        della curva mean-max, il dato è per-blocco: permette di verificare se un
        allenamento strutturato (es. 3×15' a target) è stato eseguito alla potenza
        prescritta blocco per blocco, non solo in media sull'intera uscita.
        `None` se offline/no-key o nessun intervallo rilevato.
        """
        data = await self._get(f"/activity/{activity_external_id}/intervals")
        return _parse_activity_intervals(data)

    async def fetch_activity_streams(
        self, activity_external_id: str,
        types: str = "watts,heartrate,time",
    ) -> Optional[Dict[str, List[Any]]]:
        """Stream raw secondo-per-secondo (potenza/HR/tempo) di una singola attività.

        Endpoint `/activity/{id}/streams` → lista di `{type, data}`. A differenza di
        curva mean-max (miglior potenza per durata) e lap (aggregato per blocco), qui
        il dato è punto-per-punto: l'unico modo per vedere come si è distribuito lo
        sforzo DENTRO un singolo intervallo (es. pacing in crescendo/calo entro un
        test massimale). Non persistito su DB (volume pesante, ~1 punto/sec): fetch
        on-demand per analisi puntuali, non backfill storico.
        """
        data = await self._get(f"/activity/{activity_external_id}/streams",
                               {"types": types})
        return _parse_activity_streams(data)

    # --- Scrittura ----------------------------------------------------------------
    # Il progetto tratta intervals.icu come sorgente di verità in *lettura*: il
    # calendario lo scrive l'atleta. `update_event`/`create_event` esistono solo per
    # applicare una decisione ESPLICITA e già concordata con l'atleta (mai
    # pianificazione automatica silenziosa) — chi chiama deve aver mostrato il
    # diff/piano prima di scrivere. Nessun metodo di delete: aggiungerlo richiede
    # una decisione esplicita, non è una dimenticanza.

    async def update_event(self, athlete_id: str, event_id: int | str,
                           patch: Dict[str, Any]) -> WriteResult:
        """PUT parziale su `/athlete/{id}/events/{eventId}`.

        `patch` contiene solo i campi da cambiare (es. `name`, `description`,
        `moving_time`). Passando una `description` con i passi del workout,
        intervals.icu ri-genera lato server il `workout_doc`: non lo costruiamo noi.
        """
        if not self.available:
            return WriteResult(ok=False, status=None, body=None,
                               error="client non disponibile (offline o key mancante)")
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            return await fetcher.send_json(
                "PUT", f"{BASE}/athlete/{athlete_id}/events/{event_id}",
                payload=patch, headers=self._auth_headers())
        finally:
            if own:
                await fetcher.__aexit__()

    async def create_event(self, athlete_id: str, event: Dict[str, Any]) -> WriteResult:
        """POST di un evento NUOVO su `/athlete/{id}/events`.

        `event` tipicamente include `category` (es. "WORKOUT"), `start_date_local`,
        `type`, `name`, `description`, `moving_time`. A differenza di `update_event`
        aggiunge una entry al calendario invece di modificarne una esistente: usarlo
        solo quando l'atleta ha esplicitamente chiesto una nuova sessione, mai per
        pianificare interi microcicli senza conferma puntuale.
        """
        if not self.available:
            return WriteResult(ok=False, status=None, body=None,
                               error="client non disponibile (offline o key mancante)")
        own = self._fetcher is None
        fetcher = self._fetcher or HttpFetcher()
        if own:
            await fetcher.__aenter__()
        try:
            return await fetcher.send_json(
                "POST", f"{BASE}/athlete/{athlete_id}/events",
                payload=event, headers=self._auth_headers())
        finally:
            if own:
                await fetcher.__aexit__()


def _date_of(rec: dict) -> Optional[str]:
    d = rec.get("id") or rec.get("date")          # nel wellness il campo 'id' è la data
    return str(d)[:10] if d else None


def _parse_daily(athlete_id: str, data: Any) -> List[TimeseriesPoint]:
    if not data:
        return []
    points: List[TimeseriesPoint] = []
    fields = {**_WELLNESS_FIELDS, **_FITNESS_FIELDS}
    for rec in data:
        date = _date_of(rec)
        if not date:
            continue
        for field, metric in fields.items():
            val = rec.get(field)
            if val is None:
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue
            points.append(TimeseriesPoint(athlete_id=athlete_id, metric_type=metric,
                                          date=date, value=fval, source="intervals_icu"))
        # TSB = CTL - ATL (identità: l'API non espone la "form"). Solo se entrambi presenti.
        ctl, atl = rec.get("ctl"), rec.get("atl")
        if ctl is not None and atl is not None:
            try:
                points.append(TimeseriesPoint(
                    athlete_id=athlete_id, metric_type=MetricType.TSB, date=date,
                    value=float(ctl) - float(atl), source="intervals_icu"))
            except (TypeError, ValueError):
                pass
    return points


def _parse_power_curve_list(data: Any) -> Dict[str, Dict[str, Any]]:
    """Normalizza il payload di /power-curves in `{label_periodo: curva}`.

    Ogni curva porta `secs` (durate) e `values` (best watt per durata), più
    `watts_per_kg`. Le impacchettiamo per label di periodo ("42 days"… "All time"),
    con `secs_watts` durata→watt (stringa, coerente con l'esempio del modello) e i
    metadati del periodo. Curve senza dati utili vengono scartate.
    """
    lst = data.get("list") if isinstance(data, dict) else data
    if not lst:
        return {}
    curves: Dict[str, Dict[str, Any]] = {}
    for curve in lst:
        if not isinstance(curve, dict):
            continue
        secs = curve.get("secs") or []
        values = curve.get("values") or []
        secs_watts = {str(s): v for s, v in zip(secs, values) if v is not None}
        if not secs_watts:
            continue
        label = curve.get("label") or str(curve.get("days") or len(curves))
        entry: Dict[str, Any] = {
            "start": curve.get("start_date_local"),
            "end": curve.get("end_date_local"),
            "days": curve.get("days"),
            "secs_watts": secs_watts,
        }
        wkg = curve.get("watts_per_kg") or []
        wkg_map = {str(s): w for s, w in zip(secs, wkg) if w is not None}
        if wkg_map:
            entry["watts_per_kg"] = wkg_map
        curves[label] = entry
    return curves


def _build_power_curve_point(
    athlete_id: str, periods: Dict[str, Dict[str, Any]]
) -> Optional[TimeseriesPoint]:
    """Impacchetta i periodi in **un unico** punto POWER_CURVE datato "as-of".

    `periods` = `{label_periodo: curva}` (curva cycling combinata indoor+outdoor). Un
    solo punto al giorno evita la collisione sulla chiave serie `(atleta, power_curve,
    data)` quando più periodi finiscono lo stesso giorno. La data è la fine periodo più
    recente vista.
    """
    if not periods:
        return None
    as_of = ""
    for entry in periods.values():
        end = str(entry.get("end") or "")[:10]
        if end > as_of:
            as_of = end
    if not as_of:
        return None
    return TimeseriesPoint(
        athlete_id=athlete_id, metric_type=MetricType.POWER_CURVE, date=as_of,
        value=None, source="intervals_icu",
        extra={"as_of": as_of, "periods": periods,
               "note": "curva cycling combinata (Ride + VirtualRide indoor)"})


def _parse_events(athlete_id: str, data: Any):
    """Divide gli eventi del calendario in gare (`Race`) e workout pianificati (dict).

    Categorie `RACE_A/B/C` → `Race` con priorità; `WORKOUT` → dict leggero (data,
    nome, tipo, target di carico/tempo, descrizione). Altre categorie (NOTE, ecc.)
    ignorate. Eventi senza data scartati.
    """
    races: List[Race] = []
    planned: List[Dict[str, Any]] = []
    if not data:
        return races, planned
    for ev in data:
        if not isinstance(ev, dict):
            continue
        date = str(ev.get("start_date_local") or "")[:10]
        if not date:
            continue
        cat = ev.get("category")
        name = ev.get("name")
        if cat in _RACE_CATEGORY:
            races.append(Race(
                id=make_race_id(athlete_id, name or cat, date),
                athlete_id=athlete_id, name=name or "Gara", date=date,
                priority=_RACE_CATEGORY[cat], discipline="strada",
                role="allenante" if cat == "RACE_C" else None,
                notes=ev.get("description")))
        elif cat == "WORKOUT":
            planned.append({
                "external_id": str(ev.get("id")) if ev.get("id") is not None else None,
                "date": date,
                "name": name,
                "type": ev.get("type"),
                "category": cat,
                "load_target": ev.get("load_target"),
                "moving_time_s": ev.get("moving_time"),
                "indoor": ev.get("indoor"),
                "description": ev.get("description"),
            })
    return races, planned


def _parse_activity_power_curve(data: Any) -> Optional[Dict[str, Any]]:
    """Curva mean-max di una singola attività → `{secs_watts, watts_per_kg}` o None."""
    if not isinstance(data, dict):
        return None
    secs = data.get("secs") or []
    values = data.get("values") or []
    secs_watts = {str(s): v for s, v in zip(secs, values) if v is not None}
    if not secs_watts:
        return None
    out: Dict[str, Any] = {"secs_watts": secs_watts}
    wkg = data.get("watts_per_kg") or []
    wkg_map = {str(s): w for s, w in zip(secs, wkg) if w is not None}
    if wkg_map:
        out["watts_per_kg"] = wkg_map
    return out


def _parse_activity_intervals(data: Any) -> Optional[List[Dict[str, Any]]]:
    """Lap auto-rilevati di una attività → lista di blocchi normalizzati o None."""
    if not isinstance(data, dict):
        return None
    raw = data.get("icu_intervals") or []
    if not raw:
        return None
    laps: List[Dict[str, Any]] = []
    for i, lap in enumerate(raw):
        laps.append({
            "index": i,
            "type": lap.get("type"),
            "label": lap.get("label"),
            "start_time": lap.get("start_time"),
            "end_time": lap.get("end_time"),
            "duration_s": lap.get("moving_time"),
            "avg_watts": lap.get("average_watts"),
            "weighted_avg_watts": lap.get("weighted_average_watts"),
            "max_watts": lap.get("max_watts"),
            "avg_hr": lap.get("average_heartrate"),
            "max_hr": lap.get("max_heartrate"),
            "avg_cadence": lap.get("average_cadence"),
            "intensity": lap.get("intensity"),
            "training_load": lap.get("training_load"),
            "zone": lap.get("zone"),
        })
    return laps


def _parse_activity_streams(data: Any) -> Optional[Dict[str, List[Any]]]:
    """Stream raw di una attività → {tipo: [valori]} o None."""
    if not isinstance(data, list):
        return None
    streams = {s["type"]: s["data"] for s in data if s.get("type") and s.get("data")}
    return streams or None


def _parse_activities(athlete_id: str, data: Any) -> List[ActivitySummary]:
    if not data:
        return []
    acts: List[ActivitySummary] = []
    for rec in data:
        ext = rec.get("id")
        start = rec.get("start_date_local") or rec.get("start_date")
        date = str(start)[:10] if start else ""
        acts.append(ActivitySummary(
            id=make_activity_id(athlete_id, ext),
            athlete_id=athlete_id,
            date=date,
            type=rec.get("type"),
            name=rec.get("name"),
            moving_time_s=rec.get("moving_time"),
            load=rec.get("icu_training_load"),
            intensity=rec.get("icu_intensity"),
            distance_m=rec.get("distance"),
            avg_power=rec.get("icu_average_watts"),
            avg_hr=rec.get("average_heartrate"),
            max_hr=rec.get("max_heartrate"),
            external_id=str(ext) if ext is not None else None,
        ))
    return acts
