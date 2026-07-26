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
_DEFAULT_TEXT_SYSTEM = ("Sei un preparatore ciclistico scientifico, chiaro e onesto. "
                       "Rispondi in italiano, senza inventare numeri.")


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
        self._cc_model = s.claude_code_model
        self._codex_bin: Optional[str] = None
        self._codex_model = s.codex_model
        self._codex_timeout = s.codex_timeout
        self._codex_reasoning_effort = s.codex_reasoning_effort
        self._usage_log = s.llm_usage_log
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

        # 3) Codex CLI (ChatGPT) — solo se richiesto esplicitamente (login/quota separati)
        if self._backend is None and pref == "codex":
            import shutil

            binp = shutil.which(s.codex_bin)
            if binp:
                self._backend = "codex"
                self._codex_bin = binp

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
        text = self._raw_complete(prompt, system, max_tokens)
        return _extract_json(text) if text else None

    def complete_text(
        self,
        prompt: str,
        system: str = _DEFAULT_TEXT_SYSTEM,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Output testuale libero (narrativa coach, conversazione «chiedi al preparatore»).

        A differenza di `complete_json` NON forza né estrae JSON: ritorna il testo
        grezzo del modello, o None in caso di errore/offline (il chiamante degrada
        a una risposta deterministica). Non solleva mai.
        """
        text = self._raw_complete(prompt, system, max_tokens)
        return text.strip() if text else None

    def _raw_complete(self, prompt: str, system: str,
                      max_tokens: Optional[int]) -> Optional[str]:
        """Dispatch sul backend attivo → testo grezzo (o None). Mai un'eccezione."""
        if not self._available:
            return None
        if self._backend == "anthropic":
            return self._raw_anthropic(prompt, system, max_tokens)
        if self._backend == "claude_code":
            return self._raw_claude_code(prompt, system, max_tokens)
        if self._backend == "codex":
            return self._raw_codex(prompt, system, max_tokens)
        return None

    # -- Backend: raw Messages API ----------------------------------------- #
    def _raw_anthropic(self, prompt: str, system: str,
                       max_tokens: Optional[int]) -> Optional[str]:
        if self._client is None:
            return None
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(
                block.text for block in resp.content if getattr(block, "type", None) == "text"
            )
        except Exception:
            return None

    # -- Backend: Claude Code CLI (`claude -p`) ---------------------------- #
    def _raw_claude_code(self, prompt: str, system: str,
                         max_tokens: Optional[int]) -> Optional[str]:
        import os
        import subprocess

        cmd = [
            self._claude_bin, "-p", prompt,
            "--output-format", "json",
            "--system-prompt", system,
            "--model", self._cc_model,          # esplicito: evita il default (Opus) costoso
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
            return envelope.get("result") or None
        except Exception:
            return None

    # -- Backend: Codex CLI (`codex exec`, abbonamento ChatGPT) ------------ #
    def _raw_codex(self, prompt: str, system: str,
                   max_tokens: Optional[int]) -> Optional[str]:
        import os
        import subprocess
        import tempfile

        neutral = tempfile.gettempdir()
        fd, out_path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        # Codex ha un system prompt proprio (agente di coding): anteponiamo il nostro.
        full_prompt = f"{system}\n\n{prompt}"
        cmd = [self._codex_bin, "exec", full_prompt, "-o", out_path,
               "--skip-git-repo-check", "-C", neutral, "--sandbox", "read-only"]
        if self._codex_model:
            cmd += ["-m", self._codex_model]
        # Abbassa il reasoning effort per-chiamata (override della config globale codex):
        # taglia i reasoning-token e il rischio di timeout sui batch (es. quality).
        if self._codex_reasoning_effort:
            cmd += ["-c", f"model_reasoning_effort={self._codex_reasoning_effort}"]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._codex_timeout
            )
            self._log_usage(proc.stderr)                 # traccia i "tokens used"
            if proc.returncode != 0:
                return None
            with open(out_path, "r", encoding="utf-8") as fh:
                return fh.read() or None                 # -o = solo il messaggio finale
        except Exception:
            return None
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass

    def _log_usage(self, stderr: Optional[str]) -> None:
        """Appende i token usati (riportati dal CLI) a `llm_usage_log`, per misurare il consumo."""
        if not self._usage_log or not stderr:
            return
        m = re.search(r"tokens used[^0-9]*([\d.,]+)", stderr, re.IGNORECASE | re.DOTALL)
        if not m:
            return
        try:
            with open(self._usage_log, "a", encoding="utf-8") as fh:
                fh.write(m.group(1).strip() + "\n")
        except OSError:
            pass


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


def chunked(seq, size: int):
    """Divide una sequenza in blocchi di al più `size` elementi (per il batching LLM)."""
    items = list(seq)
    step = max(1, size)
    for i in range(0, len(items), step):
        yield items[i : i + step]


_llm: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
