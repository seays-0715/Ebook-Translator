"""Regression: UI modules must not import removed language constants.

Previous Windows EXE failed at startup with:
  ImportError: cannot import name '_SOURCE_LANG_CODES' from 'src.ui._common'

Language codes come only from src.core.languages registry.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "src" / "ui" / "_common.py"
CONVERT = ROOT / "src" / "ui" / "_mix_convert.py"
FORBIDDEN = {"_SOURCE_LANG_CODES", "_TARGET_LANG_CODES"}


def _imported_names_from_common(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "src.ui._common" or mod.endswith("._common") or mod == "_common":
                for alias in node.names:
                    names.add(alias.name)
    return names


def test_no_stale_source_target_lang_imports():
    """Any UI file importing from _common must not request removed constants."""
    ui_dir = ROOT / "src" / "ui"
    offenders: list[str] = []
    for path in sorted(ui_dir.glob("*.py")):
        got = _imported_names_from_common(path) & FORBIDDEN
        if got:
            offenders.append(f"{path.name}: {sorted(got)}")
    assert not offenders, "stale language constant imports:\n" + "\n".join(offenders)


def test_common_does_not_export_legacy_lang_lists():
    tree = ast.parse(COMMON.read_text(encoding="utf-8"))
    assigned = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigned.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigned.add(node.target.id)
    assert "_SOURCE_LANG_CODES" not in assigned
    assert "_TARGET_LANG_CODES" not in assigned
    assert "_INTERFACE_LANG_CODES" in assigned
    assert "_CONVERSION_MODE_CODES" in assigned


def test_convert_mixin_source_parses_and_has_no_forbidden_imports():
    """Parse convert mixin without requiring Tk (Linux headless CI)."""
    src = CONVERT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert tree is not None
    forbidden = _imported_names_from_common(CONVERT) & FORBIDDEN
    assert not forbidden


def test_settings_separates_backend_and_model_identifier():
    from src.core.settings import AIConnectionSettings
    s = AIConnectionSettings(model="local", model_identifier="qwen3:8b")
    assert s.model == "local"
    assert s.model_identifier == "qwen3:8b"
    assert s.model != s.model_identifier


def test_interface_language_only_two_codes():
    from src.ui._common import _INTERFACE_LANG_CODES
    assert _INTERFACE_LANG_CODES == ("en", "zh-Hant")
    assert "" not in _INTERFACE_LANG_CODES
    assert "auto" not in _INTERFACE_LANG_CODES
