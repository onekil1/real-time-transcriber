@echo off
rem ==========================================================
rem  Reset Транскрибатор: ПОЛНОЕ удаление всего в папке проекта
rem  (включая веса моделей, БД, venv). После — заново склонировать
rem  репо и запустить install.bat. Модель Whisper при первом
rem  запуске скачается с HuggingFace в models\whisper\win\.
rem  Файл должен лежать В КОРНЕ проекта и запускаться оттуда.
rem ==========================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "SELF=%~nx0"

echo ==========================================================
echo  ВНИМАНИЕ: будет удалено ВСЁ в папке
echo    %CD%
echo  включая:
echo    - models\ (веса Whisper, ~1.5-3 ГБ — придётся качать заново)
echo    - data\   (БД с сессиями и аудио)
echo    - .venv\  (venv с зависимостями)
echo    - app\, web\, scripts\, .git\ и пр.
echo  Останется только %SELF% (этот файл).
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
  rd /s /q "%%D" 2>nul
  if exist "%%D" echo   [WARN] не удалось удалить: %%D
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
echo  Готово. В папке остался только %SELF%.
dir /b
echo ==========================================================
echo.
echo  Дальше (по одной строке в cmd, в этой же папке):
echo.
echo    git clone https://github.com/onekil1/real-time-transcriber.git tmp
echo    xcopy /e /h /y tmp\* .
echo    xcopy /e /h /y tmp\.* .
echo    rd /s /q tmp
echo    scripts\install.bat
echo.
echo  При первом запуске программа сама скачает модель Whisper
echo  с HuggingFace прямо в models\whisper\win\ — никаких ручных
echo  шагов с моделью не нужно.
echo ==========================================================
pause
