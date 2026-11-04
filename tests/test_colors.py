"""무지개 색상: 대비 기준, 반복 없음, Python ↔ JavaScript 결과 일치."""
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


def test_settings_palette_matches_rainbow7(settings):
    assert list(settings.chart["palette"]) == colors.rainbow(7)


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
