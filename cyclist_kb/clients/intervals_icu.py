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

    async def fetch_power_curve(self, athlete_id: str,
                                activity_type: Optional[str] = "Ride",
                                curves: Optional[str] = None) -> List[TimeseriesPoint]:
        """Curva di potenza mean-max **già calcolata** da intervals.icu (ramo mirror).

        Endpoint `/athlete/{id}/power-curves` → `{list: [curva...], activities: {...}}`.
        NON scarichiamo i watt grezzi né ricalcoliamo mean-max in casa (ADR-0001): la
        curva è una metrica derivata che la piattaforma calcola a monte. Ogni curva del
        payload diventa un `TimeseriesPoint(POWER_CURVE)` datato alla fine periodo.
        """
        params: Dict[str, Any] = {}
        if activity_type:
            params["type"] = activity_type
        if curves:
            params["curves"] = curves
        data = await self._get(f"/athlete/{athlete_id}/power-curves", params or None)
        return _parse_power_curves(athlete_id, data)


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


def _parse_power_curves(athlete_id: str, data: Any) -> List[TimeseriesPoint]:
    """Normalizza il payload di /power-curves in punti-serie POWER_CURVE.

    Ogni curva porta `secs` (durate) e `values` (best watt per durata), più
    `watts_per_kg`. Le impacchettiamo in `extra` (durata→watt come stringa, coerente
    con l'esempio del modello `{"300": 320, ...}`), datando il punto alla fine periodo
    (`end_date_local`), che è la sua natura "as-of". Curve senza data o senza dati utili
    vengono scartate.
    """
    lst = data.get("list") if isinstance(data, dict) else data
    if not lst:
        return []
    points: List[TimeseriesPoint] = []
    for curve in lst:
        if not isinstance(curve, dict):
            continue
        secs = curve.get("secs") or []
        values = curve.get("values") or []
        if not secs or not values:
            continue
        end = curve.get("end_date_local") or curve.get("start_date_local")
        date = str(end)[:10] if end else ""
        if not date:
            continue
        secs_watts = {str(s): v for s, v in zip(secs, values) if v is not None}
        if not secs_watts:
            continue
        extra: Dict[str, Any] = {
            "label": curve.get("label"),
            "start": curve.get("start_date_local"),
            "end": curve.get("end_date_local"),
            "days": curve.get("days"),
            "secs_watts": secs_watts,
        }
        wkg = curve.get("watts_per_kg") or []
        wkg_map = {str(s): w for s, w in zip(secs, wkg) if w is not None}
        if wkg_map:
            extra["watts_per_kg"] = wkg_map
        points.append(TimeseriesPoint(
            athlete_id=athlete_id, metric_type=MetricType.POWER_CURVE, date=date,
            value=None, extra=extra, source="intervals_icu"))
    return points


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
