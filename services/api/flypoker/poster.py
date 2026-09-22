from __future__ import annotations

from html import escape

from .models import TableSnapshot


def render_poster(slug: str, snapshot: TableSnapshot, winner: str) -> str:
    """Create a lightweight deterministic social poster without raster deps."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#101711"/><path d="M0 470 C260 390 900 560 1200 430V630H0Z" fill="#183524"/>
<text x="72" y="96" fill="#d9b56d" font-family="monospace" font-size="18" letter-spacing="5">FLY / POKER · ARCHIVED HAND</text>
<text x="72" y="230" fill="#f4eee2" font-family="Georgia,serif" font-size="86" font-style="italic">{escape(winner)} wins.</text>
<text x="72" y="296" fill="#9cb0a0" font-family="monospace" font-size="22">SIX CONNECTOMES · ONE TABLE · {escape(slug)}</text>
<text x="72" y="515" fill="#d9b56d" font-family="monospace" font-size="24">POT {snapshot.pot:,} CHIPS</text>
<text x="72" y="556" fill="#9cb0a0" font-family="monospace" font-size="18">THE WIRING IS REAL. THE POKER IS ENGINEERED.</text>
</svg>'''

