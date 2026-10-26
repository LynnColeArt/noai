"""Structure-preserving semantic evacuation. No security properties implied."""

from .transform import garble_html, garble_text

__all__ = ["garble_html", "garble_text"]
__version__ = "0.1.0"
