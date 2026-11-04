"""정적 산출물 생성 — SVG 차트 + HTML/CSV/JSON.

보안 원칙
  - Jinja2 autoescape 강제. 템플릿에 |safe 를 쓰지 않는다.
  - 외부 스크립트/폰트/추적기를 일절 로드하지 않는다(서드파티 의존 0).
  - 출력은 순수 정적 파일이다. 서버·DB·런타임 사용자 입력이 없어 주입 표면이 없다.
"""
from __future__ import annotations

import csv
import json
import logging
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter, MaxNLocator
from jinja2 import Environment, FileSystemLoader

from .colors import series_colors
from .config import Settings, stamp_kst

log = logging.getLogger(__name__)
_FONT_READY = False


def _ensure_font(settings: Settings) -> None:
    global _FONT_READY
    if _FONT_READY:
        return
    want = settings.chart.get("font", "NanumGothic")
    available = {f.name for f in font_manager.fontManager.ttflist}
    for cand in (want, "NanumGothic", "Malgun Gothic", "AppleGothic", "Noto Sans CJK KR", "DejaVu Sans"):
        if cand in available:
            plt.rcParams["font.family"] = cand
            if cand != want:
                log.warning("한글 폰트 '%s' 미설치 → '%s' 로 대체합니다.", want, cand)
            break
    else:
        log.warning("한글 폰트를 찾지 못했습니다. 차트의 한글이 깨질 수 있습니다.")
    plt.rcParams["axes.unicode_minus"] = False
    _FONT_READY = True


# ---------------------------------------------------------------------
# 차트 변형(variant)
#   <img> 로 넣은 SVG 는 화면 폭에 맞춰 통째로 확대·축소되므로 글자도 같이 줄어든다.
#   그래서 화면 크기별로 따로 그려 <picture> 로 고른다(자바스크립트 불필요).
#   실효 글자 크기(px) = 글자pt × 96/72 × (표시폭 / 원본폭)
#     lg: 9in(864px) · 12pt(16px) → 표시폭 648px 이상이면 12px 이상 유지
#     sm: 4.2in(403px) · 11.5pt(15.3px) → 390px 화면(표시폭 약 350px)에서 약 12.8px
#   lg 는 화면 폭 690px 이상(CHART_BREAKPOINT_PX)에서만 쓰인다.
# ---------------------------------------------------------------------
CHART_BREAKPOINT_PX = 690
VARIANTS = {
    "lg": {"suffix": "",    "width_in": 9.0, "font_pt": 12.0, "bar_h_in": 4.2,
           "row_in": 0.36, "max_xlabels": 14, "name_chars": 30, "name_lines": 1},
    "sm": {"suffix": "_sm", "width_in": 4.2, "font_pt": 11.5, "bar_h_in": 3.4,
           "row_in": 0.50, "max_xlabels": 6,  "name_chars": 15, "name_lines": 2},
}


def _variant(settings: Settings, key: str) -> dict:
    v = dict(VARIANTS[key])
    if key == "lg":                                   # 설정값이 있으면 데스크톱 폭에 반영
        v["width_in"] = float(settings.chart.get("width_in", v["width_in"]))
    return v


def _fig(settings: Settings, v: dict, height_in: float):
    plt.rcParams.update({
        "font.size": v["font_pt"], "axes.labelsize": v["font_pt"],
        "xtick.labelsize": v["font_pt"], "ytick.labelsize": v["font_pt"],
        "axes.edgecolor": "#9aa3ae", "axes.labelcolor": "#2b3440",
        "xtick.color": "#2b3440", "ytick.color": "#2b3440",
    })
    return plt.subplots(figsize=(v["width_in"], height_in), dpi=int(settings.chart.get("dpi", 110)))


def _finish(fig, ax, path: Path) -> str:
    # 차트 제목은 HTML 의 <h2> 가 맡는다(중복 제거 → 그림 영역 확보).
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout(pad=0.6)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg", transparent=False, metadata={"Date": None})
    plt.close(fig)
    return path.name


def _shorten(name: str, chars: int, lines: int) -> str:
    """긴 업체명을 줄바꿈/말줄임. 원문은 표와 CSV 에 그대로 남는다."""
    name = str(name)
    if len(name) <= chars:
        return name
    parts = textwrap.wrap(name, chars, break_long_words=True) or [name]
    if len(parts) > lines:
        parts = parts[:lines]
        parts[-1] = parts[-1][: max(1, chars - 1)].rstrip() + "…"
    return "\n".join(parts)


def _year_chart(stats: dict, settings: Settings, v: dict, path: Path) -> str:
    data = stats["yearly_trend"]
    years, counts = list(data.keys()), list(data.values())
    partial = (stats.get("partial_year") or {}).get("year")
    fig, ax = _fig(settings, v, v["bar_h_in"])
    # 연도 순서대로 무지개 그라데이션. 집계 중인 해는 같은 색에 흰 빗금(색 외 구분 수단).
    colors = series_colors(settings, len(years))
    bars = ax.bar(years, counts, color=colors, width=0.72)
    for b, y in zip(bars, years):
        if y == partial:
            b.set_hatch("///"); b.set_edgecolor("white"); b.set_linewidth(0); b.set_alpha(0.85)
    step = next(k for k in (1, 2, 5, 10, 20, 50) if len(years) / k <= v["max_xlabels"])
    ticks = [y for y in years if y % step == 0] or years[:1]
    ax.set_xticks(ticks, [f"{t}*" if t == partial else str(t) for t in ticks])
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.grid(axis="y", color="#e2e6ec", linewidth=1)
    ax.set_axisbelow(True)
    ax.set_ylabel("허가 건수")
    return _finish(fig, ax, path)


def _hbar_chart(data: dict, settings: Settings, v: dict, colors, path: Path,
                show_pct: bool = False) -> str:
    """가로 막대. 항목 수에 비례해 높이가 늘어나므로 항목이 많아도 글자가 줄지 않는다.

    좁은 화면(sm)에서 이름이 긴 경우에는 이름을 막대 위 줄에 따로 배치해
    막대가 화면 폭 전체를 쓰게 한다(왼쪽 이름 칸이 폭의 절반을 차지하지 않도록).
    """
    keys, vals = list(data.keys()), list(data.values())
    total = sum(vals) or 1
    vmax = max(vals) if vals else 1
    if isinstance(colors, str):
        colors = [colors] * len(vals)
    colors = [colors[i % len(colors)] for i in range(len(vals))]
    labels = [f"{val:,}" + (f" ({val / total * 100:.1f}%)" if show_pct else "") for val in vals]
    stacked = v["suffix"] == "_sm" and max(len(str(k)) for k in keys) > 6

    if stacked:
        # 한 항목 = [이름 줄] + [막대 줄]. 위에서부터 순서대로.
        row = 0.62
        fig, ax = _fig(settings, v, 0.15 + row * len(keys))
        for i, (k, val, c, lab) in enumerate(zip(keys, vals, colors, labels)):
            y = -i
            ax.text(0, y + 0.34, _shorten(k, 26, 1), ha="left", va="bottom",
                    fontsize=v["font_pt"], color="#16202e")
            ax.barh(y, val, color=c, height=0.36, align="center")
            ax.text(val + vmax * 0.02, y, lab, va="center", ha="left",
                    fontsize=v["font_pt"], color="#2b3440")
        ax.set_ylim(-len(keys) + 0.5, 0.95)
        ax.yaxis.set_visible(False)
        ax.spines["left"].set_visible(False)
    else:
        names = [_shorten(k, v["name_chars"], v["name_lines"]) for k in keys]
        lines = max(n.count("\n") + 1 for n in names)
        row = v["row_in"] * (1 + 0.45 * (lines - 1))
        fig, ax = _fig(settings, v, 0.35 + row * len(names))
        ax.barh(names[::-1], vals[::-1], color=colors[::-1], height=0.62)
        for i, lab in enumerate(labels[::-1]):
            ax.text(vals[::-1][i] + vmax * 0.015, i, lab, va="center", ha="left",
                    fontsize=v["font_pt"], color="#2b3440")
        ax.tick_params(axis="y", length=0, pad=6)

    ax.set_xlim(0, vmax * (1.36 if show_pct else 1.2))
    ax.xaxis.set_visible(False)                      # 값은 막대 끝에 직접 표기
    ax.spines["bottom"].set_visible(False)
    return _finish(fig, ax, path)


# ---------------------------------------------------------------------
def draw_charts(stats: dict, settings: Settings, outdir: Path, wanted: list[str]) -> dict[str, dict]:
    """차트별로 {"lg": 파일명, "sm": 파일명} 을 돌려준다.

    status_mix 는 그래프 대신 템플릿에서 숫자로 표시하므로 여기서 그리지 않는다.
    """
    _ensure_font(settings)
    made: dict[str, dict] = {}

    jobs = []
    if "yearly_trend" in wanted and stats.get("yearly_trend"):
        jobs.append(("yearly_trend", lambda v, p: _year_chart(stats, settings, v, p)))
    if "top_companies" in wanted and stats.get("top_companies"):
        jobs.append(("top_companies", lambda v, p: _hbar_chart(
            stats["top_companies"], settings, v,
            series_colors(settings, len(stats["top_companies"])), p)))
    for key in ("domestic_vs_import", "grade_mix"):
        if key in wanted and stats.get(key):
            jobs.append((key, lambda v, p, k=key: _hbar_chart(
                stats[k], settings, v, series_colors(settings, len(stats[k])), p, show_pct=True)))

    for name, fn in jobs:
        made[name] = {}
        for key in VARIANTS:
            v = _variant(settings, key)
            made[name][key] = fn(v, outdir / f"{name}{v['suffix']}.svg")

    log.info("차트 %d종 × %d변형 생성", len(made), len(VARIANTS))
    return made


# ---------------------------------------------------------------------
def _env(settings: Settings) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(settings.template_dir)),
        # 주의: select_autoescape 는 확장자로 판단하므로 '.html.j2' 를 놓친다.
        # 모든 템플릿이 HTML을 생성하므로 무조건 켠다. 절대 False 로 바꾸지 말 것.
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


DATE_COLS = {"허가일자", "취소취하일자", "변경일자"}
NOWRAP_COLS = DATE_COLS | {"허가번호", "제조수입구분", "품목상태", "추적관리대상"}


def fmt_cell(col: str, value) -> str:
    """표 셀 표시값. 20260215 → 2026-02-15 (8자리 숫자일 때만)."""
    text = "" if value is None else str(value)
    if col in DATE_COLS and len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def render_report(report: dict, df, stats: dict, charts: dict[str, dict],
                  settings: Settings, outdir: Path) -> Path:
    cols = list(settings.publish["allowed_columns"])
    limit = int(settings.publish.get("max_rows_in_table", 200))

    table_df = df[cols].copy()
    if "_허가일" in df.columns:
        table_df = table_df.assign(_s=df["_허가일"]).sort_values("_s", ascending=False).drop(columns="_s")
    # 화면 표시용 가공(날짜 구분자). 내려받기 CSV/JSON 은 원본 값을 유지한다.
    rows = [[fmt_cell(c, v) for c, v in zip(cols, r)] for r in table_df.head(limit).values.tolist()]

    if settings.publish.get("export_csv", True):
        csv_path = outdir / f"{report['slug']}.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh); w.writerow(cols); w.writerows(table_df.values.tolist())
    if settings.publish.get("export_json", True):
        (outdir / f"{report['slug']}.json").write_text(
            json.dumps({"report": report["id"], "title": report["title"],
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "stats": stats, "columns": cols,
                        "rows": table_df.values.tolist()},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")

    html = _env(settings).get_template("report.html.j2").render(
        site=settings.site, report=report, stats=stats, charts=charts,
        columns=cols, rows=rows, total_rows=len(table_df), shown_rows=len(rows),
        nowrap=[c in NOWRAP_COLS for c in cols], breakpoint=CHART_BREAKPOINT_PX,
        show_status="status_mix" in (report.get("charts") or []),
        generated=stamp_kst(),
    )
    path = outdir / "index.html"
    path.write_text(html, encoding="utf-8")
    log.info("리포트 생성: %s", path)
    return path


def render_index(entries: list[dict], settings: Settings,
                 explorer_info: dict | None = None) -> Path:
    html = _env(settings).get_template("index.html.j2").render(
        site=settings.site, entries=entries,
        explorer=explorer_info,
        explorer_slug=settings.explorer.get("slug", "explore"),
        generated=stamp_kst(),
    )
    path = settings.output_dir / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    log.info("목차 생성: %s", path)
    return path


def render_explorer(settings: Settings, outdir: Path, info: dict) -> Path:
    """대화형 탐색기 페이지를 생성한다(데이터는 explorer.build_dataset 이 별도 생성)."""
    html = _env(settings).get_template("explorer.html.j2").render(
        site=settings.site, info=info,
        generated=stamp_kst(),
    )
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "index.html"
    path.write_text(html, encoding="utf-8")
    log.info("탐색기 페이지 생성: %s", path)
    return path
