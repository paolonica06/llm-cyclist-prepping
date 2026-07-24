"""Wrapper multi-backend sull'LLM, con *graceful degradation*.

Backend, in ordine di preferenza quando `KB_LLM_BACKEND=auto`:
  1. **anthropic**   — raw Messages API (richiede `ANTHROPIC_API_KEY`).
  2. **claude_code** — shell-out al CLI `claude -p` (usa `CLAUDE_CODE_OAUTH_TOKEN`,
     cioè l'abbonamento Claude: nessun costo API pay-as-you-go). Pattern
     sanzionato per Claude Code in headless/CI.
Se `KB_FORCE_OFFLINE=1` o nessun backend è disponibile, `available` è False e ogni
agente ricade sulle proprie euristiche deterministiche. **I test girano sempre
offline** (`conftest` imposta `KB_FORCE_OFFLINE=1`): nessun backend, tutto
riproducibile, nessuna chiamata a rete/CLI.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from .config import get_settings

_DEFAULT_SYSTEM = "Sei un assistente scientifico rigoroso. Rispondi SOLO con JSON valido."


class LLMClient:
    def __init__(self) -> None:
        s = get_settings()
        self.model = s.llm_model
        self.max_tokens = s.llm_max_tokens
        self._client = None
        self._backend: Optional[str] = None
        self._claude_bin: Optional[str] = None
        self._oauth_token: Optional[str] = None
        self._cc_timeout = s.claude_code_timeout
        self._available = False

        if s.force_offline:
            return
        pref = (s.llm_backend or "auto").lower()

        # 1) API Anthropic (chiave pay-as-you-go)
        if pref in ("auto", "anthropic") and s.anthropic_api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=s.anthropic_api_key)
                self._backend = "anthropic"
            except Exception:
                self._client = None

        # 2) Claude Code CLI (OAuth abbonamento)
        if self._backend is None and pref in ("auto", "claude_code") and s.claude_code_oauth_token:
            import shutil

            binp = shutil.which(s.claude_code_bin)
            if binp:
                self._backend = "claude_code"
                self._claude_bin = binp
                self._oauth_token = s.claude_code_oauth_token

        self._available = self._backend is not None

    @property
    def available(self) -> bool:
        return self._available

    @property
    def backend(self) -> Optional[str]:
        return self._backend

    def complete_json(
        self,
        prompt: str,
        system: str = _DEFAULT_SYSTEM,
        max_tokens: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Restituisce un dict JSON dalla risposta del modello, o None in caso di errore.

        Non solleva mai: un fallimento deve degradare all'euristica, non
        interrompere la pipeline.
        """
        if not self._available:
            return None
        if self._backend == "anthropic":
            return self._complete_anthropic(prompt, system, max_tokens)
        if self._backend == "claude_code":
            return self._complete_claude_code(prompt, system, max_tokens)
        return None

    # -- Backend: raw Messages API ----------------------------------------- #
    def _complete_anthropic(self, prompt: str, system: str,
                            max_tokens: Optional[int]) -> Optional[Dict[str, Any]]:
        if self._client is None:
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

    # -- Backend: Claude Code CLI (`claude -p`) ---------------------------- #
    def _complete_claude_code(self, prompt: str, system: str,
                              max_tokens: Optional[int]) -> Optional[Dict[str, Any]]:
        import os
        import subprocess

        cmd = [
            self._claude_bin, "-p", prompt,
            "--output-format", "json",
            "--system-prompt", system,
        ]
        env = os.environ.copy()
        if self._oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self._oauth_token
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._cc_timeout, env=env
            )
            if proc.returncode != 0 or not proc.stdout:
                return None
            envelope = json.loads(proc.stdout)          # {"result": "...", ...}
            return _extract_json(envelope.get("result") or "")
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
