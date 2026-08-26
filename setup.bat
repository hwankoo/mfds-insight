@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo  MFDS Insight - 최초 설치
echo ============================================================
echo.

set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY goto no_python

echo [1/4] 파이썬 확인
%PY% --version
echo.

if exist ".venv\Scripts\python.exe" goto venv_ok
echo [2/4] 가상환경 생성 중...
%PY% -m venv .venv
if errorlevel 1 goto venv_fail
goto venv_done
:venv_ok
echo [2/4] 가상환경이 이미 있습니다. 건너뜁니다.
:venv_done
echo.

echo [3/4] 패키지 설치 중... 1~2분 걸릴 수 있습니다.
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_fail
echo.

if exist ".env" goto env_ok
copy /y ".env.example" ".env" >nul
echo [4/4] .env 파일을 만들었습니다.
echo.
echo        메모장이 열립니다. 아래 세 줄을 채우고 저장하십시오.
echo          MFDS_API_KEY  = 공공데이터포털 인증키
echo          MFDS_BASE_URL = 요청주소 - 오퍼레이션 제외
echo          MFDS_ENDPOINT = /오퍼레이션명
echo.
pause
notepad .env
goto done
:env_ok
echo [4/4] .env 파일이 이미 있습니다. 건너뜁니다.

:done
echo.
echo ============================================================
echo  설치 완료. 이제 menu.bat 을 실행하십시오.
echo ============================================================
goto end

:no_python
echo [오류] 파이썬을 찾을 수 없습니다.
echo        https://www.python.org 에서 설치하십시오.
echo        설치 화면에서 "Add Python to PATH" 를 반드시 체크하십시오.
goto end

:venv_fail
echo [오류] 가상환경 생성에 실패했습니다.
goto end

:pip_fail
echo.
echo [오류] 패키지 설치에 실패했습니다. 위 메시지를 확인하십시오.
goto end

:end
echo.
pause
