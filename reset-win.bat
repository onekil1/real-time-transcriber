@echo off
rem ==========================================================
rem  Reset Транскрибатор: удаляет всё в папке проекта, КРОМЕ
rem  models\ (веса Whisper) и самого этого скрипта.
rem  Файл должен лежать В КОРНЕ проекта (рядом с pyproject.toml)
rem  и запускаться оттуда.
rem ==========================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "SELF=%~nx0"

echo ==========================================================
echo  ВНИМАНИЕ: будет удалено ВСЁ в папке
echo    %CD%
echo  КРОМЕ:
echo    - models\ (веса Whisper)
echo    - %SELF% (этот файл)
echo.
echo  data\ (БД с сессиями), .venv\, app\, web\, .git\ и пр. —
echo  всё это удалится. Перед этим убедитесь, что записанные
echo  сессии вам не нужны.
echo ==========================================================
echo.
set /p CONFIRM="Введите YES (заглавными) для продолжения: "
if /i not "%CONFIRM%"=="YES" (
  echo Отменено.
  pause
  exit /b 1
)

echo.
echo Удаляю папки...
for /d %%D in (*) do (
  if /i not "%%~nxD"=="models" (
    rd /s /q "%%D" 2>nul
    if exist "%%D" echo   [WARN] не удалось удалить: %%D
  )
)

echo Удаляю файлы...
for %%F in (*) do (
  if /i not "%%~nxF"=="%SELF%" del /f /q "%%F" 2>nul
)

rem скрытые dot-файлы (.gitignore, .env и т.п.)
for %%F in (.*) do (
  if not "%%~nxF"=="." if not "%%~nxF"==".." del /f /q "%%F" 2>nul
)

echo.
echo ==========================================================
echo  Готово. Что осталось в папке:
dir /b
echo ==========================================================
echo.
echo  Дальше (по одной строке в cmd):
echo.
echo    git clone https://github.com/onekil1/real-time-transcriber.git tmp
echo    xcopy /e /h /y tmp\* .
echo    xcopy /e /h /y tmp\.* .
echo    rd /s /q tmp
echo    scripts\install.bat
echo.
echo  models\ с весами на месте — заново качать не надо.
echo ==========================================================
pause
