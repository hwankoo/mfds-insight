"""차트 색상: 무지개(빨·주·노·초·파·남·보) 계열.

설계 원칙
  - 색상각(hue)은 무지개 7색을 기준점으로 삼고, 항목이 많으면 그 사이를 보간한다.
    → 항목 수가 몇 개든 같은 차트 안에서 색이 반복되지 않는다.
  - 각 색은 흰 배경 대비 MIN_CONTRAST 이상이 될 때까지 명도를 낮춘다
    (WCAG 2.1 1.4.11 그래픽 요소 3:1). 그래서 노랑·연두는 황토·올리브 톤이 된다.
  - 같은 알고리즘을 static/explorer.js 에도 구현해 리포트와 탐색기 색이 일치한다.
    값을 바꾸면 양쪽을 함께 바꾸십시오(tests/test_colors.py 가 일치 여부를 검사).
"""
from __future__ import annotations

import colorsys

ANCHOR_HUES = (0, 28, 48, 130, 205, 235, 280)   # 빨 주 노 초 파 남 보 (도)
SATURATION = 0.68
START_LIGHTNESS = 0.50
MIN_CONTRAST = 3.2                               # 3:1 기준에 여유를 둔 값


def _luminance(rgb: tuple[float, float, float]) -> float:
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast_on_white(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    rgb = tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 1.05 / (_luminance(rgb) + 0.05)


def _hue_at(t: float) -> float:
    """t∈[0,1] → 무지개 기준점 사이를 선형 보간한 색상각."""
    x = t * (len(ANCHOR_HUES) - 1)
    i = min(int(x), len(ANCHOR_HUES) - 2)
    f = x - i
    return ANCHOR_HUES[i] + (ANCHOR_HUES[i + 1] - ANCHOR_HUES[i]) * f


def _to_hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(round(x * 255) for x in rgb)


def rainbow(n: int) -> list[str]:
    """빨강→보라 순서로 n개 색. 모든 색이 흰 배경 대비 MIN_CONTRAST 이상."""
    out: list[str] = []
    for i in range(max(0, n)):
        hue = _hue_at(i / (n - 1) if n > 1 else 0) / 360
        steps = 0
        while True:
            hx = _to_hex(colorsys.hls_to_rgb(hue, START_LIGHTNESS - steps * 0.005, SATURATION))
            if contrast_on_white(hx) >= MIN_CONTRAST or steps >= 60:
                break
            steps += 1
        out.append(hx)
    return out


def series_colors(settings, n: int) -> list[str]:
    """차트에 쓸 n개 색. chart.scheme = "rainbow"(기본) | "palette"(설정 팔레트 순환)."""
    scheme = str(settings.chart.get("scheme", "rainbow")).lower()
    if scheme == "palette":
        pal = list(settings.chart["palette"])
        return [pal[i % len(pal)] for i in range(n)]
    return rainbow(n)
