<!-- # MFDS Insight

> **처음 사용하신다면 `시작하기.txt` 를 먼저 읽으신 뒤 `setup.bat` 을 실행하십시오.**
> 명령을 직접 입력하지 않아도 `menu.bat` 으로 모든 기능을 쓸 수 있습니다.

식약처 의료기기 품목허가 공개데이터를 수집·분석해 **사이트 게시용 정적 리포트**를
자동 생성하는 파이프라인입니다.

- 산출물: 정적 HTML + SVG 차트 + CSV/JSON 다운로드
- 서버·DB 불필요. 생성된 `output/` 을 그대로 정적 호스팅에 올립니다.
- 리포트 추가·수정은 **설정 파일만** 고치면 됩니다. 코드는 건드리지 않습니다.

---

## 1. 설치

Python 3.9 이상에서 동작합니다(3.11 미만은 `tomli` 가 자동 설치됩니다).

> **권장: 3.12 또는 3.13.** 3.14 같은 최신 버전은 일부 라이브러리의 미리 빌드된 휠이
> 아직 없어 소스 빌드를 시도하다 실패할 수 있습니다. 필수 의존성은 3.14에서도
> 문제없이 설치되도록 정리해 두었습니다.

**Windows (PowerShell)**
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
> `Activate.ps1` 실행이 차단되면 한 번만 실행 정책을 완화합니다.
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
> 또는 정책 변경 없이 `.\.venv\Scripts\activate.bat` (명령 프롬프트)를 사용하십시오.

**Windows (명령 프롬프트 cmd)**
```bat
py -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

선택 사항(대용량에서 캐시가 약간 빨라짐, 없어도 무방):

```
pip install -r requirements-optional.txt
```

> 이 설치가 실패해도 무시하십시오. 프로그램은 정상 동작합니다.

### 한글 폰트

차트 라벨에 한글 폰트가 필요합니다.

| 환경 | 조치 |
|---|---|
| **Windows** | 별도 설치 불필요. 맑은 고딕이 기본 탑재되어 자동 인식됩니다. |
| macOS | `brew install --cask font-nanum-gothic` (또는 AppleGothic 자동 사용) |
| Ubuntu/Debian | `sudo apt install fonts-nanum` |

폰트를 찾지 못하면 중단되지 않고 경고만 남긴 뒤 대체 폰트로 진행합니다.

## 2. API 키 설정

1. [공공데이터포털](https://www.data.go.kr) 가입 후 아래 데이터셋 활용신청
   - 식품의약품안전처_의료기기 품목허가 정보 (`/data/15057456`)
   - 식품의약품안전처_의료기기 품목정보 (`/data/15073906`)
2. 발급받은 **일반 인증키**를 `.env` 에 기입

> 포털은 같은 키를 Encoding / Decoding 두 형태로 보여줍니다.
> **어느 쪽을 넣어도 됩니다.** 프로그램이 형태를 판별해 자동으로 맞춥니다.
> (`%2B` 같은 코드가 보이면 Encoding 형태이며, 내부에서 Decoding 형태로 변환합니다.)
>
> 인증키는 **계정당 하나**이며 승인된 모든 데이터셋에 공통으로 쓰입니다.
> 데이터셋마다 따로 넣을 필요가 없습니다.

**Windows (PowerShell)**
```powershell
Copy-Item .env.example .env
notepad .env        # MFDS_API_KEY=발급받은키 입력 후 저장
```

**Windows (cmd)**
```bat
copy .env.example .env
notepad .env
```

**macOS / Linux**
```bash
cp .env.example .env
chmod 600 .env
```

> `.env` 는 `.gitignore` 로 제외되어 있습니다. 절대 커밋하지 마십시오.
> Windows에는 `chmod` 가 없습니다. 대신 `.env` 를 OneDrive·공유 폴더·네트워크 드라이브에
> 두지 마시고, 필요하면 파일 속성 → 보안에서 본인 계정만 접근하도록 제한하십시오.
> 메모장 저장 시 인코딩은 **UTF-8** 로 두십시오.

## 3. 문제 해결

| 증상 | 원인 / 조치 |
|---|---|
| `ModuleNotFoundError: No module named 'pandas'` | 의존성 미설치 또는 가상환경 밖 실행. 위 1번을 수행하십시오. `python run.py check` 가 어떤 인터프리터를 쓰는지 안내해 줍니다. |
| `Activate.ps1 ... 실행할 수 없습니다` | PowerShell 실행 정책. `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` 또는 cmd에서 `activate.bat` 사용 |
| `python` 입력 시 Microsoft Store 안내창 | `python` 대신 `py` 사용, 또는 설정 → 앱 실행 별칭에서 python.exe 끄기 |
| 어느 파이썬이 실행되는지 모르겠음 | `py -0` (목록), `python -c "import sys; print(sys.executable)"` (현재), `pip -V` (pip 소속) |
| 확실하게 실행하고 싶음 | `.\.venv\Scripts\python.exe run.py check` 처럼 인터프리터를 직접 지정 |
| 차트의 한글이 네모로 나옴 | 한글 폰트 미설치. 위 폰트 표 참조 (Windows는 기본 탑재) |
| 탐색기에서 "데이터를 불러오지 못했습니다" | `file://` 로 열었기 때문. `python run.py serve` 후 `http://localhost:8000/explore/` 로 접속 |
| `포트 8000 를 열 수 없습니다` | 다른 프로그램이 사용 중. `python run.py serve --port 8080` |
| `output ... 생성된 사이트가 없습니다` | `build` 를 먼저 실행 |
| `Failed building wheel for pyarrow` / `command 'cmake' failed` | pyarrow는 **선택 사항**입니다. `requirements.txt` 에서 이미 제외했으므로 최신 버전을 받아 다시 설치하십시오. 없으면 CSV 캐시로 자동 전환되며 기능 차이는 없습니다. |
| 그 밖의 `Failed building wheel for ...` | 해당 파이썬 버전용 휠이 없어 소스 빌드를 시도한 경우입니다. Python 3.12/3.13 을 쓰시면 대부분 해결됩니다. |

## 4. 사용

가상환경을 활성화한 상태에서는 아래 명령이 세 OS 모두 동일합니다.
(활성화하지 않았다면 Windows는 `python` 대신 `py` 를 쓰십시오.)

```
python run.py check                # 설정·보안 점검 (배포 전 항상 실행)
python run.py dump --sample 300    # 원본 300건을 가공 없이 JSON/CSV 로 저장 (점검용)
python run.py probe                # API 응답 구조 확인 → 필드 매핑용
python run.py fetch --sample 300   # 소량 시험 수집 → cache/sample (정식 캐시 raw 는 유지)
python run.py build --cache sample # 시험 수집분으로 미리보기 사이트 생성 (전 페이지에 미리보기 표시)
python run.py fetch                # 전체 수집 → cache/
python run.py build                # 캐시 → output/ 정적 사이트 생성
python run.py run                  # fetch + build
python run.py serve                # 로컬 서버로 결과 확인 (--port 로 번호 변경)
```

### 수집 완전성 검사

정식 `fetch`(또는 `run`)는 다음 중 하나라도 해당하면 **캐시를 갱신하지 않고 실패로 끝납니다.**
이전 캐시는 그대로 남으므로, 불완전한 데이터가 게시되지 않습니다.

- 응답의 totalCount 보다 수집 건수가 적음
- `api.max_pages` 상한에서 중단됨
- 직전 정식 수집 대비 건수가 `api.max_row_drop_pct`(기본 5%) 넘게 감소
- 응답 본문의 `header.resultCode` 가 00(정상)·03(데이터 없음)이 아님

원인을 확인하고 의도한 결과라면 `--allow-incomplete` 로 강제할 수 있습니다.
이 경우 위반 사유가 `cache/raw.meta.json` 의 `integrity_override` 에 기록됩니다.

> **탐색기는 반드시 `serve` 로 여십시오.** `output\index.html` 을 더블클릭해
> `file://` 로 열면 브라우저가 로컬 파일의 `fetch` 를 차단해 데이터를 읽지 못합니다.
> 정적 리포트 페이지는 `file://` 로도 정상적으로 보입니다.

### 첫 실행 순서

**① 요청주소 기입 (필수)**

> **권장:** `config/settings.toml` 대신 **`.env`** 에 넣으십시오.
> `.env` 는 배포 파일에 포함되지 않으므로, 프로그램을 갱신해도 값이 보존됩니다.
> ```
> MFDS_BASE_URL=http://apis.data.go.kr/1471000/AaaService01
> MFDS_ENDPOINT=/getAaaInq01
> ```
> `.env` 값이 `settings.toml` 보다 우선합니다.

`config/settings.toml` 의 `base_url` / `endpoint` 는 **비워둔 자리표시자**입니다.
반드시 본인 계정에서 확인한 값으로 바꾸십시오.

> 공공데이터포털 → 마이페이지 → 데이터활용 → 오픈API → **활용신청 목록**
> → 해당 데이터 클릭 → **상세기능정보**의 `요청주소` 복사

요청주소가 `http://apis.data.go.kr/1471000/AaaService01/getAaaInq01` 이라면:

```toml
base_url = "http://apis.data.go.kr/1471000/AaaService01"   # 마지막 / 제외
endpoint = "/getAaaInq01"
```

포털은 `http://` 로 안내하지만 그대로 붙여넣으셔도 됩니다. 프로그램이 `https` 로
자동 승격해 인증키가 평문으로 나가지 않게 합니다.

같은 화면의 **미리보기** 버튼으로 실제 응답을 먼저 확인하면 다음 단계가 쉬워집니다.

**② 응답 구조 확인 후 매핑**

```
python run.py probe
```

출력된 JSON을 보고 `api.records_path`, `api.total_path`, `[fields]` 매핑을 맞추십시오.
**응답 구조가 바뀌어도 코드 수정은 필요 없습니다.**

### 원본 데이터 확인

수집 전에 실제 데이터를 눈으로 보고 싶을 때 씁니다.

```
python run.py dump --sample 300
```

`cache\dump_300.json` (원본 그대로) 과 `cache\dump_300.csv` (엑셀용) 가 생성됩니다.
`[fields]` 에 매핑되지 않은 필드가 있으면 함께 알려주므로, 매핑 보완에 유용합니다.

> 이 파일은 **allowlist 를 거치지 않은 원본**입니다. `cache/` 는 `.gitignore` 에
> 포함되어 있으니 그대로 두시고, 게시용으로 쓰지 마십시오.

`fetch` 로 받은 데이터는 매핑·파생·allowlist 를 거친 결과이며 `cache\raw.csv` 에서 볼 수 있습니다.

### 대화형 탐색기

`[explorer] enabled = true` 이면 `output/explore/` 에 브라우저 탐색기가 함께 생성됩니다.

- 방문자가 **데이터를 한 번만 내려받고**, 이후 품목·업체·상태·연도를 바꿔가며
  즉시 재집계합니다. 서버가 없으므로 조건을 몇 번 바꿔도 추가 요청이 없습니다.
- 차트·표·KPI 가 실시간으로 갱신되고, **현재 조건 그대로 CSV 내보내기**가 됩니다.
- 외부 라이브러리를 쓰지 않습니다. 차트는 브라우저에서 SVG 로 직접 그립니다.

```toml
[explorer]
enabled  = true
max_rows = 60000                       # 초과 시 최신 허가부터 잘라냄
columns  = ["품목명", "업체명", ...]     # publish.allowed_columns 안에서만
facet_columns  = ["제조수입구분", "품목상태", "품목명"]   # 필터로 쓸 컬럼
search_columns = ["품목명", "업체명"]                    # 텍스트 검색 대상
```

용량 기준: 약 **8,000행 = 0.4 MB**, 60,000행 ≈ 3.2 MB (gzip 전송 시 약 1/5).
데이터가 커지면 `max_rows` 를 줄이거나 `columns` 를 줄이십시오.

> `explorer.columns` 는 `publish.allowed_columns` 의 부분집합이어야 하며,
> 벗어나면 빌드가 실패합니다(의도된 안전장치).

### 포털 오류코드

호출 실패 시 프로그램이 원인을 해석해 보여줍니다.

| 코드 | 의미 | 조치 |
|---|---|---|
| 12 | 서비스가 없거나 폐기됨 | `base_url`/`endpoint` 오기입. 요청주소를 다시 복사 |
| 30 | 등록되지 않은 서비스키 | 활용신청 승인 대기(최대 1시간) |
| 20 | 서비스 접근 거부 | 해당 데이터 활용신청 여부 확인 |
| 22 | 트래픽 초과 | 개발계정 일 10,000건 한도 |
| 31 | 활용기간 만료 | 연장 신청 |

## 5. 리포트 추가

`config/settings.toml` 에 블록 하나만 추가합니다.

```toml
[[report]]
id       = "ivd-reagent"
title    = "체외진단시약 허가 동향"
slug     = "ivd-reagent"
keywords = ["체외진단"]
filters  = { "등급" = ["3등급", "4등급"] }
charts   = ["yearly_trend", "grade_mix", "top_companies"]
summary  = "체외진단 품목의 허가 추이입니다."
```

키워드 비교 방식
- `match = "contains"`(기본): 품목명에 키워드가 **포함**되면 선택합니다. 공백은 무시합니다.
- `match = "exact"`: 품목명이 키워드와 **정확히 같을 때만** 선택합니다.
- `exclude = [...]`: 품목명에 이 문자열이 포함되면 제외합니다.

부분일치에서는 `"치과용임플란트"` 가 `"치과용임플란트상부구조물"` 까지 잡습니다.
품목 단위 리포트는 `exact` 나 `exclude` 로 범위를 명시해야 다른 리포트와 중복 집계되지 않습니다.
`build` 로그의 `포함된 품목명 상위` 줄에서 실제로 잡힌 품목을 확인하십시오.

`python run.py build` 만 다시 실행하면 새 페이지가 생성되고 목차에도 자동 반영됩니다.

## 6. 구조

```
config/settings.toml   ← 거의 모든 변경은 여기서
src/mfds_insight/
  config.py    설정 로드·검증, 키 마스킹
  client.py    API 호출 (재시도·레이트리밋·리다이렉트 차단)
  pipeline.py  정규화·캐시·필터·집계   ← allowlist 적용 지점
  render.py    SVG 차트 + HTML/CSV/JSON 생성
  cli.py       명령행 진입점
templates/     Jinja2 템플릿 (autoescape 상시 활성)
cache/         API 원본 (커밋 안 함)
output/        게시물 (빌드마다 전량 재생성)
```

## 7. GitHub Pages 배포

### 방법 A — 자동 배포 (권장)

새 저장소를 하나 만들고 이 프로젝트 전체를 올리면, 매월 자동으로 데이터를 갱신해 게시합니다.
`.github/workflows/publish.yml` 이 이미 포함되어 있습니다.

1. GitHub 에서 새 저장소 생성 (예: `mfds-insight`) — **Public** 이어야 무료로 Pages 사용 가능
2. 프로젝트 폴더를 올립니다 (`.env` 는 `.gitignore` 로 제외되므로 안전)
3. 저장소 **Settings → Secrets and variables → Actions → New repository secret** 에 3개 등록
   - `MFDS_API_KEY` / `MFDS_BASE_URL` / `MFDS_ENDPOINT`
4. **Settings → Pages → Source** 를 **GitHub Actions** 로 변경
5. **Actions** 탭에서 워크플로를 수동 실행(Run workflow)해 첫 배포

주소는 `https://<계정>.github.io/<저장소명>/` 이 됩니다.
`config/settings.toml` 의 `site.base_url` 에 같은 주소를 넣어 주십시오.

### 방법 B — 수동 배포

기존 사용자 사이트(`<계정>.github.io`) 저장소의 하위 폴더에 결과물만 복사하는 방식입니다.

```
python run.py build
```

`output/` 안의 내용을 사이트 저장소의 원하는 폴더(예: `mfds/`)에 복사한 뒤 커밋·푸시합니다.
`site.base_url` 은 `"https://<계정>.github.io/mfds"` 로 지정하십시오.

> `output/.nojekyll` 파일을 함께 올려야 합니다(빌드 시 자동 생성).
> 없으면 GitHub 의 Jekyll 처리 때문에 일부 파일이 누락될 수 있습니다.

### 주의

- **`.env` 를 절대 커밋하지 마십시오.** 푸시 전 `git status` 로 확인하십시오.
- 공개 저장소이므로 재직 회사의 내부 자료가 섞이지 않았는지 확인하십시오
  (`SECURITY.md` 8항 참조).

## 8. 보안

[SECURITY.md](SECURITY.md) 를 반드시 읽어보십시오. 특히 **게시 허용 필드(allowlist)** 와
**재직 중 겸업·영업비밀 분리** 항목을 확인하시기 바랍니다.
 -->