# Транскрибатор (real-time)

Локальная запись совещаний → транскрибация → автогенерация отчёта (DOCX). Полностью офлайн, аудио и тексты не покидают машину.

**Платформы:** macOS (Apple Silicon) · Windows + NVIDIA RTX (CUDA 12.1) · Windows без GPU (медленно).

---

## Часть 1. Для пользователей

### Что делает программа

Записывает совещание с микрофона, превращает речь в текст прямо во время разговора, а в конце сама пишет отчёт (повестка, решения, задачи). Отчёт можно скачать в Word. Всё работает на вашем компьютере — никакие данные в интернет не уходят.

### Шаг 1. Установите LM Studio

Это бесплатная программа, которая пишет отчёт. Скачайте с [lmstudio.ai](https://lmstudio.ai), установите. Внутри LM Studio:

1. Найдите и загрузите модель — рекомендуем **Qwen2.5-7B-Instruct**.
2. Откройте вкладку **Developer** и нажмите **Start Server**.
3. В настройках модели **выключите thinking mode** — иначе отчёт будет состоять из прочерков.

Дальше LM Studio просто пусть работает в фоне.

### Шаг 2. Установите Транскрибатор

Есть два способа. Первый удобнее, потому что обновления потом ставятся в один клик.

#### Способ 1 — через Терминал (рекомендуется)

**На Mac.** Откройте программу **Терминал** (Cmd+Пробел → наберите «Терминал») и вставьте:

```bash
cd ~/Desktop
git clone https://github.com/onekil1/real-time-transcriber.git
cd real-time-transcriber
bash scripts/install-mac.sh
```

**На Windows.** Сначала установите [Git для Windows](https://git-scm.com/download/win) (просто всё «Далее»). Затем откройте **PowerShell** (правый клик по «Пуск» → Windows PowerShell) и вставьте:

```powershell
cd $env:USERPROFILE\Desktop
git clone https://github.com/onekil1/real-time-transcriber.git
cd real-time-transcriber
scripts\install.bat
```

Установщик спросит, есть ли у вас видеокарта NVIDIA (RTX): `[1]` да или `[2]` нет.

После установки на рабочем столе появится ярлык **Транскрибатор**.

#### Способ 2 — скачать архивом (если не хотите ставить Git)

1. Откройте [страницу последнего релиза](https://github.com/onekil1/real-time-transcriber/releases/latest) и скачайте файл **Source code (zip)**.
2. Распакуйте архив на рабочий стол. Получится папка `real-time-transcriber-…`.
3. Зайдите в эту папку и запустите установщик:
   - на Mac: двойной клик по `scripts/install-mac.sh` (если не запускается — правый клик → «Открыть»);
   - на Windows: двойной клик по `scripts/install.bat`.

Дальше так же — на рабочем столе появится ярлык **Транскрибатор**.

### Шаг 3. Модель распознавания речи

Большой файл (~1.5 ГБ) с моделью Whisper. Можно ничего не делать — программа сама скачает её при первом запуске. Если хотите положить вручную (например, без интернета):

- **Mac**: скачайте файлы со страницы [whisper-large-v3-mlx](https://huggingface.co/mlx-community/whisper-large-v3-mlx) и положите в папку `models/whisper/mac/` внутри проекта.
- **Windows**: скачайте со страницы [faster-whisper-large-v3](https://huggingface.co/Systran/faster-whisper-large-v3) → в `models/whisper/win/`.

### Как пользоваться

1. Убедитесь, что LM Studio запущена (в ней нажат **Start Server**).
2. Двойной клик по ярлыку **Транскрибатор** — откроется страница в браузере.
3. Нажмите **● Записать** — программа начнёт писать с микрофона, текст пойдёт сразу.
4. Нажмите **■ Стоп** — программа достроит отчёт.
5. Вверху страницы вкладки: **Отчёт** (готовый текст), **Редактор** (можно править руками), **Транскрипт** (полная стенограмма по времени), **Аудио** (прослушать запись).
6. Кнопка **Экспорт в DOCX** скачает отчёт в Word.
7. Кнопка **📖 Глоссарий** — впишите имена коллег и сложные термины через запятую, и программа перестанет их коверкать.

На Mac при первом запуске система попросит разрешение на микрофон — нажмите «Разрешить».

### Обновление

Раз в час программа сама проверяет, не вышла ли новая версия. Когда выходит — в правом нижнем углу появляется баннер. Жмёте **Обновить**, ждёте пару секунд, потом **Перезагрузить**. Всё внутри программы, руками ничего делать не нужно.

### Если что-то не работает

| Что видите | Что делать |
|---|---|
| «LM Studio недоступна» | Запустите LM Studio, нажмите **Start Server**, проверьте что модель загружена. |
| В отчёте одни прочерки `—` | В LM Studio выключите **thinking mode** у модели и нажмите «Пересобрать отчёт». |
| Mac не слышит микрофон | Системные настройки → Конфиденциальность → Микрофон → разрешите Терминалу. |
| Не слышно собеседника на созвоне | По умолчанию пишется только ваш голос. Чтобы писать ещё и звук из Zoom/Teams, поставьте [BlackHole](https://github.com/ExistentialAudio/BlackHole) (Mac) или VB-Cable (Windows). |
| Ярлык не запускается | Зайдите в папку `real-time-transcriber`, удалите вложенную папку `.venv` и запустите установщик заново. |

---

## Часть 2. Для разработчиков

### Запуск из репо без установщика

```bash
git clone https://github.com/onekil1/real-time-transcriber.git
cd real-time-transcriber
uv sync
uv run python run.py
```
Требования: `uv`, `ffmpeg`, Python 3.10–3.12. Headless: `MEETING_SCRIBE_NO_MENUBAR=1 uv run python run.py`.

### Архитектура

- **Backend** — FastAPI на `127.0.0.1:8765`, REST + SSE.
- **Recorder** — `sounddevice`, 30-секундные чанки с 2-сек overlap.
- **ASR** — MLX Whisper (mac) / faster-whisper + CTranslate2 (win, CUDA/CPU). Silero VAD на mac, встроенный VAD на win.
- **Pre-processing** — `ffmpeg -af "highpass=80,afftdn=12,dynaudnorm" -ar 16000 -ac 1`. Снижает WER ~2× на шумном микрофоне. Отключается `MEETING_SCRIBE_DENOISE=0`.
- **Word-level дедупликация** — на границах overlap'а слова режутся по `word.start`, не по `segment.end`.
- **LLM** — LM Studio на `127.0.0.1:1234` (OpenAI-совместимый API), map-reduce для длинных транскриптов.
- **Storage** — SQLite в `DATA_DIR` (`~/Library/Application Support/MeetingScribe` / `%APPDATA%\MeetingScribe`).
- **Menu bar** — `rumps` (только mac).
- **Updater** — GitHub Releases API + `git pull` + `uv sync`, стримом через SSE; на ZIP-установке делает `git init` поверх.

### Структура

```
app/
├── server.py       # FastAPI + SSE, пайплайн
├── recorder.py     # sounddevice + chunking
├── transcribe.py   # MLX / faster-whisper, VAD, denoise
├── summarize.py    # LM Studio, шаблоны, map-reduce, DOCX
├── storage.py      # SQLite
├── events.py       # per-session SSE bus
├── settings.py     # глоссарий
├── menubar.py      # rumps (mac)
├── updater.py      # GitHub Releases + git/uv
└── prompts/        # LLM-промпты по шаблонам
models/whisper/{mac,win}/
web/                # vanilla JS frontend
scripts/            # install-{mac.sh,win.bat}, launch-{mac.sh,win.bat}
uninstall-{mac.command,win.bat}   # полное удаление установки
```

### Переменные окружения

| Переменная | Дефолт | Описание |
|---|---|---|
| `MEETING_SCRIBE_ASR_BACKEND` | `mlx`/`faster` | Бэкенд ASR. |
| `MEETING_SCRIBE_ASR_DEVICE` | `auto`/`cuda` | `cuda` / `cpu` / `auto` (только faster). |
| `MEETING_SCRIBE_ASR_COMPUTE` | `float16`/`int8` | Precision CTranslate2. |
| `MEETING_SCRIBE_WHISPER` | — | HF repo ID или путь. Локальная папка имеет приоритет. |
| `MEETING_SCRIBE_DENOISE` | `1` | `0` — отключить ffmpeg-денойз. |
| `MEETING_SCRIBE_LMSTUDIO_URL` | `http://127.0.0.1:1234/v1` | Адрес LLM. |
| `MEETING_SCRIBE_LMSTUDIO_MODEL` | — | Пусто = первая доступная. |
| `MEETING_SCRIBE_LLM_MAX_TOKENS` | `2048` | Лимит на чанк отчёта. |
| `MEETING_SCRIBE_LLM_TEMPERATURE` | `0.2` | |
| `MEETING_SCRIBE_LLM_CHUNK_CHARS` | `8000` | Размер чанка для map-reduce. |
| `MEETING_SCRIBE_PORT` / `_HOST` | `8765` / `127.0.0.1` | API не защищён, не выставляйте наружу. |
| `MEETING_SCRIBE_DATA` | platform default | БД и аудио. |
| `MEETING_SCRIBE_NO_MENUBAR` | — | `1` — только сервер. |

### REST API

| Метод | Путь | |
|---|---|---|
| `POST` | `/api/sessions/start` | `{title, template}` |
| `POST` | `/api/sessions/{id}/stop` | |
| `POST` | `/api/upload` | multipart: `file, title, template` |
| `GET/PATCH/DELETE` | `/api/sessions[/{id}]` | CRUD |
| `GET` | `/api/sessions/{id}/{audio,docx}` | |
| `PATCH` | `/api/sessions/{id}/report` | сохранить правки |
| `POST` | `/api/sessions/{id}/regenerate` | пересобрать отчёт |
| `POST` | `/api/sessions/{id}/summarize-now` | промежуточный отчёт |
| `GET/PUT` | `/api/glossary` | |
| `GET` | `/api/templates`, `/api/health`, `/api/status`, `/api/version` | |
| `GET/POST` | `/api/update/{check,apply}` | `apply/stream` — SSE-прогресс |
| `POST` | `/api/restart` | спавн нового процесса + `os._exit` |

### SSE: `GET /api/sessions/{id}/events`

События: `recording`, `recording:stopped`, `asr:{chunk_start,chunk_done,partial,model_load,done}`, `transcribing`, `summarizing`, `llm:{start,chunk,done}`, `uploaded`, `done`, `error`. Стрим закрывается на `done`/`error`.

### Шаблоны отчётов

`app/summarize.py:TEMPLATES` — 4 шаблона (совещание / выступление / brainstorm / планирование). Свой шаблон: создать `app/prompts/<key>_ru.txt` (LLM должна вернуть валидный JSON), добавить запись в `TEMPLATES`, перезапустить.

### Подавление галлюцинаций

Whisper галлюцинирует на тишине («Субтитры сделал DimaTorzok» и пр.) — фильтруется по списку в `transcribe.py:_HALLUCINATION_MARKERS`. Плюс `temperature=(0.0..1.0)` fallback при низком `avg_logprob`.

### Глоссарий → Whisper

Подклеивается в `initial_prompt`; для faster-whisper ещё и в `hotwords`. Лимит ~224 токена (≈400–600 символов ru/en) — счётчик в UI предупреждает после 500.

### Перенос на другую машину

Копируйте проект **без `.venv`** (привязан к путям) — на новой машине просто запустите установщик. Пользовательские данные (БД, аудио) лежат отдельно в `DATA_DIR` — копируйте отдельно, если нужна история.

### Чего нет в коробке

- Диаризация спикеров (планируется pyannote).
- Захват системного звука — нужен виртуальный аудиодрайвер (BlackHole / VB-Cable).
- Упаковка в `.app`/`.exe`/MSI.
- Выбор аудио-устройства в UI — берётся системный default.
- Облачная версия — намеренно, всё локально.
