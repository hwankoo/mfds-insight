# 보안 설계 노트

공개 사이트에 게시하는 파이프라인이므로, 설계 단계에서 다음을 전제로 삼았습니다.

## 1. 공격 표면을 구조적으로 없앰

산출물은 **순수 정적 파일(HTML/SVG/CSV/JSON)** 입니다.
서버 애플리케이션도, 데이터베이스도, 런타임 사용자 입력도 없습니다.
따라서 SQL 인젝션·인증 우회·세션 탈취 같은 서버측 취약점 자체가 성립하지 않습니다.
정적 호스팅(GitHub Pages, Netlify, Cloudflare Pages 등)에 그대로 올리면 됩니다.

## 2. 비밀값 관리

| 항목 | 처리 |
|---|---|
| API 키 저장 | `.env` (환경변수). 소스·설정 파일에 절대 넣지 않음 |
| 저장소 유출 방지 | `.gitignore` 에 `.env` 등록, `check` 명령이 매번 검증 |
| 로그·예외 노출 | `Settings.mask()` 로 키 문자열을 `***REDACTED***` 치환 후 출력 |
| 전송 | HTTPS 강제(설정 로드시 http:// 거부), TLS 검증 비활성화 불가 |

키가 유출된 경우: 공공데이터포털에서 인증키를 재발급하고 `.env` 를 교체하십시오.

## 3. 게시 데이터 통제 — allowlist 방식

`config/settings.toml` 의 `publish.allowed_columns` 에 **명시된 컬럼만** 산출물에 포함됩니다.

- API에 새 필드가 추가되어도 자동으로 노출되지 않습니다.
- allowlist 밖 데이터는 정규화 단계에서 즉시 폐기되어 하류로 흐르지 않습니다.
- 이 목록이 비면 빌드가 실패합니다(의도된 안전장치 — 무심코 전량 게시되는 사고 방지).

## 4. XSS 방지

외부 API에서 받은 문자열을 HTML에 넣으므로, 데이터 경유 XSS가 실질적 위험입니다.

- Jinja2 `autoescape=True` **무조건 활성화**.
  > 개발 중 실제로 이 지점에서 결함이 있었습니다. `select_autoescape(["html","xml"])` 는
  > 파일 확장자로 판단하는데 템플릿이 `.html.j2` 라 `.j2` 로 인식되어 이스케이프가 꺼져 있었습니다.
  > 현재는 무조건 켜는 방식으로 고정했습니다. **절대 되돌리지 마십시오.**
- 템플릿에서 `|safe` 필터 사용 금지. `check` 명령이 검출합니다.
- `check` 는 정적 검사에 그치지 않고 **실제로 렌더링해 이스케이프 동작을 확인**합니다.
- 정규화 단계에서 제어문자를 제거하고 유니코드를 NFC 정규화합니다.

## 5. 서드파티 의존 0

생성된 페이지는 외부 스크립트·CDN·웹폰트·추적기를 **일절 로드하지 않습니다.**
차트는 서버측에서 SVG로 렌더링해 같은 도메인에 저장합니다.
따라서 공급망 공격(CDN 변조)과 방문자 추적 이슈가 없고, `Content-Security-Policy` 를
아래처럼 매우 엄격하게 설정할 수 있습니다.

```
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none';
                         style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self';
                         base-uri 'none'; frame-ancestors 'none'
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

> 대화형 탐색기를 켜면 `explorer.js` 가 필요하므로 `script-src` 는 `'none'` 이 아니라
> `'self'` 가 됩니다. 스크립트를 **별도 파일로 분리**했기 때문에 인라인 허용
> (`'unsafe-inline'`)이나 논스 없이 이 수준을 유지할 수 있습니다.

## 5-1. 대화형 탐색기의 보안 특성

- **서버로 아무것도 전송되지 않습니다.** 데이터를 한 번 내려받은 뒤 필터·집계·정렬·
  CSV 내보내기가 전부 브라우저 안에서 처리됩니다. 조건을 몇 번 바꿔도 추가 요청이 없습니다.
- **DOM 조작은 `textContent` 로만 합니다.** `innerHTML` 과 `eval` 을 쓰지 않으므로,
  허가 데이터에 스크립트 문자열이 섞여 있어도 실행되지 않습니다.
- **공개되는 데이터는 `explorer.columns` 에 적은 컬럼뿐**이며, 그 목록은 다시
  `publish.allowed_columns` 의 부분집합이어야 합니다(빌드 시 검증).
- `fetch` 는 `credentials: "omit"` 로 호출해 쿠키가 실려 나가지 않습니다.

## 6. 대외 API 예의 및 안정성

- 초당 요청 수 제한(`rate_limit_qps`), 지수 백오프 재시도, 타임아웃 필수.
- `max_pages` 상한으로 무한 페이징 방지.
- 리다이렉트 자동 추종 차단 — 응답이 다른 호스트로 유도되면 즉시 중단.

## 7. 데이터 분리

- `cache/` : API 원본 정규화 결과. 저장소에 커밋하지 않습니다.
- `output/` : 게시물. 빌드 시 **전량 삭제 후 재생성**하여 이전 데이터가 남지 않게 합니다.
- 게시는 `build` 라는 별도의 의도적 행위입니다. 수집만으로는 아무것도 공개되지 않습니다.

## 8. 법적·직업윤리 확인 사항

- **출처 표시 의무**: 공공데이터 이용 시 출처 표시가 필요합니다. `site.attribution` 을 삭제하지 마십시오.
- **재직 중 겸업**: 근로계약서·취업규칙의 겸업 및 경업금지 조항을 사전에 확인하십시오.
- **영업비밀 분리**: 이 파이프라인은 **공개 데이터만** 사용하도록 설계되어 있습니다.
  재직 회사의 내부 자료·미공개 심사 이력·고객 정보를 이 저장소에 절대 섞지 마십시오.
- **면책 문구**: 생성 페이지 하단에 "참고 자료이며 법적 효력이 있는 규제 해석이 아님"을 명시합니다.

## 9. 배포 전 점검

**Windows (PowerShell)**
```powershell
python run.py check
git status                                   # .env / cache 가 목록에 없어야 함
Get-ChildItem -Recurse -Include *.toml,*.py |
    Select-String "MFDS_API_KEY\s*="        # 결과가 없어야 함
git check-ignore -v .env                     # .env 가 무시되는지 확인
```

**macOS / Linux**
```bash
python run.py check
git status
grep -rn "MFDS_API_KEY=" --include="*.toml" --include="*.py" .
git check-ignore -v .env
```
