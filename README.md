# Транскрибатор (real-time)

Локальное приложение для записи совещаний, транскрибации и автогенерации отчётов. Работает **офлайн** после установки.

**Поддерживаемые платформы:**
- **macOS (Apple Silicon)** — Whisper через MLX.
- **Windows + NVIDIA RTX** — Whisper через `faster-whisper` на CUDA 12.1.
- **Windows (CPU-only)** — `faster-whisper` на CPU (медленно).

LLM для отчётов — локальная **LM Studio** (OpenAI-совместимый API).

## Архитектура

- **FastAPI** на `127.0.0.1:8765` — REST + SSE прогресс.
- **Web UI** — список сессий, транскрипт, редактируемый Markdown-отчёт, экспорт в DOCX.
- **Menu bar** (`rumps`) — только macOS.
- **SQLite** в папке данных (см. `MEETING_SCRIBE_DATA`).

---

## 1. Предусловия (оба OS)

### 1.1. LM Studio
1. Скачать и установить с [lmstudio.ai](https://lmstudio.ai).
2. Загрузить модель (рекомендация: `Qwen2.5-7B-Instruct`).
3. Запустить локальный сервер (`Developer` → `Start Server`) на порту `1234`.

Проверка: `curl http://127.0.0.1:1234/v1/models` должен вернуть JSON.

### 1.2. Whisper-модель
Положить файлы модели в `models/whisper/<platform>/`:

| OS | Формат | Куда | Пример |
|---|---|---|---|
| macOS | MLX (`*.safetensors`, `*.npz`) | `models/whisper/mac/` | [`mlx-community/whisper-large-v3-turbo`](https://huggingface.co/mlx-community/whisper-large-v3-turbo) |
| Windows | CTranslate2 (`model.bin`, `config.json`, `tokenizer.json`, `vocabulary.txt`) | `models/whisper/win/` | [`Systran/faster-whisper-large-v3`](https://huggingface.co/Systran/faster-whisper-large-v3) |

---

## 2. Установка

### 2.0. Получение кода (один раз)

Проект распространяется через GitHub. Каждая машина должна получить исходники через `git clone` — тогда ярлык на рабочем столе будет сам подтягивать обновления при каждом запуске.

**macOS:**
```bash
cd ~/Desktop/projects   # или любая другая папка
git clone https://github.com/<org>/workspace_transcribe.git
cd workspace_transcribe
bash scripts/install-mac.sh
```

**Windows (PowerShell или CMD):**
```cmd
cd %USERPROFILE%\Desktop\projects
git clone https://github.com/<org>/workspace_transcribe.git
cd workspace_transcribe
scripts\install.bat
```

> Если Git не установлен: macOS — `xcode-select --install`; Windows — `winget install Git.Git`.
>
> Для приватного репозитория настройте SSH-ключ или Personal Access Token один раз — дальше автообновление будет работать прозрачно.

После установки на рабочем столе появится ярлык **Транскрибатор**. Он запускает приложение **с автообновлением** из GitHub — при каждом двойном клике выполняется `git pull`, подтягиваются изменённые зависимости, приложение стартует. Если интернета нет — запустится текущая локальная версия.



### 2.1. macOS (Apple Silicon)

```bash
cd path/to/workspace_transcribe
bash scripts/install-mac.sh
```

Что делает скрипт:
1. Ставит **Homebrew** (если нет).
2. Ставит **ffmpeg** через brew.
3. Ставит **uv** (менеджер пакетов).
4. Создаёт `.venv` на Python 3.11 и ставит Python-зависимости (включая `mlx-whisper`, `torch` как его транзитив, `rumps` для menu bar).
5. Проверяет Whisper-модель в `models/whisper/mac/`.
6. Проверяет, что LM Studio отвечает на `127.0.0.1:1234`.

Размер установленного `.venv` — ~2 GB (основной вес — `torch`, нужен `mlx-whisper`).

При **первом запуске** macOS запросит доступ к микрофону — разрешите в `System Settings → Privacy & Security → Microphone`.

### 2.2. Windows

Двойной клик по `scripts\install.bat` → выбрать пункт:
- `[1]` — Windows + NVIDIA RTX (ставит `torch` с CUDA 12.1).
- `[2]` — Windows без GPU (CPU-only).

Скрипт поставит Python 3.11, ffmpeg, uv через `winget`, создаст venv, установит зависимости, проверит GPU/модель/LM Studio и создаст **ярлык `Транскрибатор`** на рабочем столе + `start.bat` в корне проекта.

---

## 3. Запуск

### 3.1. macOS

**Вариант 1 — быстрый ярлык на рабочем столе** (создаётся вручную):
```bash
cp scripts/run-mac.sh ~/Desktop/Транскрибатор.command
# внутри .command отредактируйте абсолютный путь в строке `cd "..."` под ваш компьютер
chmod +x ~/Desktop/Транскрибатор.command
```
Двойной клик по `Транскрибатор.command` запустит сервер и откроет браузер.

**Вариант 2 — из терминала:**
```bash
bash scripts/run-mac.sh
```
Или напрямую:
```bash
uv run python run.py
```

В menu bar появится `🎙 Scribe`. Веб-UI открывается на `http://127.0.0.1:8765`.

### 3.2. Windows

- Двойной клик по ярлыку **Транскрибатор** на рабочем столе.
- Или двойной клик по `start.bat` в корне проекта.
- Или вручную: `.venv\Scripts\python.exe run.py`.

Веб-UI: `http://127.0.0.1:8765`.

---

## 4. Перенос проекта на другой компьютер

**Копируете:** всю папку проекта, **кроме `.venv`** (привязан к абсолютным путям текущей машины — на новой машине он сломается).

```bash
# с исходной машины
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.egg-info' \
  ~/Desktop/projects/workspace_transcribe/ \
  user@new-mac:~/Desktop/projects/workspace_transcribe/
```

Либо архивом:
```bash
tar --exclude='.venv' --exclude='__pycache__' --exclude='*.egg-info' \
  -czf workspace_transcribe.tar.gz -C ~/Desktop/projects workspace_transcribe
```

**На новой машине:**
- macOS → `bash scripts/install-mac.sh`
- Windows → двойной клик по `scripts\install.bat`

**Что переносится вместе с проектом:**
- Исходный код.
- `models/whisper/<platform>/` (~1.5 GB) — качать заново не надо.

**Что ставится отдельно на новой машине:**
- `.venv` — пересоздаётся установщиком.
- **LM Studio** + модель — ставится независимо.
- Пользовательские данные (БД сессий, аудио) — лежат в:
  - macOS: `~/Library/Application Support/MeetingScribe/`
  - Windows: `%APPDATA%\MeetingScribe\`
  
  Если нужны — копируйте отдельно.

Если путь к проекту на новой машине отличается — поправьте `cd "..."` в `~/Desktop/Транскрибатор.command` (macOS).

---

## 5. Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `MEETING_SCRIBE_ASR_BACKEND` | `mlx` (macOS) / `faster` (Windows) | Бэкенд ASR: `mlx` или `faster`. |
| `MEETING_SCRIBE_ASR_DEVICE` | `auto` (MLX) / `cuda` (faster) | Устройство для `faster-whisper`: `cuda` / `cpu`. |
| `MEETING_SCRIBE_ASR_COMPUTE` | `float16` (GPU) / `int8` (CPU) | Тип вычислений для CTranslate2. |
| `MEETING_SCRIBE_WHISPER` | зависит от бэкенда | HF-repo или путь. Приоритет у локальной модели в `models/whisper/<platform>/`. |
| `MEETING_SCRIBE_LMSTUDIO_URL` | `http://127.0.0.1:1234/v1` | Адрес LM Studio (OpenAI API). |
| `MEETING_SCRIBE_LMSTUDIO_MODEL` | (пусто) | Имя модели в LM Studio. Пусто = первая доступная. |
| `MEETING_SCRIBE_PORT` | `8765` | Порт сервера. |
| `MEETING_SCRIBE_DATA` | `~/Library/.../MeetingScribe` (Mac), `%APPDATA%\MeetingScribe` (Win) | Папка с БД и аудио. |
| `MEETING_SCRIBE_NO_MENUBAR` | авто на Windows | `1` — стартовать только сервер (для отладки на Mac). |

---

## 6. Шаблоны отчётов

Четыре типа: **Совещание**, **Выступление**, **Мозговой штурм**, **Планирование задач**. Промпты в `app/prompts/*.txt` — править текстом, код менять не нужно.

---

## 7. Траблшутинг

**`[ОШИБКА] .venv не найден`** при двойном клике по `.command` — значит папка проекта находится не по пути, прописанному внутри скрипта. Отредактируйте строку `cd "..."` в `~/Desktop/Транскрибатор.command` или перезапустите `bash scripts/install-mac.sh`.

**`bad interpreter: .../python3: no such file or directory`** при вызове `.venv/bin/pip` — venv сломан (проект переносили, а venv не пересоздали). Лечится:
```bash
rm -rf .venv
bash scripts/install-mac.sh
```

**LM Studio не отвечает** — запустите сервер в LM Studio (`Developer` → `Start Server`) и проверьте порт `1234`.

**В отчёте одни прочерки (`—`)** — в LM Studio у активной модели включён **thinking mode**. Qwen3 и подобные оборачивают ответ в `<think>...</think>`, парсер JSON падает, секции остаются пустыми. Выключите thinking в настройках модели в LM Studio и пересоберите отчёт (кнопка «Пересобрать отчёт» в UI).

**Нет звука с Zoom/Teams** — нужен виртуальный аудиодрайвер ([BlackHole](https://github.com/ExistentialAudio/BlackHole) или Loopback на Mac, VB-Cable на Windows). В коробке этого нет.

---

## Что не входит

- Диаризация спикеров.
- Захват системного звука (Zoom/Teams) — нужен BlackHole/Loopback/VB-Cable.
- Упаковка в `.app` / `.exe` / MSI — скриптовая установка в venv.
