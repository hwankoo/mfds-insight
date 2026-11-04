"""차트 색상: 기본(accent) 규칙, 무지개 옵션의 대비·반복 없음, Python ↔ JavaScript 일치."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from mfds_insight import colors

JS = Path(__file__).resolve().parents[1] / "static" / "explorer.js"


@pytest.mark.parametrize("n", [1, 2, 3, 7, 12, 26, 40])
def test_rainbow_contrast_and_unique(n):
    pal = colors.rainbow(n)
    assert len(pal) == n and len(set(pal)) == n               # 같은 차트 안에서 색 반복 없음
    assert all(colors.contrast_on_white(c) >= 3.0 for c in pal)  # WCAG 1.4.11


def test_rainbow_order_red_to_violet():
    import colorsys
    hues = [colorsys.rgb_to_hls(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0] * 360
            for c in colors.rainbow(7)]
    assert hues[0] < 10 and 260 < hues[-1] < 300
    assert hues == sorted(hues)


def test_default_scheme_is_accent(settings):
    assert colors.scheme_of(settings) == "accent"


def test_accent_scheme_rules(settings):
    sc = colors.series_colors
    assert sc(settings, 26, kind="single") == [colors.BASE_COLOR] * 26     # 연도·업체: 단색
    assert sc(settings, 2) == [colors.BASE_COLOR, colors.ACCENT_COLOR]      # 제조·수입
    four = sc(settings, 4)                                                  # 등급 등
    assert four == list(colors.CATEGORY_COLORS[:4]) and len(set(four)) == 4


@pytest.mark.parametrize("c", [colors.BASE_COLOR, colors.ACCENT_COLOR, *colors.CATEGORY_COLORS])
def test_accent_colors_contrast(c):
    assert colors.contrast_on_white(c) >= 3.0


def test_rainbow_option_still_available(settings):
    s = replace(settings, chart=dict(settings.chart, scheme="rainbow"))
    assert colors.series_colors(s, 12, kind="single") == colors.rainbow(12)


def test_invalid_scheme(settings):
    s = replace(settings, chart=dict(settings.chart, scheme="neon"))
    with pytest.raises(ValueError):
        colors.series_colors(s, 3)


def test_scheme_palette_fallback(settings):
    s = replace(settings, chart=dict(settings.chart, scheme="palette", palette=["#111111", "#222222"]))
    assert colors.series_colors(s, 3) == ["#111111", "#222222", "#111111"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_js_rainbow_matches_python():
    """explorer.js 의 색 생성 함수만 떼어 node 로 실행해 비교한다."""
    src = JS.read_text(encoding="utf-8")
    start = src.index("  var ANCHOR_HUES")
    end = src.index("  function seriesColors")
    code = src[start:end] + "\nconsole.log(JSON.stringify([1,2,7,12,26].map(rainbow)));"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [colors.rainbow(n) for n in (1, 2, 7, 12, 26)]


def test_js_and_python_share_constants():
    src = JS.read_text(encoding="utf-8")
    hues = re.search(r"ANCHOR_HUES = \[([^\]]+)\]", src).group(1)
    assert tuple(int(x) for x in hues.split(",")) == colors.ANCHOR_HUES
    assert f"SAT = {colors.SATURATION}" in src and f"MIN_CONTRAST = {colors.MIN_CONTRAST}" in src
