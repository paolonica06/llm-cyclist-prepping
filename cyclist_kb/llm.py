"""Wrapper minimale sull'API LLM (Anthropic).

Progettato per il *graceful degradation*: se non è configurata alcuna chiave
(oppure `KB_FORCE_OFFLINE=1`), `available` è False e ogni agente ricade sulle
proprie euristiche deterministiche. Questo rende la demo eseguibile offline e i
test riproducibili, senza mai bloccare la pipeline.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from .config import get_settings


class LLMClient:
    def __init__(self) -> None:
        s = get_settings()
        self.model = s.llm_model
        self.max_tokens = s.llm_max_tokens
        self._client = None
        self._available = False
        if s.anthropic_api_key and not s.force_offline:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=s.anthropic_api_key)
                self._available = True
            except Exception:
                self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def complete_json(
        self,
        prompt: str,
        system: str = "Sei un assistente scientifico rigoroso. Rispondi SOLO con JSON valido.",
        max_tokens: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Restituisce un dict JSON dalla risposta del modello, o None in caso di errore.

        Non solleva mai: un fallimento LLM deve degradare all'euristica, non
        interrompere la pipeline.
        """
        if not self._available or self._client is None:
            return None
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                block.text for block in resp.content if getattr(block, "type", None) == "text"
            )
            return _extract_json(text)
        except Exception:
            return None


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    # Rimuove eventuali fence markdown ```json ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Ultimo tentativo: prende il primo blocco { ... } bilanciato
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        return None
        return None


_llm: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
