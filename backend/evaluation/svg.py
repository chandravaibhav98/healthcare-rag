"""Tiny dependency-free SVG line chart, so evaluation plots are deterministic text files
that render on GitHub and diff cleanly (no matplotlib in the runtime or CI images)."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

W, H, PAD = 640, 360, 48
COLORS = ("#2563eb", "#dc2626", "#16a34a", "#9333ea")


def line_chart(
    title: str,
    x: Sequence[float],
    series: dict[str, Sequence[float]],
    *,
    x_label: str,
    y_label: str,
    markers: dict[str, float] | None = None,
    y_max: float = 1.0,
) -> str:
    x0, x1 = min(x), max(x)

    def px(v: float) -> float:
        return PAD + (v - x0) / ((x1 - x0) or 1) * (W - 2 * PAD)

    def py(v: float) -> float:
        return H - PAD - v / y_max * (H - 2 * PAD)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="{W / 2}" y="20" text-anchor="middle" font-size="14">{escape(title)}</text>',
        f'<line x1="{PAD}" y1="{H - PAD}" x2="{W - PAD}" y2="{H - PAD}" stroke="#333"/>',
        f'<line x1="{PAD}" y1="{PAD}" x2="{PAD}" y2="{H - PAD}" stroke="#333"/>',
        f'<text x="{W / 2}" y="{H - 10}" text-anchor="middle">{escape(x_label)}</text>',
        f'<text x="14" y="{H / 2}" text-anchor="middle" transform="rotate(-90 14 {H / 2})">{escape(y_label)}</text>',
    ]
    for i in range(6):
        v = y_max * i / 5
        parts.append(f'<text x="{PAD - 6}" y="{py(v) + 4:.1f}" text-anchor="end">{v:.1f}</text>')
        parts.append(
            f'<line x1="{PAD}" y1="{py(v):.1f}" x2="{W - PAD}" y2="{py(v):.1f}" stroke="#eee"/>'
        )
    for v in x[:: max(1, len(x) // 7)]:
        parts.append(
            f'<text x="{px(v):.1f}" y="{H - PAD + 16}" text-anchor="middle">{v:.2f}</text>'
        )
    for ys, color in zip(series.values(), COLORS, strict=False):
        pts = " ".join(f"{px(a):.1f},{py(b):.1f}" for a, b in zip(x, ys, strict=True))
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>')
    for i, (name, color) in enumerate(zip(series, COLORS, strict=False)):
        parts.append(
            f'<text x="{W - PAD - 150}" y="{PAD + 16 * i}" fill="{color}">— {escape(name)}</text>'
        )
    for label, v in (markers or {}).items():
        parts.append(
            f'<line x1="{px(v):.1f}" y1="{PAD}" x2="{px(v):.1f}" y2="{H - PAD}" stroke="#999" stroke-dasharray="4 3"/>'
        )
        parts.append(f'<text x="{px(v) + 4:.1f}" y="{PAD + 12}" fill="#555">{escape(label)}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
