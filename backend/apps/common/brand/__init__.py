"""Brand assets and colours shared by every generated file (report Excel/PDF, receipts).

Palette: justSmile_color_palette.jpg (rust A74D20, orange FBA023, black 050404, golden yellow FBBE25, flame F36A21).
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGO_ON_DARK = HERE / "logo-on-dark.png"  # white lettering, yellow smile: for dark bands
LOGO_INK = HERE / "logo-ink.png"  # all ink: for white paper

INK = "050404"
DEEP = "592911"
OLIVE = "A74D20"
MOSS = "FBA023"
YELLOW = "FBBE25"
YELLOW_SOFT = "FFF4D6"
PAPER_TINT = "FFFAF3"
LINE = "ECE3DA"
MUTED = "6E5A55"
TEXT = "271F1F"
GOOD = "067647"
BAD = "B42318"
TAGLINE = "Printing Press · Photography & Videography · Clothing"
