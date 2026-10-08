"""Import bootstrap for the pdf-builder tests.

Not named `test_*`, so `unittest discover` imports it but never runs it.

Importing `md2pdf` is side-effect free: it defines constants and functions, and every
impure thing it does (fetching mermaid, launching Chrome, writing files) sits inside a
function that these tests either avoid or stub. No network, no Chrome, no PDF is
produced by this suite.
"""
from __future__ import annotations

import json
import pathlib
import sys

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import md2pdf as m  # noqa: E402

try:                      # python-markdown is a third-party dep. build_html needs it,
    import markdown      # and so does convert_callouts, which renders the callout
    HAS_MARKDOWN = True  # body with it — the other helpers are pure text.
except ImportError:       # pragma: no cover
    HAS_MARKDOWN = False


def vault_dir() -> pathlib.Path | None:
    """The installed vault's `ideaVerse/`, or None outside an installed tree.

    The suite ships with the skill, so it runs in repos whose vault is not where this
    one's is: `aiOS/aios.config.json` is the only thing that knows. Hardcoding
    `<repo>/docs/ideaVerse` made the vault-wide citation test pass in the vault it was
    written in and fail everywhere else.
    """
    for repo in pathlib.Path(__file__).resolve().parents:
        config = repo / "aiOS" / "aios.config.json"
        if not config.is_file():
            continue
        try:
            cfg = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        root = repo if cfg.get("vaultAtRepoRoot") else repo / cfg.get("vaultDir", "docs")
        return root / "ideaVerse"
    return None


def pdf_bytes(pages: int) -> bytes:
    """Minimal stand-in for a Chrome-produced PDF with `pages` page objects."""
    body = b"".join(b"<< /Type /Page /Parent 1 0 R >>\n" for _ in range(pages))
    header = b"%PDF-1.4\n<< /Type /Pages /Count " + str(pages).encode() + b" >>\n"
    return header + body + b"%%EOF"
