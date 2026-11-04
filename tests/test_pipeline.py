"""결함 2(날짜 공란 예외)와 결함 3(키워드 중첩 집계)."""
from __future__ import annotations

import pandas as pd
import pytest

from conftest import rec
from mfds_insight import pipeline as p


# ── 결함 2 ─────────────────────────────────────────────
def test_normalize_all_dates_blank(settings):
    df = p.normalize([rec(1, date=""), rec(2, date="잘못된값")], settings)
    assert len(df) == 2
    assert str(df["_허가일"].dtype).startswith("datetime64")
    assert df["_연도"].isna().all()


def test_normalize_mixed_dates(settings):
    df = p.normalize([rec(1, date="2021-03-04"), rec(2, date="")], settings)
    assert df["_연도"].tolist()[0] == 2021
    assert pd.isna(df["_연도"].tolist()[1])
    p.summarize(df, settings)   # 집계도 예외 없이 동작해야 한다


@pytest.mark.parametrize("pyarrow_ok", [True, False])
def test_cache_roundtrip_blank_dates(settings, monkeypatch, pyarrow_ok):
    if not pyarrow_ok:
        def _fail(*a, **k):
            raise ImportError("no pyarrow")
        monkeypatch.setattr(pd.DataFrame, "to_parquet", _fail)
    df = p.normalize([rec(1, date="")], settings)
    p.save_cache(df, settings)
    back = p.load_cache(settings)
    assert len(back) == 1 and back["_연도"].isna().all()


def test_save_cache_removes_stale_other_format(settings, monkeypatch):
    """CSV 로 저장할 때 옛 parquet 가 남아 있으면 load_cache 가 옛 것을 읽는 문제 방지."""
    settings.cache_dir.mkdir(parents=True)
    (settings.cache_dir / "raw.parquet").write_bytes(b"old")
    monkeypatch.setattr(pd.DataFrame, "to_parquet",
                        lambda *a, **k: (_ for _ in ()).throw(ImportError()))
    p.save_cache(p.normalize([rec(1)], settings), settings)
    assert not (settings.cache_dir / "raw.parquet").exists()


# ── 결함 3 ─────────────────────────────────────────────
# 2026-11-04 실제 게시 로그에서 확인된 품목명(부분일치 시 고정체 리포트에 섞였던 것 포함)
NAMES = ["치과용임플란트고정체", "치과용 임플란트 고정체", "치과용임플란트상부구조물",
         "치과용 임플란트 상부구조물", "치과용임플란트상부구조물 홀 충전재",
         "치과용임플란트기공재료", "치과용임플란트", "치과용임플란트가이드", "임시치과용임플란트",
         "치과용임플란트시스템", "치과용임플란트시술기구", "어버트먼트",
         "고주파자극기", "고주파 자극기", "의료용고주파온열기", "의료용 고주파 온열기", "개인용온열기"]


@pytest.fixture
def name_df():
    return pd.DataFrame({"품목명": NAMES})


def _report(settings, rid):
    return next(r for r in settings.reports if r["id"] == rid)


def test_fixture_report_exact_only(settings, name_df):
    got = p.select(name_df, _report(settings, "dental-implant"))["품목명"].tolist()
    assert got == ["치과용임플란트고정체", "치과용 임플란트 고정체"]


def test_abutment_report_excludes_hole_filler(settings, name_df):
    got = p.select(name_df, _report(settings, "dental-abutment"))["품목명"].tolist()
    assert got == ["치과용임플란트상부구조물", "치과용 임플란트 상부구조물"]


def test_rf_report_exact(settings, name_df):
    got = p.select(name_df, _report(settings, "rf-device"))["품목명"].tolist()
    assert got == ["고주파자극기", "고주파 자극기", "의료용고주파온열기", "의료용 고주파 온열기"]


def test_all_reports_use_exact_match(settings):
    assert all(r.get("match") == "exact" for r in settings.reports)


def test_fixture_and_abutment_reports_do_not_overlap(settings, name_df):
    a = set(p.select(name_df, _report(settings, "dental-implant"))["품목명"])
    b = set(p.select(name_df, _report(settings, "dental-abutment"))["품목명"])
    assert a and b and not (a & b)


def test_exact_match(name_df):
    r = {"id": "t", "keywords": ["치과용임플란"], "match": "exact"}   # 접두어는 정확 일치가 아님
    assert p.select(name_df, r).empty
    r["keywords"] = ["치과용임플란트"]                                    # 같은 이름 1건만, 고정체 등은 제외
    assert p.select(name_df, r)["품목명"].tolist() == ["치과용임플란트"]
    r["keywords"] = ["치과용임플란트고정체"]
    assert len(p.select(name_df, r)) == 2      # 공백 차이는 같은 것으로 본다


def test_invalid_match_value(name_df):
    with pytest.raises(ValueError):
        p.select(name_df, {"id": "t", "keywords": ["x"], "match": "regex"})


def test_keyword_regex_chars_are_literal():
    df = pd.DataFrame({"품목명": ["a.b", "axb"]})
    assert p.select(df, {"keywords": ["a.b"]})["품목명"].tolist() == ["a.b"]
