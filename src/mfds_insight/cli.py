"""명령행 진입점.

  probe    API 응답 구조 확인 (필드 매핑 잡을 때)
  dump     API 원본 레코드를 가공 없이 저장 (데이터 점검용)
  fetch    원본 수집 → cache/ 저장
  build    캐시 → output/ 정적 사이트 생성
  run      fetch + build
  check    설정·보안 점검
  serve    생성된 사이트를 로컬에서 확인 (탐색기는 이 방법으로 열어야 함)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

from . import config as cfgmod
from .config import ConfigError
from .pipeline import normalize, save_cache, load_cache, read_cache_meta, select, summarize
from .render import draw_charts, render_report, render_index


class IntegrityError(RuntimeError):
    """수집 결과가 불완전해 게시하면 안 되는 상태."""


def check_completeness(run: dict, previous: dict, settings) -> list[str]:
    """수집 완전성 검사. 위반 사유 목록을 돌려준다(빈 목록이면 통과).

    1) totalCount 대비 수집 건수 부족, 또는 max_pages 상한 도달
    2) 직전 정식 수집 대비 건수가 api.max_row_drop_pct(기본 5%) 넘게 감소
       — 허가 목록은 누적 데이터라 정상적으로는 거의 줄지 않는다.
    """
    problems: list[str] = []
    total, fetched = run.get("total_count"), int(run.get("fetched", 0))
    if run.get("stop_reason") == "max_pages":
        problems.append(f"max_pages 상한에서 중단됨({fetched}건 수집). api.max_pages 를 늘리십시오.")
    if total is not None and fetched < total:
        problems.append(f"totalCount {total}건 중 {fetched}건만 수집됨({total - fetched}건 누락).")
    elif total is None and not run.get("complete", False):
        problems.append(f"totalCount 를 알 수 없고 수집이 정상 종료되지 않음({run.get('stop_reason')}).")

    prev = previous.get("fetched", previous.get("rows"))
    drop_pct = float(settings.api.get("max_row_drop_pct", 5))
    if prev and not previous.get("sample"):
        prev = int(prev)
        if fetched < prev * (1 - drop_pct / 100):
            problems.append(
                f"직전 수집 {prev}건 대비 {fetched}건으로 {100 * (prev - fetched) / prev:.1f}% 감소"
                f"(허용 {drop_pct:g}%). API 범위·필터 변경 여부를 확인하십시오.")
    return problems


def _fetch(settings, sample: int | None = None, allow_incomplete: bool = False) -> str:
    """수집 후 캐시에 저장하고 캐시 이름을 돌려준다.

    --sample 수집은 정식 캐시(raw)를 덮어쓰지 않도록 'sample' 캐시에 저장한다.
    정식 수집은 완전성 검사를 통과해야만 raw 캐시를 교체한다(실패 시 기존 캐시 유지).
    """
    from .client import MfdsClient
    records: list[dict] = []
    with MfdsClient(settings) as client:
        for rec in client.iter_records():
            records.append(rec)
            if sample and len(records) >= sample:
                break
        run = dict(client.last_run)
    if not records:
        raise SystemExit("수집된 레코드가 없습니다. `probe` 로 응답 구조를 확인하십시오.")

    meta = {"source_url": client.full_url(), **run, "sample": bool(sample)}
    if sample:
        save_cache(normalize(records, settings), settings, name="sample", extra_meta=meta)
        print(f"\n시험 수집 {len(records)}건 → cache/sample.* (정식 캐시 raw 는 그대로 둡니다)")
        print("미리보기:  python run.py build --cache sample")
        return "sample"

    problems = check_completeness(run, read_cache_meta(settings, "raw"), settings)
    if problems:
        for p in problems:
            print(f"  [무결성] {p}", file=sys.stderr)
        if not allow_incomplete:
            raise IntegrityError(
                "수집 결과가 완전성 검사를 통과하지 못해 캐시를 갱신하지 않았습니다. "
                "원인을 확인한 뒤 다시 실행하거나, 의도한 것이면 --allow-incomplete 를 지정하십시오.")
        print("  [경고] --allow-incomplete 지정 — 불완전한 데이터로 캐시를 갱신합니다.", file=sys.stderr)
        meta["integrity_override"] = problems
    save_cache(normalize(records, settings), settings, name="raw", extra_meta=meta)
    return "raw"


def _dump(settings, limit: int | None) -> None:
    """API 원본 레코드를 가공 없이 그대로 저장한다(필드 매핑·allowlist 적용 안 함).

    데이터 점검용이다. 산출물은 cache/ 에만 두며 output/ 으로 나가지 않는다.
    """
    from .client import MfdsClient

    records: list[dict] = []
    with MfdsClient(settings) as client:
        for rec in client.iter_records():
            records.append(rec)
            if limit and len(records) >= limit:
                break
    if not records:
        raise SystemExit("수집된 레코드가 없습니다.")

    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    stem = f"dump_{len(records)}"

    jpath = settings.cache_dir / f"{stem}.json"
    jpath.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    # 엑셀에서 바로 열 수 있도록 CSV 도 함께. 필드는 등장 순서를 보존한다.
    cols: list[str] = []
    for rec in records:
        for k in rec:
            if k not in cols:
                cols.append(k)
    cpath = settings.cache_dir / f"{stem}.csv"
    with cpath.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for rec in records:
            w.writerow({k: ("" if v is None else v) for k, v in rec.items()})

    print(f"\n원본 {len(records)}건 저장 완료")
    print(f"  JSON : {jpath}")
    print(f"  CSV  : {cpath}   (엑셀에서 바로 열림)")
    print(f"\n원본 필드 {len(cols)}종: {', '.join(cols)}")

    mapped = set(settings.fields)
    unmapped = [c for c in cols if c not in mapped]
    if unmapped:
        print(f"\n[참고] settings.toml 의 [fields] 에 없는 필드: {', '.join(unmapped)}")
        print("       필요하면 매핑에 추가하십시오. 현재는 수집 시 폐기됩니다.")
    print("\n[주의] 이 파일은 allowlist 를 거치지 않은 원본입니다. 그대로 게시하지 마십시오.")


def _build(settings, cache: str = "raw") -> None:
    df = load_cache(settings, cache)
    if cache != "raw" or read_cache_meta(settings, cache).get("sample"):
        # 시험 수집분으로 만든 사이트는 모든 페이지에 표시해 정식 게시물과 혼동을 막는다.
        notice = (f"미리보기: 시험 수집 캐시({cache}, {len(df):,}행)로 생성한 페이지입니다. "
                  "수치는 전체 데이터가 아니므로 인용하지 마십시오.")
        settings = replace(settings, site={**settings.site, "notice": notice})
        print(f"  [주의] {notice}", file=sys.stderr)
    out = settings.output_dir
    if out.exists():
        shutil.rmtree(out)           # 이전 산출물 잔존 방지(구 데이터 유출 차단)
    out.mkdir(parents=True, exist_ok=True)

    entries = []
    for report in settings.reports:
        subset = select(df, report)
        if subset.empty:
            print(f"  [skip] {report['id']}: 해당 데이터 없음", file=sys.stderr)
            continue
        stats = summarize(subset, settings)
        rdir = out / report["slug"]
        rdir.mkdir(parents=True, exist_ok=True)
        charts = draw_charts(stats, settings, rdir, report.get("charts", []))
        render_report(report, subset, stats, charts, settings, rdir)
        entries.append({**report, "total": stats["total"], "last_year": stats.get("last_year")})

    if not entries:
        raise SystemExit("생성된 리포트가 없습니다. 키워드/필터를 확인하십시오.")

    explorer_info = None
    if settings.explorer.get("enabled", False):
        from .explorer import build_dataset, copy_assets
        from .render import render_explorer
        edir = out / settings.explorer.get("slug", "explore")
        explorer_info = build_dataset(df, settings, edir)
        copy_assets(settings, edir)
        render_explorer(settings, edir, explorer_info)

    render_index(entries, settings, explorer_info)

    # GitHub Pages 는 기본적으로 Jekyll 로 후처리한다. 정적 산출물을 그대로
    # 내보내기 위해 비활성화 표식을 남긴다(밑줄로 시작하는 파일 누락 방지).
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"\n완료: {out} — 리포트 {len(entries)}건")
    print("이 디렉터리를 그대로 정적 호스팅(GitHub Pages, Netlify, Cloudflare Pages 등)에 올리면 됩니다.")


def _serve(settings, port: int) -> None:
    """생성된 정적 사이트를 로컬에서 확인하기 위한 임시 웹서버.

    file:// 로는 브라우저가 fetch 를 막아 탐색기가 동작하지 않으므로 필요하다.
    로컬 확인 전용이며, 외부에 공개하는 용도가 아니다(127.0.0.1 로만 바인딩).
    """
    import functools
    import webbrowser
    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

    root = settings.output_dir
    if not (root / "index.html").exists():
        raise SystemExit(f"{root} 에 생성된 사이트가 없습니다. 먼저 `build` 를 실행하십시오.")

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        raise SystemExit(f"포트 {port} 를 열 수 없습니다({exc}). --port 로 다른 번호를 지정하십시오.")

    url = f"http://localhost:{port}/"
    print(f"\n로컬 서버 시작: {url}")
    print(f"  대화형 탐색기: {url}explore/")
    print("\n종료하려면 Ctrl+C 를 누르십시오.\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료했습니다.")
    finally:
        httpd.server_close()


def _check(settings) -> int:
    problems = 0
    def ok(msg): print(f"  [OK]   {msg}")
    def bad(msg):
        nonlocal problems; problems += 1; print(f"  [FAIL] {msg}")
    def warn(msg): print(f"  [WARN] {msg}")

    print("설정 및 보안 점검\n")
    import importlib.util, platform
    print(f"  [INFO] 파이썬 {platform.python_version()} · {sys.executable}")
    ok("캐시 형식: parquet (pyarrow 사용)" if importlib.util.find_spec("pyarrow")
       else "캐시 형식: CSV (pyarrow 미설치 — 선택 사항이며 기능 차이 없음)")
    ok(f"게시 허용 컬럼 {len(settings.publish['allowed_columns'])}종 정의됨")
    ok(f"리포트 {len(settings.reports)}건 정의됨")
    (ok if str(settings.api['base_url']).startswith('https://') else bad)("API 엔드포인트 HTTPS")
    built = str(settings.api["base_url"]).rstrip("/") + str(settings.api.get("endpoint", ""))
    print(f"  [INFO] 호출 URL: {built}")
    if built.count("/get") > 1:
        bad("URL 에 오퍼레이션이 두 번 들어 있습니다 — base_url 과 endpoint 를 확인하십시오.")
    if settings.has_api_key:
        raw = os.environ.get("MFDS_API_KEY", "")
        _, was_enc = cfgmod.normalize_api_key(raw)
        ok(f"API 키 설정됨 (길이 {len(settings.api_key)}자"
           + (", Encoding 형태 → 자동 변환됨" if was_enc else ", Decoding 형태") + ")")
    else:
        warn("API 키 미설정 — fetch/probe 불가 (build 는 캐시로 가능)")

    gi = settings.root / ".gitignore"
    if gi.exists() and ".env" in gi.read_text(encoding="utf-8"):
        ok(".gitignore 가 .env 를 제외함")
    else:
        bad(".gitignore 에 .env 가 없습니다. 키가 저장소에 올라갈 위험이 있습니다.")

    env_path = settings.root / ".env"
    if env_path.exists():
        if os.name == "nt":
            ok(".env 존재 (Windows: 파일 권한은 NTFS 속성으로 관리 — 사용자 폴더 밖 공유 위치 금지)")
        else:
            mode = oct(env_path.stat().st_mode)[-3:]
            (ok if mode in ("600", "400") else warn)(f".env 파일 권한 {mode} (권장 600)")

    ext = []
    for tpl in settings.template_dir.glob("*.j2"):
        text = tpl.read_text(encoding="utf-8")
        if "|safe" in text or "{% autoescape false" in text:
            bad(f"{tpl.name}: 이스케이프 우회(|safe)가 있습니다 — XSS 위험")
        # 동일출처 <script src="explorer.js"> 는 허용. 외부 호스트만 문제 삼는다.
        import re as _re
        for m in _re.finditer(r'<script[^>]*src=["\']([^"\']+)', text):
            if _re.match(r"(https?:)?//", m.group(1)):
                ext.append(f"{tpl.name}: {m.group(1)}")
        if _re.search(r"<script(?![^>]*\bsrc=)", text):
            ext.append(f"{tpl.name}: 인라인 스크립트(CSP 에 해시/논스 필요)")
        if "//cdn." in text or "fonts.googleapis" in text:
            ext.append(f"{tpl.name}: 외부 리소스 참조")
    (warn if ext else ok)(
        f"외부/인라인 스크립트: {'; '.join(ext)}" if ext
        else "스크립트는 동일출처 파일뿐 — CSP script-src 'self' 로 운영 가능")

    # 정적 검사만으로는 autoescape 설정 실수를 못 잡는다. 실제로 렌더링해 확인한다.
    try:
        from .render import _env
        probe = _env(settings).from_string("{{ x }}").render(x="<script>alert(1)</script>")
        (ok if "<script>" not in probe else bad)(
            "HTML 자동 이스케이프 실동작 확인" if "<script>" not in probe
            else "자동 이스케이프가 꺼져 있습니다 — XSS 위험(render.py autoescape 확인)")
    except Exception as exc:
        bad(f"이스케이프 자가진단 실패: {exc}")

    print(f"\n결과: {'통과' if problems == 0 else f'{problems}건 조치 필요'}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mfds-insight", description="MFDS 허가데이터 리포트 생성기")
    p.add_argument("command",
               choices=["probe", "dump", "fetch", "build", "run", "check", "serve"])
    p.add_argument("--root", type=Path, default=None, help="프로젝트 루트")
    p.add_argument("--sample", type=int, default=None,
               help="fetch/dump 시 가져올 최대 레코드 수 (예: --sample 300)")
    p.add_argument("--cache", default=None,
               help="build 에 사용할 캐시 이름 (기본 raw, 시험 수집분은 sample)")
    p.add_argument("--allow-incomplete", action="store_true",
               help="완전성 검사 실패 시에도 캐시를 갱신 (원인 확인 후에만 사용)")
    p.add_argument("--port", type=int, default=8000, help="serve 포트 (기본 8000)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    cfgmod.setup_logging(args.verbose)
    try:
        settings = cfgmod.load(args.root)
    except ConfigError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2

    try:
        if args.command == "check":
            return _check(settings)
        if args.command == "probe":
            from .client import MfdsClient
            with MfdsClient(settings) as c:
                print(json.dumps(c.probe(), ensure_ascii=False, indent=2)[:4000])
            return 0
        if args.command == "serve":
            _serve(settings, args.port)
            return 0
        if args.command == "dump":
            _dump(settings, args.sample)
            return 0
        cache = args.cache or "raw"
        if args.command in ("fetch", "run"):
            cache = _fetch(settings, args.sample, args.allow_incomplete)
        if args.command in ("build", "run"):
            _build(settings, args.cache or cache)
        return 0
    except ConfigError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:                      # 키가 섞여 나가지 않도록 마스킹
        print(f"실패: {settings.mask(str(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
