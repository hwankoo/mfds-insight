#!/usr/bin/env python3
"""프로젝트 루트에서 바로 실행하기 위한 래퍼.

  python run.py check     설정·보안 점검
  python run.py probe     API 응답 구조 확인
  python run.py dump --sample 300   원본 300건을 JSON/CSV 로 저장
  python run.py fetch     데이터 수집
  python run.py build     정적 사이트 생성
  python run.py run       fetch + build
  python run.py serve     로컬 서버로 결과 확인 (탐색기 필수)
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

MIN_PY = (3, 9)
REQUIRED = {                      # import 이름 -> pip 패키지명
    "pandas": "pandas",
    "requests": "requests",
    "matplotlib": "matplotlib",
    "jinja2": "Jinja2",
}


def _preflight() -> None:
    """의존성·파이썬 버전을 먼저 확인하고, 문제가 있으면 원시 트레이스백 대신 안내를 낸다."""
    if sys.version_info < MIN_PY:
        sys.exit(
            f"파이썬 {MIN_PY[0]}.{MIN_PY[1]} 이상이 필요합니다 "
            f"(현재 {sys.version_info.major}.{sys.version_info.minor}).\n"
            "Windows: https://www.python.org 에서 최신 버전을 설치한 뒤 `py -3.12 run.py ...` 로 실행하십시오."
        )

    import importlib.util

    missing = [pkg for mod, pkg in REQUIRED.items() if importlib.util.find_spec(mod) is None]
    if sys.version_info < (3, 11) and importlib.util.find_spec("tomli") is None:
        missing.append("tomli")
    if not missing:
        return

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    is_win = sys.platform.startswith("win")

    lines = [
        "필요한 패키지가 설치되어 있지 않습니다: " + ", ".join(missing),
        "",
        f"현재 인터프리터 : {sys.executable}",
        f"가상환경 활성화 : {'예' if in_venv else '아니오'}",
        "",
        "다음 순서로 진행하십시오.",
        "",
    ]
    if is_win:
        lines += [
            "  PowerShell:",
            "    py -m venv .venv",
            "    .\\.venv\\Scripts\\Activate.ps1",
            "    pip install -r requirements.txt",
            "",
            "  Activate.ps1 이 차단되면 명령 프롬프트(cmd)에서:",
            "    .venv\\Scripts\\activate.bat",
            "    pip install -r requirements.txt",
            "",
            "  가상환경 없이 지금 인터프리터에 바로 설치하려면:",
            f'    "{sys.executable}" -m pip install -r requirements.txt',
        ]
    else:
        lines += [
            "    python3 -m venv .venv",
            "    source .venv/bin/activate",
            "    pip install -r requirements.txt",
            "",
            "  또는 지금 인터프리터에 바로 설치:",
            f'    "{sys.executable}" -m pip install -r requirements.txt',
        ]
    lines += ["", "설치 후 다시 실행하십시오:  python run.py check"]
    sys.exit("\n".join(lines))


_preflight()

from mfds_insight.cli import main  # noqa: E402

raise SystemExit(main())
