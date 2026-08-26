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
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from jinja2 import Environment, FileSystemLoader

from .config import Settings

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


def _fig(settings: Settings):
    return plt.subplots(
        figsize=(float(settings.chart["width_in"]), float(settings.chart["height_in"])),
        dpi=int(settings.chart["dpi"]),
    )


def _finish(fig, ax, path: Path, title: str) -> str:
    ax.set_title(title, fontsize=13, pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg", transparent=False)
    plt.close(fig)
    return path.name


# ---------------------------------------------------------------------
def draw_charts(stats: dict, settings: Settings, outdir: Path, wanted: list[str]) -> dict[str, str]:
    _ensure_font(settings)
    palette = list(settings.chart["palette"])
    made: dict[str, str] = {}

    if "yearly_trend" in wanted and stats.get("yearly_trend"):
        data = stats["yearly_trend"]
        fig, ax = _fig(settings)
        ax.bar(list(data.keys()), list(data.values()), color=palette[0])
        ax.set_xlabel("허가 연도"); ax.set_ylabel("허가 건수")
        ax.grid(axis="y", alpha=0.25)
        made["yearly_trend"] = _finish(fig, ax, outdir / "yearly_trend.svg", "연도별 허가 건수")

    if "grade_mix" in wanted and stats.get("grade_mix"):
        data = stats["grade_mix"]
        fig, ax = _fig(settings)
        ax.pie(list(data.values()), labels=list(data.keys()), autopct="%1.1f%%",
               colors=palette[: len(data)], startangle=90,
               wedgeprops={"edgecolor": "white", "linewidth": 1.2})
        ax.axis("equal")
        made["grade_mix"] = _finish(fig, ax, outdir / "grade_mix.svg", "등급 분포")

    if "status_mix" in wanted and stats.get("status_mix"):
        data = stats["status_mix"]
        fig, ax = _fig(settings)
        ax.pie(list(data.values()), labels=list(data.keys()), autopct="%1.1f%%",
               colors=palette[: len(data)], startangle=90,
               wedgeprops={"edgecolor": "white", "linewidth": 1.2})
        ax.axis("equal")
        made["status_mix"] = _finish(fig, ax, outdir / "status_mix.svg", "품목 상태 (정상 · 취소취하)")

    if "top_companies" in wanted and stats.get("top_companies"):
        data = stats["top_companies"]
        names = list(data.keys())[::-1]; vals = list(data.values())[::-1]
        fig, ax = _fig(settings)
        ax.barh(names, vals, color=palette[1])
        ax.set_xlabel("허가 건수")
        ax.grid(axis="x", alpha=0.25)
        made["top_companies"] = _finish(fig, ax, outdir / "top_companies.svg", "업체별 허가 건수 (상위)")

    if "domestic_vs_import" in wanted and stats.get("domestic_vs_import"):
        data = stats["domestic_vs_import"]
        fig, ax = _fig(settings)
        ax.bar(list(data.keys()), list(data.values()), color=palette[:len(data)], width=0.5)
        ax.set_ylabel("허가 건수")
        ax.grid(axis="y", alpha=0.25)
        made["domestic_vs_import"] = _finish(fig, ax, outdir / "domestic_vs_import.svg", "제조 · 수입 구분")

    log.info("차트 %d종 생성", len(made))
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


def render_report(report: dict, df, stats: dict, charts: dict[str, str],
                  settings: Settings, outdir: Path) -> Path:
    cols = list(settings.publish["allowed_columns"])
    limit = int(settings.publish.get("max_rows_in_table", 200))

    table_df = df[cols].copy()
    if "_허가일" in df.columns:
        table_df = table_df.assign(_s=df["_허가일"]).sort_values("_s", ascending=False).drop(columns="_s")
    rows = table_df.head(limit).values.tolist()

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
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
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
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
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
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "index.html"
    path.write_text(html, encoding="utf-8")
    log.info("탐색기 페이지 생성: %s", path)
    return path
