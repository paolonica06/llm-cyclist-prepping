"""Helper HTTP asincrono condiviso dai client bibliografici."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from ..config import get_settings

logger = logging.getLogger("cyclist_kb.http")


@dataclass
class WriteResult:
    """Esito di una scrittura HTTP. Esplicito per costruzione: le scritture non
    possono degradare a None come le letture."""

    ok: bool
    status: Optional[int]
    body: Any
    error: Optional[str] = None


class HttpFetcher:
    """Wrapper su httpx.AsyncClient con retry, backoff e cortesia (User-Agent/mailto).

    Non solleva mai per errori di rete/HTTP: restituisce None così che i client
    possano degradare a lista vuota.
    """

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        s = get_settings()
        self._external = client is not None
        self._client = client
        self._headers = {"User-Agent": s.resolved_user_agent(), "Accept": "application/json"}
        self._timeout = s.http_timeout
        self._max_retries = s.http_max_retries

    async def __aenter__(self) -> "HttpFetcher":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, headers=self._headers,
                                             follow_redirects=True)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None and not self._external:
            await self._client.aclose()
            self._client = None

    async def _request(self, url: str, params: Optional[Dict[str, Any]], as_json: bool,
                       headers: Optional[Dict[str, str]] = None):
        assert self._client is not None
        # Gli header per-richiesta si FONDONO con quelli di default (User-Agent/mailto):
        # così un'eventuale Authorization non fa perdere la cortesia della polite pool.
        merged = {**self._headers, **(headers or {})}
        delay = 1.0
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._client.get(url, params=params, headers=merged)
                if resp.status_code == 429 or resp.status_code >= 500:
                    logger.warning("HTTP %s da %s (tentativo %d)", resp.status_code, url, attempt)
                    if attempt < self._max_retries:
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                resp.raise_for_status()
                return resp.json() if as_json else resp.text
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Errore su %s (tentativo %d/%d): %s",
                               url, attempt, self._max_retries, exc)
                if attempt < self._max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    return None
        return None

    async def get_json(self, url: str, params: Optional[Dict[str, Any]] = None,
                       headers: Optional[Dict[str, str]] = None) -> Optional[Any]:
        return await self._request(url, params, as_json=True, headers=headers)

    async def send_json(self, method: str, url: str, payload: Any,
                        headers: Optional[Dict[str, str]] = None) -> "WriteResult":
        """Scrittura (PUT/POST/DELETE). A differenza delle letture NON degrada in
        silenzio: l'esito torna sempre esplicito, perché un push perso o duplicato è
        peggio di un errore visibile. Retry solo su 429 (richiesta non processata);
        mai su 5xx, che su POST potrebbe duplicare l'evento.
        """
        assert self._client is not None
        merged = {**self._headers, **(headers or {})}
        delay = 1.0
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._client.request(method, url, json=payload, headers=merged)
            except httpx.HTTPError as exc:
                logger.warning("Errore rete su %s %s: %s", method, url, exc)
                return WriteResult(ok=False, status=None, body=None, error=str(exc))
            if resp.status_code == 429 and attempt < self._max_retries:
                logger.warning("HTTP 429 da %s (tentativo %d)", url, attempt)
                await asyncio.sleep(delay)
                delay *= 2
                continue
            ok = 200 <= resp.status_code < 300
            body: Any = None
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            return WriteResult(ok=ok, status=resp.status_code, body=body,
                               error=None if ok else str(body)[:400])
        return WriteResult(ok=False, status=429, body=None, error="rate limit persistente")

    async def get_text(self, url: str, params: Optional[Dict[str, Any]] = None,
                       headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        # Di default per il testo/HTML sovrascrive l'Accept JSON del client.
        headers = headers or {"Accept": "text/html,application/xhtml+xml,text/plain,*/*"}
        return await self._request(url, params, as_json=False, headers=headers)
