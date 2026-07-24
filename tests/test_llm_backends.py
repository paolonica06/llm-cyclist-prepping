"""LLMClient multi-backend: offline = nessun backend; backend Claude Code (`claude -p`)."""

import json
import subprocess
import types

from cyclist_kb.llm import LLMClient


def _cc_client() -> LLMClient:
    # Nei test si è offline (backend None): forziamo 'claude_code' per testarne il parsing.
    c = LLMClient()
    c._backend = "claude_code"
    c._claude_bin = "claude"
    c._oauth_token = "tok"
    c._available = True
    c._cc_timeout = 5
    return c


def test_offline_has_no_backend():
    c = LLMClient()
    assert c.available is False
    assert c.backend is None
    assert c.complete_json("qualsiasi prompt") is None


def test_claude_code_parses_result_envelope(monkeypatch):
    c = _cc_client()

    def fake_run(cmd, **kw):
        assert "-p" in cmd and "--output-format" in cmd and "json" in cmd
        assert (kw.get("env") or {}).get("CLAUDE_CODE_OAUTH_TOKEN") == "tok"  # token propagato
        return types.SimpleNamespace(
            returncode=0, stdout=json.dumps({"result": '{"decision":"include","score":0.9}'}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert c.complete_json("prompt", system="sys") == {"decision": "include", "score": 0.9}


def test_claude_code_extracts_json_from_fenced_result(monkeypatch):
    c = _cc_client()

    def fake_run(cmd, **kw):
        return types.SimpleNamespace(
            returncode=0, stdout=json.dumps({"result": 'Ecco:\n```json\n{"a": 1}\n```'}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert c.complete_json("p") == {"a": 1}


def test_claude_code_degrades_on_failure(monkeypatch):
    c = _cc_client()

    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: types.SimpleNamespace(returncode=1, stdout=""))
    assert c.complete_json("p") is None                       # exit != 0

    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: types.SimpleNamespace(returncode=0, stdout="not json"))
    assert c.complete_json("p") is None                       # envelope non-JSON

    def boom(cmd, **kw):
        raise OSError("claude non trovato")

    monkeypatch.setattr(subprocess, "run", boom)
    assert c.complete_json("p") is None                       # eccezione → None, mai propagata
