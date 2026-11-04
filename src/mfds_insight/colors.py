"""차트 색상.

색 체계(chart.scheme)
  accent  (기본) 색은 의미가 있을 때만 쓴다.
          - 지표가 하나인 차트(연도별·업체별): 기본색 한 가지
          - 항목 2개(제조·수입 등): 기본색 + 강조색
          - 항목 3개 이상(등급 등): 색각이상 안전 범주색(Okabe–Ito 기반, 대비 보정)
  rainbow 빨·주·노·초·파·남·보 계열(아래 rainbow()). 모든 차트에 항목별로 다른 색.
  palette chart.palette 를 순서대로 순환.

무지개 설계 원칙
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


BASE_COLOR = "#1F3864"      # 남색 — 사이트 머리글색과 통일 (흰 배경 대비 11.6:1)
ACCENT_COLOR = "#C2570C"    # 주황 — 2항목 비교의 두 번째 색, 취소·취하 (4.5:1)
# Okabe & Ito(2008) 색각이상 안전 팔레트를 흰 배경 대비 3.2:1 이상으로 명도 보정
CATEGORY_COLORS = ("#0072B2", "#D55E00", "#009E73", "#BD8300", "#CA73A3", "#1D96DB", "#9C920C")
SCHEMES = ("accent", "rainbow", "palette")


def scheme_of(settings) -> str:
    scheme = str(settings.chart.get("scheme", "accent")).lower()
    if scheme not in SCHEMES:
        raise ValueError(f"chart.scheme 은 {', '.join(SCHEMES)} 중 하나여야 합니다: {scheme!r}")
    return scheme


def series_colors(settings, n: int, kind: str = "category") -> list[str]:
    """차트에 쓸 n개 색.

    kind = "single"   : 지표 하나를 항목별로 나열한 차트(연도별, 업체별)
           "category" : 서로 다른 범주를 비교하는 차트(제조·수입, 등급)
    """
    scheme = scheme_of(settings)
    if scheme == "rainbow":
        return rainbow(n)
    if scheme == "palette":
        pal = list(settings.chart["palette"])
        return [pal[i % len(pal)] for i in range(n)]
    # accent
    base = settings.chart.get("base_color", BASE_COLOR)
    if kind == "single" or n <= 1:
        return [base] * n
    if n == 2:
        return [base, settings.chart.get("accent_color", ACCENT_COLOR)]
    cats = list(settings.chart.get("category_colors", CATEGORY_COLORS))
    return [cats[i % len(cats)] for i in range(n)]
