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

from ..athlete_models import (ActivitySummary, MetricType, TimeseriesPoint,
                              make_activity_id)
from ..config import get_settings
from .base import HttpFetcher

BASE = "https://intervals.icu/api/v1"

# Curva di potenza: periodi richiesti (recenti → assoluti) e tipi di attività.
# `type` accetta un solo valore per chiamata, quindi outdoor+indoor = due chiamate.
POWER_CURVE_WINDOWS = "42d,90d,365d,all"
POWER_CURVE_TYPES = ("Ride", "VirtualRide")

# Campo dell'endpoint wellness → nostra grandezza (MetricType).
_WELLNESS_FIELDS = {
    "sleepSecs": MetricType.SLEEP,
    "hrv": MetricType.HRV,
    "weight": MetricType.WEIGHT,
    "restingHR": MetricType.RESTING_HR,
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

    async def fetch_activity_power_curve(self, activity_external_id: str) -> Optional[Dict[str, Any]]:
        """Curva mean-max della **singola** attività (già calcolata da intervals.icu).

        Endpoint `/activity/{id}/power-curve` → `{secs, values, watts_per_kg, ...}`.
        `None` se offline/no-key o se l'attività non ha potenza (nessun power meter).
        """
        data = await self._get(f"/activity/{activity_external_id}/power-curve")
        return _parse_activity_power_curve(data)


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
            external_id=str(ext) if ext is not None else None,
        ))
    return acts
