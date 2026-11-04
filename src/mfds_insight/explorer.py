"""브라우저 내 대화형 탐색기용 데이터셋 생성.

설계 원칙
  - 데이터는 정적 JSON 한 번만 내려받고, 이후 필터·집계·차트는 전부 클라이언트에서 처리한다.
  - 저카디널리티 컬럼은 사전(dictionary) 인코딩해 용량을 크게 줄인다.
  - 자바스크립트는 별도 파일로 분리한다 → CSP 를 script-src 'self' 로 유지할 수 있다.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import pandas as pd

from .colors import BASE_COLOR, scheme_of
from .config import Settings, now_kst, stamp_kst

log = logging.getLogger(__name__)


def _encode_column(series: pd.Series) -> dict:
    """고유값 비율이 낮으면 사전 인코딩, 높으면 원본 배열 그대로."""
    values = series.fillna("").astype(str)
    uniques = values.unique()
    if len(values) and len(uniques) / len(values) < 0.5:
        lookup = {v: i for i, v in enumerate(uniques)}
        return {"kind": "dict", "dict": list(uniques), "data": [lookup[v] for v in values]}
    return {"kind": "raw", "data": values.tolist()}


def scope_frame(df: pd.DataFrame, settings: Settings) -> tuple[pd.DataFrame, dict]:
    """탐색기에 실을 행을 고른다.

    scope = "reports"(기본): [[report]] 들이 선택하는 행의 합집합. 리포트와 똑같은
    select() 규칙을 쓰므로 탐색기 수치와 리포트 수치가 어긋나지 않는다.
    scope = "all": 전체 데이터.
    """
    from .pipeline import select

    scope = str(settings.explorer.get("scope", "reports")).lower()
    if scope not in ("reports", "all"):
        raise ValueError(f"explorer.scope 는 'reports' 또는 'all' 이어야 합니다: {scope!r}")
    if scope == "all":
        return df, {"kind": "all", "titles": [], "source_total": int(len(df))}
    rid = "__rid"
    tagged = df.assign(**{rid: range(len(df))})
    keep: set[int] = set()
    titles: list[str] = []
    for report in settings.reports:
        hit = select(tagged, report)
        if len(hit):
            keep.update(int(x) for x in hit[rid])
            titles.append(str(report.get("title", report.get("id", ""))))
    out = df.iloc[sorted(keep)].reset_index(drop=True)
    log.info("탐색기 수록 범위: 리포트 대상 품목 %d행 (전체 %d행 중)", len(out), len(df))
    return out, {"kind": "reports", "titles": titles, "source_total": int(len(df))}


def build_dataset(df: pd.DataFrame, settings: Settings, outdir: Path,
                  scope: dict | None = None) -> dict:
    cfg = settings.explorer
    cols = [c for c in cfg.get("columns", []) if c in df.columns]
    if not cols:
        cols = [c for c in settings.publish["allowed_columns"] if c in df.columns]

    max_rows = int(cfg.get("max_rows", 60000))
    work = df
    if len(work) > max_rows:
        # 최신 허가부터 남긴다. 잘렸다는 사실은 화면에 표시한다.
        if "_허가일" in work.columns:
            work = work.sort_values("_허가일", ascending=False)
        work = work.head(max_rows)
        log.warning("탐색기 데이터가 %d행으로 잘렸습니다(전체 %d행). "
                    "explorer.max_rows 를 조정하거나 리포트 범위를 좁히십시오.", max_rows, len(df))

    payload = {
        "generated": stamp_kst(),
        "total_all": int(len(df)),
        "truncated": bool(len(work) < len(df)),
        "scope": scope or {"kind": "all", "titles": [], "source_total": int(len(df))},
        "columns": cols,
        "facets": [c for c in cfg.get("facet_columns", []) if c in cols],
        "search": [c for c in cfg.get("search_columns", []) if c in cols],
        "merge_spacing": [c for c in cfg.get("merge_spacing_columns", []) if c in cols],
        "year_column": "_연도" if "_연도" in work.columns else None,
        # 색상 체계(리포트와 동일 설정). rainbow 는 explorer.js 가 같은 알고리즘으로 생성한다.
        "colors": {"scheme": scheme_of(settings),
                   "palette": list(settings.chart.get("palette", [])),
                   "base": settings.chart.get("base_color", BASE_COLOR)},
        "encoded": {c: _encode_column(work[c]) for c in cols},
    }
    # 집계 중인 해(리포트와 같은 규칙). 탐색기 연도 차트에 빗금·주석으로 표시한다.
    if "_허가일" in work.columns and work["_허가일"].notna().any():
        last = work["_허가일"].max()
        if last.year >= now_kst().year and last.month < 12:
            payload["partial_year"] = {"year": int(last.year), "through_month": int(last.month)}
    if payload["year_column"]:
        years = work["_연도"]
        payload["encoded"]["_연도"] = {
            "kind": "raw",
            "data": [int(y) if pd.notna(y) else None for y in years],
        }

    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "data.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_mb = path.stat().st_size / 1024 / 1024
    log.info("탐색기 데이터 생성: %s (%d행, %.1f MB)", path.name, len(work), size_mb)
    if size_mb > 8:
        log.warning("데이터가 %.1f MB 로 큽니다. 모바일 접속이 느려질 수 있습니다. "
                    "explorer.max_rows 를 줄이거나 컬럼을 줄이십시오.", size_mb)
    return {"rows": int(len(work)), "size_mb": round(size_mb, 2),
            "scope": payload["scope"]}


def copy_assets(settings: Settings, outdir: Path) -> None:
    src = settings.root / "static" / "explorer.js"
    if src.exists():
        shutil.copy2(src, outdir / "explorer.js")
    else:
        log.warning("static/explorer.js 가 없습니다.")
