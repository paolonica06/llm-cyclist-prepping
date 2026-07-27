"""Lint offline e deterministico della wiki Markdown/Obsidian."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import List, Optional, Sequence
from urllib.parse import unquote, urlsplit


_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_MANUAL_MARKER_RE = re.compile(
    r"^\s*<!--\s*(BEGIN|END)\s+MANUAL:\s*([A-Za-z0-9_.-]+)\s*-->\s*$"
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+\.\s+")
_PROVENANCE_RE = re.compile(r"^\s*\d+\.\s+\*\*\[(studi|dati_atleta|euristica)\]\*\*")
_URL_RE = re.compile(r"https?://[^\s<>\]]+")
_PRIVATE_PATTERNS = (
    re.compile(r"\bi215294\b", re.IGNORECASE),
    re.compile(r"\bdata/private/mental-health(?:/|\b)", re.IGNORECASE),
    re.compile(r"\b(?:sk-ant-|sk-proj-|ghp_|github_pat_)[A-Za-z0-9_-]*", re.IGNORECASE),
)


@dataclass(frozen=True)
class LintIssue:
    path: Path
    line: int
    code: str
    message: str

    def format(self, root: Path) -> str:
        try:
            relative = self.path.relative_to(root)
        except ValueError:
            relative = self.path
        return f"{relative}:{self.line}: {self.code} {self.message}"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _lint_relative_links(path: Path, text: str) -> List[LintIssue]:
    issues: List[LintIssue] = []
    for match in _MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith(("#", "mailto:")):
            continue
        raw_path = unquote(parsed.path)
        if not raw_path.lower().endswith(".md"):
            continue
        resolved = (path.parent / raw_path).resolve()
        if not resolved.exists():
            issues.append(
                LintIssue(
                    path=path,
                    line=_line_number(text, match.start()),
                    code="WIKI001",
                    message=f"link relativo inesistente: {target}",
                )
            )
    return issues


def _line_is_fenced(line: str, in_fence: bool) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def _lint_wikilinks(
    root: Path,
    path: Path,
    text: str,
    files_by_stem: dict[str, List[Path]],
) -> List[LintIssue]:
    issues: List[LintIssue] = []
    for match in _WIKILINK_RE.finditer(text):
        target = unquote(match.group(1).split("|", 1)[0].split("#", 1)[0].strip())
        if not target:
            continue

        target_path = Path(target)
        if target_path.suffix.lower() == ".md":
            target_path = target_path.with_suffix("")

        candidates: List[Path]
        if len(target_path.parts) > 1:
            relative_candidate = (path.parent / target_path).with_suffix(".md").resolve()
            root_candidate = (root / target_path).with_suffix(".md").resolve()
            candidates = sorted(
                {
                    candidate
                    for candidate in (relative_candidate, root_candidate)
                    if candidate.is_file()
                }
            )
        else:
            candidates = files_by_stem.get(target_path.name.casefold(), [])

        if not candidates:
            issues.append(
                LintIssue(
                    path,
                    _line_number(text, match.start()),
                    "WIKI002",
                    f"wikilink irrisolto: {match.group(1)}",
                )
            )
        elif len(candidates) > 1:
            issues.append(
                LintIssue(
                    path,
                    _line_number(text, match.start()),
                    "WIKI002",
                    f"wikilink ambiguo: {match.group(1)}",
                )
            )
    return issues


def _lint_manual_markers(path: Path, lines: List[str]) -> List[LintIssue]:
    issues: List[LintIssue] = []
    open_marker: Optional[tuple[str, int]] = None
    completed_names: set[str] = set()

    for line_number, line in enumerate(lines, start=1):
        match = _MANUAL_MARKER_RE.match(line)
        if not match:
            continue
        kind, name = match.groups()
        if kind == "BEGIN":
            if open_marker is not None:
                issues.append(
                    LintIssue(path, line_number, "WIKI003", "blocco MANUAL annidato")
                )
            elif name in completed_names:
                issues.append(
                    LintIssue(
                        path,
                        line_number,
                        "WIKI003",
                        f"blocco MANUAL duplicato: {name}",
                    )
                )
            else:
                open_marker = (name, line_number)
            continue

        if open_marker is None:
            issues.append(
                LintIssue(
                    path,
                    line_number,
                    "WIKI003",
                    f"fine MANUAL senza inizio: {name}",
                )
            )
        elif open_marker[0] != name:
            issues.append(
                LintIssue(
                    path,
                    line_number,
                    "WIKI003",
                    f"marker MANUAL non corrispondenti: {open_marker[0]} / {name}",
                )
            )
            open_marker = None
        else:
            completed_names.add(name)
            open_marker = None

    if open_marker is not None:
        issues.append(
            LintIssue(
                path,
                open_marker[1],
                "WIKI003",
                f"blocco MANUAL non chiuso: {open_marker[0]}",
            )
        )
    return issues


def _lint_duplicate_index_targets(root: Path, path: Path, text: str) -> List[LintIssue]:
    if path != root / "index.md":
        return []

    issues: List[LintIssue] = []
    seen: set[str] = set()
    for match in _MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        parsed = urlsplit(target)
        raw_path = unquote(parsed.path)
        if parsed.scheme or not raw_path.lower().endswith(".md"):
            continue
        normalized = str((path.parent / raw_path).resolve()).casefold()
        if normalized in seen:
            issues.append(
                LintIssue(
                    path,
                    _line_number(text, match.start()),
                    "WIKI004",
                    f"target duplicato nell'indice: {target}",
                )
            )
        else:
            seen.add(normalized)
    return issues


def _lint_identifiers(path: Path, text: str) -> List[LintIssue]:
    issues: List[LintIssue] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(").,;:")
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").casefold()
        line = _line_number(text, match.start())

        if hostname in {"doi.org", "dx.doi.org"}:
            suffix = unquote(parsed.path.lstrip("/"))
            canonical = (
                parsed.scheme == "https"
                and hostname == "doi.org"
                and bool(re.fullmatch(r"10\.\d{4,9}/\S+", suffix))
            )
            if not canonical:
                issues.append(
                    LintIssue(path, line, "WIKI005", f"URL DOI non canonico: {url}")
                )
        elif hostname == "pubmed.ncbi.nlm.nih.gov":
            canonical = (
                parsed.scheme == "https"
                and bool(re.fullmatch(r"/\d+/", parsed.path))
                and not parsed.query
                and not parsed.fragment
            )
            if not canonical:
                issues.append(
                    LintIssue(path, line, "WIKI005", f"URL PubMed non canonico: {url}")
                )
    return issues


def _lint_curated_provenance(path: Path, text: str, lines: List[str]) -> List[LintIssue]:
    if "Corpus curato manualmente" not in text:
        return []

    issues: List[LintIssue] = []
    operational_section = False
    for line_number, line in enumerate(lines, start=1):
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            title = heading.group(1).casefold()
            operational_section = (
                "applicazione" in title or "principi osservabili" in title
            )
            continue
        if operational_section and _NUMBERED_ITEM_RE.match(line):
            if not _PROVENANCE_RE.match(line):
                issues.append(
                    LintIssue(
                        path,
                        line_number,
                        "WIKI006",
                        "raccomandazione operativa senza provenienza",
                    )
                )
    return issues


def _lint_private_content(path: Path, lines: List[str]) -> List[LintIssue]:
    issues: List[LintIssue] = []
    for line_number, line in enumerate(lines, start=1):
        if any(pattern.search(line) for pattern in _PRIVATE_PATTERNS):
            issues.append(
                LintIssue(
                    path,
                    line_number,
                    "WIKI007",
                    "identificatore privato o prefisso di segreto",
                )
            )
    return issues


def _table_column_count(line: str) -> int:
    content = line.strip()[1:-1]
    return len(re.split(r"(?<!\\)\|", content))


def _lint_tables(path: Path, lines: List[str]) -> List[LintIssue]:
    issues: List[LintIssue] = []
    expected_columns: Optional[int] = None
    in_table = False

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        is_table_row = stripped.startswith("|") and stripped.endswith("|")
        if not is_table_row:
            in_table = False
            expected_columns = None
            continue

        columns = _table_column_count(line)
        if not in_table:
            in_table = True
            expected_columns = columns
        elif columns != expected_columns:
            issues.append(
                LintIssue(
                    path,
                    line_number,
                    "WIKI008",
                    f"tabella con {columns} colonne; attese {expected_columns}",
                )
            )
    return issues


def _lint_headings(path: Path, lines: List[str]) -> List[LintIssue]:
    issues: List[LintIssue] = []
    h1_lines: List[int] = []
    previous_level: Optional[int] = None
    in_fence = False

    for line_number, line in enumerate(lines, start=1):
        if _line_is_fenced(line, in_fence):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        if level == 1:
            h1_lines.append(line_number)
        if previous_level is not None and level > previous_level + 1:
            issues.append(
                LintIssue(
                    path,
                    line_number,
                    "WIKI009",
                    f"salto di livello H{previous_level} → H{level}",
                )
            )
        previous_level = level

    if not h1_lines:
        issues.append(LintIssue(path, 1, "WIKI009", "H1 mancante"))
    for line_number in h1_lines[1:]:
        issues.append(LintIssue(path, line_number, "WIKI009", "H1 duplicato"))
    return issues


def _lint_whitespace(root: Path, path: Path, lines: List[str]) -> List[LintIssue]:
    relative = path.relative_to(root)
    if relative.parts and relative.parts[0] == "papers":
        return []

    issues: List[LintIssue] = []
    for line_number, line in enumerate(lines, start=1):
        if "\t" in line or line.endswith(" "):
            issues.append(
                LintIssue(
                    path,
                    line_number,
                    "WIKI010",
                    "tab o spazio finale",
                )
            )
    return issues


def lint_wiki(root: Path) -> List[LintIssue]:
    root = root.resolve()
    issues: List[LintIssue] = []
    files = sorted(root.rglob("*.md"))
    files_by_stem: dict[str, List[Path]] = {}
    for path in files:
        files_by_stem.setdefault(path.stem.casefold(), []).append(path)

    for path in files:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        issues.extend(_lint_relative_links(path, text))
        issues.extend(_lint_wikilinks(root, path, text, files_by_stem))
        issues.extend(_lint_manual_markers(path, lines))
        issues.extend(_lint_duplicate_index_targets(root, path, text))
        issues.extend(_lint_identifiers(path, text))
        issues.extend(_lint_curated_provenance(path, text, lines))
        issues.extend(_lint_private_content(path, lines))
        issues.extend(_lint_tables(path, lines))
        issues.extend(_lint_headings(path, lines))
        issues.extend(_lint_whitespace(root, path, lines))
    return sorted(issues, key=lambda issue: (str(issue.path), issue.line, issue.code))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lint semantico della wiki Markdown/Obsidian")
    default_root = Path(__file__).resolve().parent.parent / "wiki"
    parser.add_argument("--root", type=Path, default=default_root, help="radice della wiki")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"{root}: root wiki inesistente", file=sys.stderr)
        return 2

    issues = lint_wiki(root)
    if issues:
        for issue in issues:
            print(issue.format(root), file=sys.stderr)
        print(f"Wiki lint: {len(issues)} errore/i", file=sys.stderr)
        return 1

    count = sum(1 for _ in root.rglob("*.md"))
    print(f"Wiki lint: OK ({count} file Markdown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
