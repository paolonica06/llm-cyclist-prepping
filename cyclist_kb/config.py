"""Configurazione centralizzata (percorsi, credenziali API, cortesia verso i servizi).

Le API bibliografiche pubbliche (NCBI, OpenAlex, Crossref) chiedono un contatto
`mailto`/User-Agent per la "polite pool": impostare `KB_CONTACT_EMAIL`.
La chiave `ANTHROPIC_API_KEY` è opzionale: se assente gli agenti usano euristiche
deterministiche offline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Radice del progetto (…/llm_cyclist)
ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KB_",
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Percorsi ---------------------------------------------------------- #
    data_dir: Path = ROOT / "data"
    raw_dir: Path = ROOT / "data" / "raw"
    db_path: Path = ROOT / "data" / "kb.sqlite3"
    wiki_dir: Path = ROOT / "wiki"
    profiles_dir: Path = ROOT / "profiles"

    # --- Cortesia verso le API --------------------------------------------- #
    contact_email: str = "anonymous@example.com"     # KB_CONTACT_EMAIL
    user_agent: str = "cyclist-kb/0.1 (local MVP; mailto:{email})"

    # --- LLM --------------------------------------------------------------- #
    anthropic_api_key: Optional[str] = None          # KB_ANTHROPIC_API_KEY oppure ANTHROPIC_API_KEY
    llm_model: str = "claude-opus-4-8"
    llm_max_tokens: int = 2000
    force_offline: bool = False                      # KB_FORCE_OFFLINE=1 → euristiche anche con chiave
    # Backend LLM: "auto" (API se c'è la key, altrimenti Claude Code se c'è il token),
    # oppure forzato: "anthropic" | "claude_code" | "off".
    llm_backend: str = "auto"
    # Token OAuth dell'abbonamento per il backend Claude Code (headless `claude -p`).
    # KB_CLAUDE_CODE_OAUTH_TOKEN oppure la variabile standard CLAUDE_CODE_OAUTH_TOKEN.
    claude_code_oauth_token: Optional[str] = None
    claude_code_bin: str = "claude"                  # nome/percorso del CLI Claude Code
    claude_code_timeout: float = 180.0               # secondi per chiamata `claude -p`
    # Modello del backend Claude Code. NB: senza questo, `claude -p` userebbe il
    # default (spesso Opus) — costosissimo per il batch. Sonnet: qualità/quota bilanciate.
    claude_code_model: str = "claude-sonnet-4-6"
    # Batching: quanti record valutare in UNA singola chiamata LLM (screening/
    # estrazione/qualità). Riduce ~N× il numero di chiamate → molto più veloce e
    # leggero sull'uso. 1 = comportamento non-batch.
    llm_batch_size: int = 10

    # --- Ingestione atleta (Fase B) --------------------------------------- #
    intervals_icu_api_key: Optional[str] = None      # KB_INTERVALS_ICU_API_KEY (auth Basic su intervals.icu)

    # --- Recupero ---------------------------------------------------------- #
    ncbi_api_key: Optional[str] = None               # aumenta il rate limit di E-utilities
    results_per_source: int = 25
    citation_chase_seeds: int = 5                     # quanti top-record usare come semi
    citation_chase_limit: int = 15                    # quante referenze aggiungere per seme
    http_timeout: float = 30.0
    http_max_retries: int = 3

    # --- Git --------------------------------------------------------------- #
    git_autocommit: bool = True                      # committa gli aggiornamenti della wiki

    def resolved_user_agent(self) -> str:
        return self.user_agent.replace("{email}", self.contact_email)

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.raw_dir, self.wiki_dir, self.profiles_dir,
                  self.wiki_dir / "topics", self.wiki_dir / "papers", self.wiki_dir / "athlete"):
            p.mkdir(parents=True, exist_ok=True)


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton pigro delle impostazioni, con fallback su ANTHROPIC_API_KEY 'classica'."""
    global _settings
    if _settings is None:
        import os

        s = Settings()
        # Consente sia KB_ANTHROPIC_API_KEY sia la variabile standard ANTHROPIC_API_KEY.
        if not s.anthropic_api_key:
            s.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not s.claude_code_oauth_token:
            s.claude_code_oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if os.environ.get("KB_CONTACT_EMAIL"):
            s.contact_email = os.environ["KB_CONTACT_EMAIL"]
        s.ensure_dirs()
        _settings = s
    return _settings
