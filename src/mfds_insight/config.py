"""설정 로드 및 검증. 비밀값은 환경변수에서만 읽는다."""
from __future__ import annotations

import os
import re
import sys
import logging
from urllib.parse import quote, quote_plus, unquote
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

log = logging.getLogger(__name__)

ENV_KEY_NAME = "MFDS_API_KEY"


class ConfigError(RuntimeError):
    pass


# 공공데이터포털은 같은 키를 Encoding/Decoding 두 형태로 제공한다.
# requests 가 파라미터를 다시 인코딩하므로 반드시 Decoding 형태여야 한다.
# Base64 키에는 '%' 가 나올 수 없으므로, %XX 패턴이 보이면 Encoding 키로 판단한다.
_PCT = re.compile(r"%[0-9A-Fa-f]{2}")


def normalize_api_key(raw: str) -> tuple[str, bool]:
    """(정규화된 키, 디코딩 수행 여부) 를 돌려준다."""
    key = (raw or "").strip().strip('"').strip("'")
    if not key:
        return "", False
    if _PCT.search(key):
        decoded = unquote(key)
        if decoded != key:
            return decoded, True
    return key, False


def _load_dotenv(path: Path) -> None:
    """의존성 없이 .env 를 읽어 환경변수에 주입한다(기존 값 우선)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    root: Path
    site: dict
    api: dict
    fields: dict
    publish: dict
    reports: list
    chart: dict
    derive: list
    labels: dict
    explorer: dict
    _api_key: str = field(repr=False, default="")

    @property
    def api_key(self) -> str:
        if not self._api_key:
            raise ConfigError(
                f"환경변수 {ENV_KEY_NAME} 가 비어 있습니다. "
                f".env 에 {ENV_KEY_NAME}=<발급받은키> 를 넣거나 셸에서 export 하십시오."
            )
        return self._api_key

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def mask(self, text: str) -> str:
        """로그·예외 메시지에 키가 섞여 나가는 것을 막는다.

        requests 는 쿼리 파라미터를 URL 인코딩하므로, 연결 오류 메시지에는
        원문이 아니라 인코딩된 키(예: '+' → '%2B')가 담긴다. 원문과
        인코딩 형태(quote_plus / quote)를 모두 치환한다. 긴 형태부터 치환해
        부분 치환으로 일부가 남는 일을 막는다.
        """
        if not self._api_key or not text:
            return text
        forms = {self._api_key, quote_plus(self._api_key), quote(self._api_key, safe="")}
        for form in sorted(forms, key=len, reverse=True):
            if form:
                text = text.replace(form, "***REDACTED***")
                # 퍼센트 인코딩의 대소문자 변형(%2b 등)도 차단
                if "%" in form:
                    text = re.sub(re.escape(form), "***REDACTED***", text, flags=re.IGNORECASE)
        return text

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def template_dir(self) -> Path:
        return self.root / "templates"


def load(root: Path | None = None, config_name: str = "settings.toml") -> Settings:
    root = Path(root or Path(__file__).resolve().parents[2])
    _load_dotenv(root / ".env")

    cfg_path = root / "config" / config_name
    if not cfg_path.exists():
        raise ConfigError(f"설정 파일이 없습니다: {cfg_path}")

    with cfg_path.open("rb") as fh:
        raw = tomllib.load(fh)

    for section in ("site", "api", "fields", "publish", "chart"):
        if section not in raw:
            raise ConfigError(f"설정에 [{section}] 섹션이 없습니다: {cfg_path}")

    reports = raw.get("report", [])
    if not reports:
        raise ConfigError("정의된 [[report]] 가 없습니다. 최소 1개가 필요합니다.")

    allowed = raw["publish"].get("allowed_columns") or []
    if not allowed:
        raise ConfigError(
            "publish.allowed_columns 가 비어 있습니다. "
            "게시 허용 필드를 명시하지 않으면 아무것도 발행하지 않습니다(의도된 안전장치)."
        )
    derived_names = {d.get("name") for d in raw.get("derive", [])}
    unknown = set(allowed) - set(raw["fields"].values()) - derived_names
    if unknown:
        raise ConfigError(f"allowed_columns 에 매핑되지 않은 컬럼: {sorted(unknown)}")

    # 환경변수(.env)가 있으면 settings.toml 보다 우선한다.
    # .env 는 배포물에 포함되지 않으므로, 프로그램을 갱신해도 값이 보존된다.
    env_base = os.environ.get("MFDS_BASE_URL", "").strip()
    env_ep = os.environ.get("MFDS_ENDPOINT", "").strip()
    if env_base:
        raw["api"]["base_url"] = env_base
        # base_url 을 .env 로 덮어쓸 때는 endpoint 도 .env 기준으로 맞춘다.
        # (파일에 남아 있던 옛 endpoint 가 뒤에 덧붙는 것을 막는다)
        raw["api"]["endpoint"] = env_ep
        log.info(".env 의 MFDS_BASE_URL/MFDS_ENDPOINT 를 사용합니다.")
    elif env_ep:
        raw["api"]["endpoint"] = env_ep

    exp = raw.get("explorer", {})
    if exp.get("enabled"):
        extra = set(exp.get("columns", [])) - set(allowed)
        if extra:
            raise ConfigError(
                f"explorer.columns 에 게시 비허용 컬럼이 있습니다: {sorted(extra)}. "
                "publish.allowed_columns 안에서만 고르십시오."
            )

    # 공공데이터포털은 요청주소를 http:// 로 안내하지만 https 도 동일하게 동작한다.
    # 포털에서 복사한 주소를 그대로 붙여넣어도 되도록 자동 승격한다.
    base = str(raw["api"].get("base_url", "")).strip().rstrip("/")
    if base.startswith("http://"):
        if raw["api"].get("allow_insecure_http", False):
            log.warning("평문 HTTP 로 통신합니다. 인증키가 네트워크에 노출될 수 있습니다.")
        else:
            base = "https://" + base[len("http://"):]
            log.info("api.base_url 을 https 로 자동 변경했습니다(평문 전송 방지).")
    elif base and not base.startswith("https://"):
        raise ConfigError(f"api.base_url 형식이 올바르지 않습니다: {base!r}")
    if not base:
        raise ConfigError("api.base_url 이 비어 있습니다. 포털의 '요청주소'를 기입하십시오.")
    if "여기에" in base:
        raise ConfigError(
            "api.base_url 이 자리표시자 그대로입니다. "
            "포털 마이페이지 > 활용신청 상세의 '요청주소'로 바꾸십시오."
        )

    ep = str(raw["api"].get("endpoint", "")).strip()
    if "여기에" in ep:
        raise ConfigError("api.endpoint 가 자리표시자 그대로입니다.")
    if ep and not ep.startswith("/"):
        ep = "/" + ep                      # 앞 슬래시 누락 교정

    # 흔한 실수 ①: 요청주소 전체를 base_url 에 넣고 endpoint 도 남겨둔 경우
    #   → base_url 끝이 endpoint 와 같으면 잘라낸다 (…/getX + /getX 중복 방지)
    if ep and base.endswith(ep):
        base = base[: -len(ep)]
        log.warning("base_url 끝에 endpoint 가 중복되어 있어 제거했습니다 → %s", base)
    # 흔한 실수 ②: base_url 에 오퍼레이션이 들어 있는데 endpoint 는 비어 있는 경우
    elif not ep:
        head, _, tail = base.rpartition("/")
        if tail.lower().startswith("get"):
            base, ep = head, "/" + tail
            log.warning("base_url 에서 오퍼레이션을 분리했습니다 → base=%s, endpoint=%s", base, ep)

    raw["api"]["base_url"] = base
    raw["api"]["endpoint"] = ep

    key, was_encoded = normalize_api_key(os.environ.get(ENV_KEY_NAME, ""))
    if was_encoded:
        log.info("Encoding 형태의 인증키를 감지하여 Decoding 형태로 자동 변환했습니다.")

    return Settings(
        root=root,
        site=raw["site"],
        api=raw["api"],
        fields=raw["fields"],
        publish=raw["publish"],
        reports=reports,
        chart=raw["chart"],
        derive=raw.get("derive", []),
        labels=raw.get("labels", {}),
        explorer=raw.get("explorer", {}),
        _api_key=key,
    )


def setup_logging(verbose: bool = False) -> None:
    # Windows 콘솔은 기본 인코딩이 cp949 라, 표현 불가 문자가 섞이면 예외로 죽는다.
    # 인코딩을 바꾸지 않고 대체표기만 허용해 중단을 막는다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)-20s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
