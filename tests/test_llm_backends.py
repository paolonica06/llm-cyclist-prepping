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
    c._cc_model = "claude-sonnet-4-6"
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
        assert "--model" in cmd and "claude-sonnet-4-6" in cmd                # modello fissato
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


def _codex_client() -> LLMClient:
    c = LLMClient()
    c._backend = "codex"
    c._codex_bin = "codex"
    c._codex_model = None
    c._codex_timeout = 5
    c._usage_log = None
    c._codex_reasoning_effort = None
    c._available = True
    return c


def test_codex_reads_last_message_file(monkeypatch):
    c = _codex_client()

    def fake_run(cmd, **kw):
        assert "exec" in cmd and "-o" in cmd                  # modalità non-interattiva
        path = cmd[cmd.index("-o") + 1]                       # scrive il JSON nel file -o
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('Ecco:\n{"decision": "include", "score": 0.7}')
        return types.SimpleNamespace(returncode=0, stderr="tokens used\n123")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert c.complete_json("prompt") == {"decision": "include", "score": 0.7}


def test_codex_degrades_on_failure(monkeypatch):
    c = _codex_client()
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: types.SimpleNamespace(returncode=1, stderr=""))
    assert c.complete_json("p") is None


def _codex_capture(monkeypatch, captured):
    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as fh:
            fh.write('{"ok": true}')
        return types.SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)


def test_codex_passes_reasoning_effort_override(monkeypatch):
    c = _codex_client()
    c._codex_reasoning_effort = "low"                         # override per-chiamata
    captured = {}
    _codex_capture(monkeypatch, captured)
    assert c.complete_json("prompt") == {"ok": True}
    cmd = captured["cmd"]
    assert "-c" in cmd and "model_reasoning_effort=low" in cmd


def test_codex_omits_reasoning_effort_when_unset(monkeypatch):
    c = _codex_client()                                       # _codex_reasoning_effort=None
    captured = {}
    _codex_capture(monkeypatch, captured)
    c.complete_json("p")
    assert "model_reasoning_effort" not in " ".join(captured["cmd"])
