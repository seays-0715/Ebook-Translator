"""UI mixin — Convert page (preview + ops)."""
from __future__ import annotations

from src.ui._mix_convert_preview import ConvertPreviewMixin
from src.ui._mix_convert_ops import ConvertOpsMixin


class ConvertMixin(ConvertPreviewMixin, ConvertOpsMixin):
    """Combined convert-page mixin."""
    pass
