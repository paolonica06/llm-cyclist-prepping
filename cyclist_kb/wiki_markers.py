"""Grammatica condivisa dei blocchi Markdown preservati dalla rigenerazione."""

import re


MANUAL_NAME_PATTERN = r"[a-z0-9][a-z0-9_-]*"
MANUAL_BEGIN_RE = re.compile(
    rf"^<!-- BEGIN MANUAL: (?P<name>{MANUAL_NAME_PATTERN}) -->$"
)
MANUAL_END_RE = re.compile(
    rf"^<!-- END MANUAL: (?P<name>{MANUAL_NAME_PATTERN}) -->$"
)
MANUAL_BLOCK_RE = re.compile(
    rf"<!-- BEGIN MANUAL: (?P<name>{MANUAL_NAME_PATTERN}) -->\n"
    r".*?\n"
    r"<!-- END MANUAL: (?P=name) -->",
    re.DOTALL,
)
