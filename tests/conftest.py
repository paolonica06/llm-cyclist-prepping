"""Configurazione dei test: modalità offline deterministica (nessun LLM/rete)."""

import os

os.environ.setdefault("KB_FORCE_OFFLINE", "1")
os.environ.setdefault("KB_GIT_AUTOCOMMIT", "0")
