"""Image resize for EPUB size control (spec §12).

Technical judgment only — no AI. Keep aspect ratio.
"""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore


# Max edge in pixels; typical for ebook body images
DEFAULT_MAX_EDGE = 1600


def maybe_resize_image(
    path: str | Path,
    *,
    max_edge: int = DEFAULT_MAX_EDGE,
    output: str | Path | None = None,
) -> Path:
    """Resize in place (or to output) if either edge exceeds max_edge.

    Returns path written. No-op if Pillow missing or image already small.
    """
    path = Path(path)
    if Image is None:
        return path
    out = Path(output) if output else path
    try:
        with Image.open(path) as im:
            w, h = im.size
            if max(w, h) <= max_edge:
                if out != path:
                    im.save(out)
                return out
            scale = max_edge / max(w, h)
            nw, nh = int(w * scale), int(h * scale)
            resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
            # Preserve format when possible
            fmt = im.format or "JPEG"
            save_kw = {}
            if fmt.upper() in ("JPEG", "JPG"):
                save_kw["quality"] = 85
                save_kw["optimize"] = True
                if resized.mode in ("RGBA", "P"):
                    resized = resized.convert("RGB")
            resized.save(out, format=fmt, **save_kw)
            return out
    except Exception:
        return path


def resize_book_assets(
    assets: dict[str, str],
    *,
    max_edge: int = DEFAULT_MAX_EDGE,
) -> dict[str, str]:
    """Resize all existing asset files; returns same mapping."""
    for key, rel in list(assets.items()):
        p = Path(rel)
        if p.exists():
            maybe_resize_image(p, max_edge=max_edge)
    return assets
