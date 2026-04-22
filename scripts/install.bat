@echo off
setlocal EnableDelayedExpansion

rem ===================================================================
rem  Транскрибатор (real-time) - установщик зависимостей и окружения
rem ===================================================================

rem Перейти в корень проекта (папка, где лежит pyproject.toml)
cd /d "%~dp0.."

:MENU
cls
echo ==========================================================
echo   Транскрибатор (real-time) - установщик
echo ==========================================================
echo.
echo  Выберите конфигурацию:
echo.
echo    [1] Windows + NVIDIA RTX (CUDA 12.1)   ^<-- рекомендуется
echo    [2] Windows без GPU (CPU-only, медленно)
echo    [3] Я на macOS - показать инструкцию
echo    [4] Выход
echo.
set /p CHOICE="Введите цифру: "

if "%CHOICE%"=="1" goto INSTALL_WIN_RTX
if "%CHOICE%"=="2" goto INSTALL_WIN_CPU
if "%CHOICE%"=="3" goto MAC_HINT
if "%CHOICE%"=="4" exit /b 0
echo Неверный ввод.
pause
goto MENU


:MAC_HINT
cls
echo ==========================================================
echo   Установка на macOS
echo ==========================================================
echo.
echo  Этот .bat-файл работает только в Windows.
echo  На macOS откройте Terminal в папке проекта и выполните:
echo.
echo      bash scripts/install-mac.sh
echo.
pause
goto MENU


:INSTALL_WIN_CPU
set ASR_DEVICE=cpu
set NEED_TORCH=0
goto INSTALL_COMMON

:INSTALL_WIN_RTX
set ASR_DEVICE=cuda
set NEED_TORCH=1
goto INSTALL_COMMON


:INSTALL_COMMON
cls
echo ==========================================================
echo   Установка (режим: %ASR_DEVICE%)
echo ==========================================================
echo.

rem --- 1. Python 3.10+ -----------------------------------------------
echo [1/9] Проверяем Python...
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo     Python не найден. Устанавливаем через winget...
  winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements --silent
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось поставить Python. Поставьте вручную с https://python.org и перезапустите скрипт.
    pause
    goto MENU
  )
  echo     Перезапустите терминал, чтобы PATH подхватил Python, и запустите install.bat снова.
  pause
  goto MENU
) else (
  for /f "tokens=*" %%v in ('py -3 --version') do echo     OK: %%v
)

rem --- 2. ffmpeg -----------------------------------------------------
echo [2/9] Проверяем ffmpeg...
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo     ffmpeg не найден. Устанавливаем через winget...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent
  if errorlevel 1 (
    echo [WARN] Автоустановка ffmpeg не удалась. Установите вручную: https://ffmpeg.org/
  ) else (
    echo     OK. Возможно, нужно перезапустить терминал для обновления PATH.
  )
) else (
  echo     OK
)

rem --- 3. uv ---------------------------------------------------------
echo [3/9] Проверяем uv (менеджер пакетов)...
where uv >nul 2>&1
if errorlevel 1 (
  echo     uv не найден. Устанавливаем...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
  where uv >nul 2>&1
  if errorlevel 1 (
    echo [ОШИБКА] uv не установился. Установите вручную: https://docs.astral.sh/uv/
    pause
    goto MENU
  )
  echo     OK
) else (
  echo     OK
)

rem --- 4. venv -------------------------------------------------------
echo [4/9] Создаём виртуальное окружение .venv...
if not exist ".venv" (
  uv venv --python 3.11 .venv
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать venv.
    pause
    goto MENU
  )
) else (
  echo     .venv уже существует - пропускаем.
)

rem --- 5. Python-зависимости -----------------------------------------
echo [5/9] Устанавливаем зависимости проекта...
uv pip install --python .venv\Scripts\python.exe -e .
if errorlevel 1 (
  echo [ОШИБКА] Установка зависимостей не удалась.
  pause
  goto MENU
)

rem --- 6. torch + CUDA (только для RTX) -----------------------------
if "%NEED_TORCH%"=="1" (
  echo [6/9] Устанавливаем PyTorch с поддержкой CUDA 12.1...
  uv pip install --python .venv\Scripts\python.exe torch --index-url https://download.pytorch.org/whl/cu121
  if errorlevel 1 (
    echo [WARN] Не удалось поставить torch+cu121. CUDA-путь не будет работать.
  )
) else (
  echo [6/9] Пропускаем torch - CPU-режим не требует PyTorch.
)

rem --- 7. Проверка GPU ----------------------------------------------
echo [7/9] Проверяем GPU/драйверы...
if not "%ASR_DEVICE%"=="cuda" goto GPU_DONE_CPU
where nvidia-smi >nul 2>&1
if errorlevel 1 goto GPU_NO_NVIDIA
nvidia-smi -L
.venv\Scripts\python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available())" 2>nul
goto GPU_DONE
:GPU_NO_NVIDIA
echo [WARN] nvidia-smi не найден - драйверы NVIDIA не установлены. CUDA работать не будет.
goto GPU_DONE
:GPU_DONE_CPU
echo     CPU-режим - проверка GPU не нужна.
:GPU_DONE

rem --- 8. Whisper-модель --------------------------------------------
echo [8/9] Проверяем Whisper-модель...
if exist "models\whisper\win\model.bin" goto WHISPER_OK
echo [WARN] Модель Whisper ^(CTranslate2^) не найдена в models\whisper\win\.
echo        Положите файлы модели туда: model.bin, config.json, tokenizer.json, vocabulary.txt
echo        Скачать можно отсюда: https://huggingface.co/Systran/faster-whisper-large-v3
goto WHISPER_DONE
:WHISPER_OK
echo     OK: models\whisper\win\model.bin
:WHISPER_DONE

rem --- 9. LM Studio --------------------------------------------------
echo [9/9] Проверяем LM Studio (http://127.0.0.1:1234/v1)...
curl.exe -fsS --max-time 3 http://127.0.0.1:1234/v1/models >nul 2>&1
if errorlevel 1 (
  echo [WARN] LM Studio не отвечает. Установите её с https://lmstudio.ai,
  echo        загрузите модель и запустите локальный сервер на порту 1234.
) else (
  echo     OK: LM Studio отвечает
)

set "PROJECT=%CD%"

rem --- start.bat в корне проекта ------------------------------------
echo.
echo Создаём start.bat в корне проекта...
> "%PROJECT%\start.bat" echo @echo off
>> "%PROJECT%\start.bat" echo cd /d "%%~dp0"
if /i "%ASR_DEVICE%"=="cpu" >> "%PROJECT%\start.bat" echo set "MEETING_SCRIBE_ASR_DEVICE=cpu"
>> "%PROJECT%\start.bat" echo ".venv\Scripts\python.exe" run.py
>> "%PROJECT%\start.bat" echo pause
echo     Создан: %PROJECT%\start.bat

rem --- Ярлык на рабочем столе ---------------------------------------
echo Создаём ярлык на рабочем столе...
set "LNK=%USERPROFILE%\Desktop\Транскрибатор.lnk"
set "PS_CMD=$sh = New-Object -ComObject WScript.Shell; $ps = $sh.CreateShortcut('%LNK%'); $ps.TargetPath = '%PROJECT%\scripts\launch.bat'; $ps.WorkingDirectory = '%PROJECT%'; $ps.IconLocation = '%SystemRoot%\System32\shell32.dll,138'; $ps.Save()"
powershell -NoProfile -Command "%PS_CMD%"
echo     Ярлык: %LNK%

echo.
echo ==========================================================
echo   Готово!
echo ==========================================================
echo   Запуск:   двойной клик по ярлыку "Транскрибатор" на рабочем столе
echo             (ярлык при каждом запуске подтянет обновления из GitHub)
echo   Без обновления: двойной клик по start.bat в корне проекта
echo   Веб-UI:   http://127.0.0.1:8765
echo ==========================================================
echo.
pause
goto MENU
