@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto not_installed
set "PY=.venv\Scripts\python.exe"

:menu
cls
echo ============================================================
echo  MFDS Insight
echo ============================================================
echo.
echo    1. 설정 점검             check
echo    2. 응답 구조 확인         probe
echo    3. 원본 300건 내려받기     dump
echo    4. 시험 수집+미리보기     run --sample 2000
echo    5. 전체 수집              fetch
echo    6. 사이트 생성            build
echo    7. 브라우저로 확인         serve
echo    8. 명령창 열기            직접 입력
echo    0. 종료
echo.
set "sel="
set /p sel="번호 선택: "

if "%sel%"=="1" goto c_check
if "%sel%"=="2" goto c_probe
if "%sel%"=="3" goto c_dump
if "%sel%"=="4" goto c_sample
if "%sel%"=="5" goto c_fetch
if "%sel%"=="6" goto c_build
if "%sel%"=="7" goto c_serve
if "%sel%"=="8" goto c_shell
if "%sel%"=="0" exit /b 0
goto menu

:c_check
%PY% run.py check
goto back

:c_probe
%PY% run.py probe
goto back

:c_dump
%PY% run.py dump --sample 300
echo.
echo cache 폴더를 엽니다.
start "" explorer.exe "%~dp0cache"
goto back

:c_sample
rem 시험 수집분은 cache\sample 에 저장되어 정식 캐시(raw)를 덮어쓰지 않습니다.
%PY% run.py run --sample 2000
goto back

:c_fetch
echo 전체 수집은 3~5분 걸립니다. 진행 상황이 계속 표시됩니다.
echo.
%PY% run.py fetch
goto back

:c_build
%PY% run.py build
goto back

:c_serve
echo.
echo 브라우저가 자동으로 열립니다. 종료하려면 Ctrl+C 를 누르십시오.
echo.
%PY% run.py serve
goto back

:c_shell
start "MFDS Insight" cmd /k ""%~dp0.venv\Scripts\activate.bat" && cd /d "%~dp0""
goto menu

:back
echo.
pause
goto menu

:not_installed
echo [오류] 설치가 되어 있지 않습니다. 먼저 setup.bat 을 실행하십시오.
echo.
pause
exit /b 1
