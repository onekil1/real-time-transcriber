@echo off
rem Транскрибатор - запуск с авто-обновлением из GitHub.
rem При каждом старте: git pull -> uv pip install -> run.py.
rem Если интернета нет или pull упал - запускаем текущую локальную версию.

setlocal
cd /d "%~dp0.."

echo === Проверяем обновления ===
where git >nul 2>&1
if errorlevel 1 (
  echo [WARN] git не найден - автообновление пропущено.
) else (
  if exist ".git" (
    git pull --ff-only --quiet
    if errorlevel 1 (
      echo [WARN] git pull не удался - запускаем текущую версию.
    ) else (
      echo     OK: код актуален.
    )
  ) else (
    echo [WARN] не git-репозиторий - автообновление пропущено.
  )
)

echo === Синхронизируем зависимости ===
where uv >nul 2>&1
if errorlevel 1 (
  echo [WARN] uv не найден - пропускаем sync. Запустите scripts\install.bat.
) else (
  uv pip install --quiet --python .venv\Scripts\python.exe -e .
  if errorlevel 1 echo [WARN] Не удалось синхронизировать зависимости.
)

if not exist ".venv\Scripts\python.exe" (
  echo [ОШИБКА] .venv не найден. Запустите scripts\install.bat.
  pause
  exit /b 1
)

echo === Запуск ===
".venv\Scripts\python.exe" run.py
pause
