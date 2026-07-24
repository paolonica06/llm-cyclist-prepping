"""Gestione della wiki Markdown e versionamento Git.

Le pagine sono interconnesse: `index.md` → `topics/<slug>.md` → `papers/<id>.md`.
Ogni aggiornamento della sintesi viene committato su Git, così la storia delle
conclusioni resta tracciata e nulla viene sovrascritto "silenziosamente".
"""

from __future__ import annotations

import logging
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import List, Optional

from .config import get_settings

logger = logging.getLogger("cyclist_kb.wiki")


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80] or "topic"


class Wiki:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.root = self.settings.wiki_dir
        (self.root / "topics").mkdir(parents=True, exist_ok=True)
        (self.root / "papers").mkdir(parents=True, exist_ok=True)
        (self.root / "athlete").mkdir(parents=True, exist_ok=True)

    # -- Percorsi ----------------------------------------------------------- #
    def topic_path(self, topic: str) -> Path:
        return self.root / "topics" / f"{slugify(topic)}.md"

    def paper_path(self, record_id: str) -> Path:
        return self.root / "papers" / f"{record_id}.md"

    def athlete_path(self, name: str) -> Path:
        return self.root / "athlete" / f"{slugify(name)}.md"

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    # -- Git ---------------------------------------------------------------- #
    def _git(self, *args: str) -> Optional[str]:
        try:
            out = subprocess.run(
                ["git", *args], cwd=str(self.settings.data_dir.parent),
                capture_output=True, text=True,
            )
            if out.returncode != 0:
                logger.debug("git %s → %s", args, out.stderr.strip())
                return None
            return out.stdout.strip()
        except FileNotFoundError:
            logger.warning("git non disponibile: versionamento disabilitato.")
            return None

    def ensure_repo(self) -> None:
        repo_root = self.settings.data_dir.parent
        if not (repo_root / ".git").exists():
            self._git("init")
            self._git("config", "user.email", "kb-agent@localhost")
            self._git("config", "user.name", "Cyclist KB Agent")
            logger.info("Repository git inizializzato in %s", repo_root)

    def commit(self, message: str) -> Optional[str]:
        if not self.settings.git_autocommit:
            return None
        self.ensure_repo()
        rel = self.root.relative_to(self.settings.data_dir.parent)
        self._git("add", str(rel))
        # Committa solo se ci sono modifiche NELLA WIKI (status scopato al path,
        # altrimenti altri file untracked del repo lo rendono sempre non vuoto).
        status = self._git("status", "--porcelain", "--", str(rel))
        if not status:
            return None
        commit_out = self._git("commit", "-m", message, "--", str(rel))
        if commit_out is None:  # commit fallito: non restituire un HEAD stantìo
            return None
        return self._git("rev-parse", "--short", "HEAD")


def update_index(wiki: Wiki, topics: List[dict]) -> None:
    """(Ri)genera l'indice della wiki da un elenco di descrittori topic."""
    lines = ["# Knowledge base — Allenamento ciclistico", "",
             "Base di conoscenza scientifica mantenuta automaticamente dagli agenti.", ""]
    lines.append("## Argomenti")
    for t in topics:
        rel = f"topics/{slugify(t['topic'])}.md"
        lines.append(f"- [{t['topic']}]({rel}) — {t.get('n_studies', 0)} studi sintetizzati "
                     f"(aggiornato {t.get('updated', 'n/d')})")
    lines.append("")
    wiki.write(wiki.root / "index.md", "\n".join(lines))
