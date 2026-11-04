"""수집 → 정규화 → 캐시 → 집계.

게시 안전장치
  - allowlist 에 없는 컬럼은 정규화 단계에서 즉시 폐기한다(하류로 흐르지 않음).
  - 원본 캐시(cache/)와 게시물(output/)을 분리한다. 게시는 별도 명령이다.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import Settings

log = logging.getLogger(__name__)

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(value: object) -> str:
    """제어문자 제거 + 유니코드 정규화. HTML 이스케이프는 렌더러가 담당."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).strip()
    return _CTRL.sub("", text)


def _parse_date(value: str) -> pd.Timestamp | None:
    text = re.sub(r"[^0-9]", "", value or "")
    if len(text) != 8:
        return None
    try:
        return pd.Timestamp(datetime.strptime(text, "%Y%m%d"))
    except ValueError:
        return None


def _add_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """허가일자 → _허가일(datetime64) / _연도(Int64).

    값이 전부 비거나 형식이 틀려도 dtype 이 datetime64 로 고정되도록
    to_datetime 을 거친다(object dtype 이면 .dt 접근에서 예외가 난다).
    """
    if "허가일자" in df.columns:
        parsed = df["허가일자"].astype(str).map(_parse_date)
        df["_허가일"] = pd.to_datetime(parsed, errors="coerce")
        df["_연도"] = df["_허가일"].dt.year.astype("Int64")
    return df


# ---------------------------------------------------------------------
def normalize(records: list[dict], settings: Settings) -> pd.DataFrame:
    """원본 레코드 → 표준 컬럼 DataFrame. allowlist 밖 컬럼은 여기서 제거."""
    mapping = settings.fields
    allowed = set(settings.publish["allowed_columns"])

    derive_specs = list(settings.derive)
    # 파생의 근거 컬럼은 게시 대상이 아니어도 중간 단계에서는 보관해야 한다.
    needed = allowed | {d["source"] for d in derive_specs}

    rows: list[dict] = []
    dropped: set[str] = set()
    for rec in records:
        row: dict[str, object] = {}
        for src_key, value in rec.items():
            std = mapping.get(src_key)
            if std is None:
                dropped.add(src_key)
                continue
            if std not in needed:
                continue           # 매핑은 되지만 필요 없음 → 폐기
            row[std] = _clean(value)
        if row:
            rows.append(row)

    if dropped:
        log.info("매핑되지 않아 폐기한 원본 필드 %d종: %s",
                 len(dropped), ", ".join(sorted(dropped)[:12]))

    df = pd.DataFrame(rows)

    # ── 파생 컬럼 생성 ──────────────────────────────────────
    for spec in derive_specs:
        name, src = spec["name"], spec["source"]
        base = df[src].astype(str) if src in df.columns else pd.Series("", index=df.index)
        base = base.replace({"None": "", "nan": ""})
        out = pd.Series(spec.get("default", ""), index=df.index, dtype=object)
        assigned = pd.Series(False, index=df.index)
        for needle, label in spec.get("rules", []):
            hit = (base == "") if needle == "" else base.str.contains(needle, regex=False, na=False)
            out = out.mask(hit & ~assigned, label)
            assigned = assigned | hit
        df[name] = out
        log.info("파생 컬럼 '%s' 생성: %s", name, dict(out.value_counts().head(5)))

    # ── 코드값 라벨 치환 ────────────────────────────────────
    for col, table in (settings.labels or {}).items():
        if col in df.columns and table:
            df[col] = df[col].astype(str).replace({str(k): v for k, v in table.items()})

    for col in settings.publish["allowed_columns"]:
        if col not in df.columns:
            df[col] = ""
    df = df[settings.publish["allowed_columns"]].copy()

    df = _add_date_columns(df)

    before = len(df)
    if "허가번호" in df.columns:
        df = df.drop_duplicates(subset=["허가번호", "품목명"], keep="last")
    log.info("정규화 완료: %d행 (중복 %d행 제거)", len(df), before - len(df))
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------
def read_cache_meta(settings: Settings, name: str = "raw") -> dict:
    """캐시 메타데이터. 없거나 손상되면 빈 dict."""
    path = settings.cache_dir / f"{name}.meta.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_cache(df: pd.DataFrame, settings: Settings, name: str = "raw",
               extra_meta: dict | None = None) -> Path:
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    path = settings.cache_dir / f"{name}.parquet"
    try:
        df.to_parquet(path, index=False)
    except Exception as exc:            # pyarrow 미설치 등 — CSV 로 대체
        path.unlink(missing_ok=True)    # 반쯤 쓰인 파일이 남으면 다음 로드가 깨진다
        log.info("parquet 저장 불가(%s) → CSV 캐시를 사용합니다.", type(exc).__name__)
        path = settings.cache_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
    # 다른 형식의 옛 캐시가 남아 있으면 load_cache 가 그것을 먼저 읽을 수 있다.
    for suffix in (".parquet", ".csv"):
        stale = settings.cache_dir / f"{name}{suffix}"
        if stale != path:
            stale.unlink(missing_ok=True)
    meta = settings.cache_dir / f"{name}.meta.json"
    info = {"rows": int(len(df)), "fetched_at": datetime.now(timezone.utc).isoformat(),
            "columns": list(df.columns)}
    info.update(extra_meta or {})
    meta.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("캐시 저장: %s (%d행)", path.name, len(df))
    return path


def load_cache(settings: Settings, name: str = "raw") -> pd.DataFrame:
    readers = (
        (".parquet", lambda p: pd.read_parquet(p)),
        # utf-8-sig 로 저장했으므로 동일하게 읽어야 BOM 이 첫 컬럼명에 붙지 않는다.
        (".csv", lambda p: pd.read_csv(p, encoding="utf-8-sig", dtype=str).fillna("")),
    )
    for suffix, reader in readers:
        path = settings.cache_dir / f"{name}{suffix}"
        if not path.exists():
            continue
        try:
            df = reader(path)
        except Exception as exc:        # pyarrow 없음/손상 → 다음 형식으로 넘어간다
            log.warning("%s 읽기 실패(%s) — 다른 캐시 형식을 찾습니다.", path.name, type(exc).__name__)
            continue
        df = _add_date_columns(df)
        log.info("캐시 로드: %s (%d행)", path.name, len(df))
        return df
    hint = "먼저 `fetch` 를 실행하십시오."
    if name == "raw" and any((settings.cache_dir / f"sample{s}").exists() for s in (".parquet", ".csv")):
        hint += " 시험 수집분만 있다면 `build --cache sample` 로 미리보기를 만들 수 있습니다."
    raise FileNotFoundError(f"캐시({name})가 없습니다: {settings.cache_dir}. {hint}")


# ---------------------------------------------------------------------
def select(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """리포트 정의(keywords, match, exclude, filters)에 따라 부분집합을 고른다.

    match   = "contains"(기본) — 품목명에 키워드가 포함되면 선택
              "exact"         — 품목명이 키워드와 정확히 같을 때만 선택
    exclude = 포함되면 제외할 문자열 목록(match 와 무관하게 부분일치)

    공백은 비교 전에 모두 제거한다("치과용 임플란트" == "치과용임플란트").
    부분일치에서는 "치과용임플란트" 가 "치과용임플란트상부구조물" 까지 잡으므로,
    품목 단위 리포트는 exact 또는 exclude 로 범위를 명시해야 중복 집계를 막는다.
    """
    def _norm(s: pd.Series) -> pd.Series:
        return s.astype(str).str.replace(r"\s+", "", regex=True).str.lower()

    def _nk(words) -> list[str]:
        return [re.sub(r"\s+", "", str(w)).lower() for w in words if str(w).strip()]

    out = df
    name_cols = [c for c in ("품목명", "품목분류명") if c in out.columns]
    keywords = _nk(report.get("keywords") or [])
    match = str(report.get("match", "contains")).lower()
    if match not in ("contains", "exact"):
        raise ValueError(f"[{report.get('id', '?')}] match 는 'contains' 또는 'exact' 여야 합니다: {match!r}")

    if keywords:
        hit = pd.Series(False, index=out.index)
        for col in name_cols:
            norm = _norm(out[col])
            if match == "exact":
                hit |= norm.isin(keywords)
            else:
                hit |= norm.str.contains("|".join(map(re.escape, keywords)), regex=True, na=False)
        out = out[hit]

    excludes = _nk(report.get("exclude") or [])
    if excludes and name_cols:
        pattern = "|".join(map(re.escape, excludes))
        drop = pd.Series(False, index=out.index)
        for col in name_cols:
            drop |= _norm(out[col]).str.contains(pattern, regex=True, na=False)
        if drop.any():
            log.info("[%s] exclude 로 %d행 제외", report.get("id", "?"), int(drop.sum()))
        out = out[~drop]

    for col, values in (report.get("filters") or {}).items():
        if col in out.columns and values:
            out = out[out[col].isin(list(values))]

    log.info("[%s] 대상 %d행", report.get("id", "?"), len(out))
    if keywords and "품목명" in out.columns and len(out):
        # 범위 검증용: 실제로 잡힌 품목명 분포를 남긴다(의도치 않은 품목 혼입 확인).
        top = out["품목명"].astype(str).value_counts().head(10)
        log.info("[%s] 포함된 품목명 상위: %s", report.get("id", "?"),
                 ", ".join(f"{k}({v})" for k, v in top.items()))
    return out.reset_index(drop=True)


def summarize(df: pd.DataFrame, settings: Settings) -> dict:
    """차트/표에 필요한 집계를 한 번에 만든다."""
    top_n = int(settings.chart.get("top_n", 12))
    res: dict = {"total": int(len(df))}

    if "_연도" in df.columns:
        yearly = df.dropna(subset=["_연도"]).groupby("_연도").size().sort_index()
        res["yearly_trend"] = {int(k): int(v) for k, v in yearly.items()}
        if len(yearly):
            res["first_year"] = int(yearly.index.min())
            res["last_year"] = int(yearly.index.max())
            res["peak_year"] = int(yearly.idxmax())
            res["peak_count"] = int(yearly.max())

    # 집계 중인 해: 데이터의 마지막 연도가 생성 시점(KST)의 연도와 같으면 1년치가 아니다.
    # 추세 차트에서 다른 해와 같은 무게로 읽히지 않도록 표시한다.
    if "_허가일" in df.columns and df["_허가일"].notna().any():
        from .config import now_kst
        last = df["_허가일"].max()
        res["last_date"] = last.strftime("%Y-%m-%d")
        if last.year >= now_kst().year and last.month < 12:
            res["partial_year"] = {"year": int(last.year), "through_month": int(last.month)}

    for key, col in (("grade_mix", "등급"),
                     ("domestic_vs_import", "제조수입구분"),
                     ("status_mix", "품목상태")):
        if col in df.columns:
            counts = df[col].replace("", "미상").value_counts()
            res[key] = {str(k): int(v) for k, v in counts.items()}

    if res.get("status_mix"):
        total = sum(res["status_mix"].values()) or 1
        res["status_rows"] = [{"label": k, "count": v, "pct": round(v / total * 100, 1)}
                              for k, v in res["status_mix"].items()]

    if "업체명" in df.columns:
        comp = df["업체명"].replace("", "미상").value_counts()
        res["top_companies"] = {str(k): int(v) for k, v in comp.head(top_n).items()}
        res["company_count"] = int(comp.shape[0])
        if len(df):
            res["top3_share"] = round(float(comp.head(3).sum()) / len(df) * 100, 1)

    return res
