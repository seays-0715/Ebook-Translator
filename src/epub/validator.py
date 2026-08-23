"""Level 3 — EPUB package validation (spec §32.1).

Lightweight structural checks (not full epubcheck).
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EpubValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_epub_file(path: str | Path) -> EpubValidationResult:
    path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        return EpubValidationResult(ok=False, errors=[f"File not found: {path}"])
    if path.stat().st_size == 0:
        return EpubValidationResult(ok=False, errors=["EPUB file is empty"])

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            if "mimetype" not in names:
                errors.append("Missing mimetype")
            else:
                mt = zf.read("mimetype")
                if mt != b"application/epub+zip":
                    errors.append(f"Bad mimetype: {mt!r}")
            if "META-INF/container.xml" not in names:
                errors.append("Missing META-INF/container.xml")
            opfs = [n for n in names if n.endswith(".opf")]
            if not opfs:
                errors.append("No OPF package document found")
            htmls = [n for n in names if n.endswith((".xhtml", ".html", ".htm"))]
            if not htmls:
                warnings.append("No XHTML/HTML documents found")
    except zipfile.BadZipFile:
        errors.append("Not a valid ZIP/EPUB archive")
    except Exception as e:
        errors.append(str(e))

    return EpubValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)
