# Транскрибатор (real-time)

Локальное приложение для записи совещаний, транскрибации и автогенерации отчётов. Работает **офлайн** после установки, не отправляет аудио в облако.

**Поддерживаемые платформы:**
- **macOS (Apple Silicon)** — M1/M2/M3/M4.
- **Windows + NVIDIA RTX** — с CUDA 12.1.
- **Windows (без GPU)** — медленно, но работает.

---

# Часть 1. Для обычных пользователей

## Что делает программа

1. Пишет звук с микрофона (или вы загружаете готовый файл).
2. Превращает речь в текст прямо во время записи.
3. Когда вы нажимаете «Стоп» — строит структурированный отчёт (повестка, решения, задачи и т.п.).
4. Даёт редактировать отчёт и скачать его в DOCX.

Всё локально: ваш звук и тексты никуда не уходят.

## Что нужно установить один раз

1. **LM Studio** — это движок, который пишет отчёт. Скачайте с [lmstudio.ai](https://lmstudio.ai), установите, внутри LM Studio загрузите модель (рекомендуем `Qwen2.5-7B-Instruct`) и нажмите `Developer → Start Server`. Дальше трогать её не надо — просто пусть работает в фоне.

2. **Модель распознавания речи (Whisper)** — большой файл ~1.5 GB. Скачайте с HuggingFace:
   - **macOS**: [`mlx-community/whisper-large-v3-mlx`](https://huggingface.co/mlx-community/whisper-large-v3-mlx) → положите файлы в папку `models/whisper/mac/`
   - **Windows**: [`Systran/faster-whisper-large-v3`](https://huggingface.co/Systran/faster-whisper-large-v3) → положите файлы в `models/whisper/win/`

3. **Само приложение** — установщик сделает всё остальное (ниже).

## Установка приложения

### macOS

Откройте Терминал и выполните:

```bash
cd ~/Desktop
git clone https://github.com/onekil1/real-time-transcriber.git
cd real-time-transcriber
bash scripts/install-mac.sh
```

Установщик поставит нужные компоненты (Homebrew, ffmpeg, uv, Python-окружение) и создаст на рабочем столе ярлык **Транскрибатор**.

### Windows

1. Скачайте и установите Git: [git-scm.com](https://git-scm.com/download/win).
2. Откройте PowerShell и выполните:

```powershell
cd $env:USERPROFILE\Desktop
git clone https://github.com/onekil1/real-time-transcriber.git
cd real-time-transcriber
scripts\install.bat
```

3. Установщик спросит: `[1]` RTX-видеокарта, `[2]` без GPU — выберите свой вариант. Появится ярлык **Транскрибатор** на рабочем столе.

## Как запустить и пользоваться

1. Убедитесь, что LM Studio запущена (в ней нажат `Start Server`).
2. Двойной клик по ярлыку **Транскрибатор** на рабочем столе.
3. Откроется страница `http://127.0.0.1:8765` в браузере.
4. Нажмите **● Записать** — начнётся запись с микрофона. Текст пойдёт в реальном времени.
5. Нажмите **■ Стоп** — запись остановится, программа достроит отчёт.
6. Вкладки в интерфейсе: **Отчёт** (просмотр), **Редактор** (ручные правки), **Транскрипт** (полный текст по времени), **Аудио** (прослушать запись).
7. Кнопка **Экспорт в DOCX** — скачать отчёт в Word.

**macOS при первом запуске попросит разрешение на микрофон** — нажмите «Разрешить» или откройте `Системные настройки → Приватность → Микрофон`.

## Обновление программы

Программа сама проверяет GitHub раз в час. Когда выходит новая версия, в правом нижнем углу появляется баннер:

> Доступна новая версия 0.1.3. [Обновить] [Позже]

Нажмите **Обновить** → подтвердите → подождите пару секунд → перезапустите программу (закройте окно и кликните по ярлыку снова). Всё.

Если не хотите сейчас — кнопка «Позже» уберёт баннер до следующей версии.

## Типы отчётов

В момент начала записи вы выбираете шаблон — от него зависит формат итогового отчёта:

- **Совещание** — повестка, резюме, решения, открытые вопросы.
- **Выступление** — участники, тезисы, выводы.
- **Мозговой штурм** — идеи, направления, следующие шаги.
- **Планирование задач** — цели, задачи, приоритеты, блокеры.

## Глоссарий

Кнопка 📖 **Глоссарий** в левой панели — сюда впишите имена коллег, аббревиатуры и термины через запятую. Распознаватель речи будет знать, как они правильно пишутся. Применяется ко всем сессиям.

Лимит ~500 символов (Whisper режет длинные подсказки).

## Если что-то не работает

| Проблема | Что делать |
|---|---|
| «LM Studio недоступна» | Запустите LM Studio, убедитесь, что нажали `Developer → Start Server`, и что модель загружена. |
| В отчёте везде прочерки `—` | В LM Studio у модели включён **thinking mode**. Откройте настройки модели в LM Studio и отключите его. Потом нажмите «Пересобрать отчёт». |
| Не записывает с микрофона (macOS) | Дайте разрешение в `Системные настройки → Приватность → Микрофон`. |
| Не слышно собеседника на созвоне | По умолчанию пишется только ваш микрофон. Для захвата системного звука нужна сторонняя программа: [BlackHole](https://github.com/ExistentialAudio/BlackHole) (бесплатно, macOS) или VB-Cable (бесплатно, Windows). |
| Ярлык не запускается | Удалите папку `.venv` внутри `real-time-transcriber` и запустите установщик заново. |

---

# Часть 2. Для продвинутых пользователей

## Архитектура

- **Backend**: FastAPI на `127.0.0.1:8765`, REST + SSE для прогресса в реальном времени.
- **Recorder**: `sounddevice` пишет WAV + одновременно нарезает 30-секундные чанки с 2-секундным overlap.
- **ASR**:
  - macOS → **MLX Whisper** (нативно под Apple Silicon, использует Neural Engine/GPU).
  - Windows → **faster-whisper** (CTranslate2 backend, CUDA/CPU).
- **VAD**: Silero VAD на macOS + встроенный VAD в faster-whisper на Windows — отсекает тишину до Whisper.
- **Pre-processing**: ffmpeg-фильтр (`highpass=80,afftdn,dynaudnorm`) перед подачей в Whisper — убирает гул, клавиатуру, нормализует громкость. Заодно ресемплит в 16 kHz mono.
- **LLM**: локальная LM Studio на `127.0.0.1:1234` (OpenAI-совместимый API). Map-reduce для длинных транскриптов.
- **Storage**: SQLite в `DATA_DIR`, сегменты хранятся с word-level дедупликацией на границах чанков.
- **Menu bar** (только macOS): `rumps` — иконка, таймер записи, быстрый старт/стоп.
- **Updater**: проверяет GitHub Releases API, запускает `git pull --ff-only` + `uv sync` из Web UI.

## Структура репозитория

```
app/
├── config.py       # env-переменные, пути, дефолты
├── server.py       # FastAPI роуты + SSE, пайплайн микрофона и upload
├── recorder.py     # sounddevice → WAV + чанкер с overlap
├── transcribe.py   # ASR: MLX / faster-whisper, VAD, denoise, word timestamps
├── summarize.py    # LM Studio client, шаблоны отчётов, map-reduce, DOCX export
├── storage.py      # SQLite: sessions, segments, reports
├── events.py       # Per-session event bus для SSE
├── settings.py     # Глобальный глоссарий
├── menubar.py      # rumps-приложение (macOS)
├── updater.py      # GitHub Releases + git pull + uv sync
└── prompts/        # Текстовые промпты для LLM по шаблонам
models/whisper/
├── mac/            # MLX: *.safetensors / *.npz + config.json
└── win/            # CT2: model.bin + config.json + tokenizer.json + vocabulary.txt
web/                # Статический frontend (vanilla JS)
scripts/            # install-mac.sh, install.bat, launch-*, run-mac.sh
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `MEETING_SCRIBE_ASR_BACKEND` | `mlx` (mac) / `faster` (win) | Какой бэкенд использовать. |
| `MEETING_SCRIBE_ASR_DEVICE` | `auto` (MLX) / `cuda` (faster) | `cuda` / `cpu` / `auto`. Только для faster. |
| `MEETING_SCRIBE_ASR_COMPUTE` | `float16` (GPU) / `int8` (CPU) | Precision для CTranslate2. `float16`, `int8`, `int8_float16`, `float32`. |
| `MEETING_SCRIBE_WHISPER` | зависит от бэкенда | HF-repo ID или путь к модели. Локальная папка имеет приоритет. |
| `MEETING_SCRIBE_DENOISE` | `1` | Включить ffmpeg-денойз перед Whisper. `0` / `false` — отключить. |
| `MEETING_SCRIBE_LMSTUDIO_URL` | `http://127.0.0.1:1234/v1` | Адрес LLM. |
| `MEETING_SCRIBE_LMSTUDIO_MODEL` | (пусто) | ID модели в LM Studio. Пусто = первая доступная. |
| `MEETING_SCRIBE_LMSTUDIO_KEY` | `lm-studio` | API-ключ (LM Studio не проверяет, но FastAPI ожидает header). |
| `MEETING_SCRIBE_LLM_MAX_TOKENS` | `2048` | Лимит генерации на один чанк отчёта. |
| `MEETING_SCRIBE_LLM_TEMPERATURE` | `0.2` | Температура LLM. |
| `MEETING_SCRIBE_LLM_CHUNK_CHARS` | `8000` | Размер чанка транскрипта для map-reduce. |
| `MEETING_SCRIBE_PORT` | `8765` | Порт FastAPI. |
| `MEETING_SCRIBE_HOST` | `127.0.0.1` | Хост FastAPI. Менять на `0.0.0.0` на свой риск — API не защищён. |
| `MEETING_SCRIBE_DATA` | `~/Library/.../MeetingScribe` (mac), `%APPDATA%\MeetingScribe` (win) | Папка с БД и аудио. |
| `MEETING_SCRIBE_NO_MENUBAR` | (не задана) | `1` — запустить только сервер, без menu bar. Полезно для headless и отладки. |

## Pre-processing перед Whisper

В `app/transcribe.py` каждый WAV перед Whisper проходит через:

```
ffmpeg -af "highpass=f=80,afftdn=nr=12,dynaudnorm=f=200:g=15" -ac 1 -ar 16000
```

Цепочка:
- `highpass=80` — срезает низкочастотный гул (вентилятор, кондиционер, сетевой фон 50 Гц).
- `afftdn=nr=12` — спектральный денойз (FFT-based noise reduction), 12 дБ подавления.
- `dynaudnorm` — динамическая нормализация громкости: выравнивает тихие и громкие участки.
- Ресемплинг в **16 kHz mono** — нативный формат Whisper, экономит I/O и избегает внутреннего ресемплинга модели.

Отключается переменной `MEETING_SCRIBE_DENOISE=0`. Если ffmpeg не найден — шаг тихо пропускается.

На шумном микрофоне даёт **снижение WER примерно в 2 раза**. На чистой студийной записи разница минимальна.

## VAD (Voice Activity Detection)

**macOS / MLX**: Silero VAD запускается до Whisper. Склеивает только сегменты речи (`min_silence_duration_ms=500`) и пересчитывает таймстемпы обратно в исходное время. Если в чанке только тишина — возвращает пустой результат мгновенно.

**Windows / faster-whisper**: встроенный `vad_filter=True` с теми же параметрами.

Это дополнительно к денойзу — VAD отсекает молчание, денойз чистит что осталось.

## Word-level дедупликация

Чанки в recorder перекрываются на 2 секунды. Без обработки это даёт дубли слов на границах. Решение:

1. В обоих бэкендах включён `word_timestamps=True`.
2. На каждом новом чанке получаем слова с абсолютными таймстемпами (с учётом `chunk.start_sec`).
3. `_dedup_overlap()` в `server.py` отрезает слова, у которых `word.start < last_segment_end - 0.15s`.
4. Оставшиеся слова склеиваются в чистый текст.
5. Если у сегмента нет word-данных (редкий случай) — fallback на старое правило по `segment.end`.

Результат: ни потерянных, ни дублированных слов на границах overlap'а.

## Подавление галлюцинаций

Whisper склонен галлюцинировать на тишине — чаще всего «Субтитры сделал DimaTorzok», «Продолжение следует», «Подпишитесь на канал» и т.п. Блок-лист в `transcribe.py:_HALLUCINATION_MARKERS` фильтрует такие сегменты на выходе модели. Если замечаете повторяющийся мусор, добавьте фразу в этот список.

Плюс: `temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)` — fallback от жадного декодинга к сэмплированию при низком avg_logprob. Работает из коробки в mlx-whisper и faster-whisper.

## Глоссарий → initial_prompt + hotwords

Глоссарий подклеивается к `initial_prompt` Whisper'а:
```
"Стенограмма рабочего совещания на русском языке. ... Участники и термины: Иван Петров, API Gateway, SLA, ..."
```

Для faster-whisper дополнительно передаётся в параметр `hotwords` (буст логитов на эти токены). MLX-whisper этого параметра не поддерживает — работает только через prompt.

**Жёсткий лимит Whisper'а — ~224 токена на prompt** (≈400–600 символов для смешанного ru/en текста). Всё сверх — игнорируется. Поэтому счётчик в UI предупреждает после 500 символов.

## Встроенный апдейтер

Модуль `app/updater.py`:

- `check()` → GET `https://api.github.com/repos/onekil1/real-time-transcriber/releases/latest`, сравнение семвера с `importlib.metadata.version("meeting-scribe")` (fallback — парсинг `pyproject.toml`).
- `apply()` → `git pull --ff-only` + `uv sync` в `PROJECT_ROOT`. Возвращает логи stdout/stderr каждого шага.

REST-интерфейс: `GET /api/update/check`, `POST /api/update/apply`.

Frontend (`web/app.js`): проверка при загрузке UI и раз в час, показ баннера, подтверждение через `confirm()`, отображение логов при ошибке, дисмисс текущей версии через `sessionStorage`.

**Что апдейтер НЕ чистит** (намеренно):
- `__pycache__/` — безвредные stale .pyc файлы (Python 3 их не импортирует без .py).
- `data/audio/chunks/<sid>/` — временные чанки, оставшиеся после аварийного завершения.
- Веса моделей в `models/whisper/*/` (явно исключено).
- БД в `DATA_DIR`.

`git pull` сам удаляет файлы кода, `uv sync` удаляет снятые с поддержки пакеты из `.venv`.

## Шаблоны отчётов

В `app/summarize.py:TEMPLATES` — 4 шаблона, каждый состоит из:
- `label` — название в UI;
- `prompt_file` — путь к LLM-промпту в `app/prompts/`;
- `sections` — список `(json_key, heading, kind)`, где `kind` = `"list"` или `"text"`. Определяет структуру JSON-ответа LLM и markdown-рендеринг.

Как добавить свой шаблон:
1. Создать `app/prompts/<key>_ru.txt` с инструкцией для LLM (должна требовать валидный JSON с нужными полями).
2. Добавить запись в `TEMPLATES`.
3. Перезапустить сервер. Шаблон появится в UI автоматически.

## Map-reduce для длинных транскриптов

Если транскрипт > `LLM_CHUNK_CHARS` (8000 по умолчанию) — `summarize._chunk_text` режет его по границам предложений/абзацев. Каждый чанк обрабатывается отдельно, результаты сливаются в `_merge_reports`: списки объединяются с дедупликацией, текстовые поля конкатенируются и сокращаются до 5 предложений (`summary`) или 1 (`topic`).

## API

### REST

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/api/sessions/start` | Начать запись. Body: `{title, template}`. |
| `POST` | `/api/sessions/{id}/stop` | Остановить запись. |
| `POST` | `/api/upload` | Загрузить готовый файл. Multipart: `file`, `title`, `template`. |
| `GET` | `/api/sessions` | Список всех сессий. |
| `GET` | `/api/sessions/{id}` | Полные данные сессии (transcript + report). |
| `PATCH` | `/api/sessions/{id}` | Переименовать / сменить шаблон. |
| `DELETE` | `/api/sessions/{id}` | Удалить сессию. |
| `GET` | `/api/sessions/{id}/audio` | Скачать оригинальный WAV. |
| `GET` | `/api/sessions/{id}/docx` | Экспорт в DOCX. |
| `PATCH` | `/api/sessions/{id}/report` | Сохранить ручные правки отчёта. |
| `POST` | `/api/sessions/{id}/regenerate` | Пересобрать отчёт с другим шаблоном/промптом. |
| `POST` | `/api/sessions/{id}/summarize-now` | Промежуточный отчёт без остановки записи. |
| `GET` | `/api/glossary` / `PUT` | Чтение/сохранение глоссария. |
| `GET` | `/api/templates` | Список шаблонов. |
| `GET` | `/api/health` | LLM + Whisper статус. |
| `GET` | `/api/status` | Текущее состояние записи и активности бэкендов. |
| `GET` | `/api/update/check` | Проверить новую версию на GitHub. |
| `POST` | `/api/update/apply` | Выполнить `git pull` + `uv sync`. |

### SSE

`GET /api/sessions/{id}/events` — server-sent events с прогрессом обработки. Стрим закрывается на событии `done` / `error`.

События: `recording`, `recording:stopped`, `asr:chunk_start`, `asr:chunk_done`, `asr:partial` (текст живого куска), `asr:model_load`, `asr:done`, `transcribing`, `summarizing`, `llm:start`, `llm:chunk`, `llm:done`, `uploaded`, `done`, `error`.

## Перенос на другой компьютер

Копировать **всю папку проекта кроме `.venv`** (он привязан к абсолютным путям):

```bash
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.egg-info' \
  ~/Desktop/projects/real-time-transcriber/ \
  user@new-mac:~/Desktop/projects/real-time-transcriber/
```

Или архивом:
```bash
tar --exclude='.venv' --exclude='__pycache__' --exclude='*.egg-info' \
  -czf transcriber.tar.gz -C ~/Desktop/projects real-time-transcriber
```

На новой машине запустить установщик (`install-mac.sh` / `install.bat`) — он пересоздаст `.venv`.

Пользовательские данные (БД сессий, аудио) лежат отдельно от проекта:
- macOS: `~/Library/Application Support/MeetingScribe/`
- Windows: `%APPDATA%\MeetingScribe\`

Копируйте отдельно, если нужна история.

## Альтернатива установке: запуск из клонированного репо

Без установщика, напрямую:
```bash
git clone https://github.com/onekil1/real-time-transcriber.git
cd real-time-transcriber
uv sync
uv run python run.py
```

Требования: `uv`, `ffmpeg`, Python 3.10–3.12. На Windows дополнительно CUDA Toolkit 12.1 для GPU-ветки (через `install.bat` проще).

Запуск без menu bar (для headless):
```bash
MEETING_SCRIBE_NO_MENUBAR=1 uv run python run.py
```

## Расширенный траблшутинг

**MLX Whisper грузит модель 15+ секунд на первом запуске** — нормально, модель весит 1.5 GB, кэшируется в `~/.cache/huggingface/hub/` или берётся из `models/whisper/mac/` (приоритет у локальной).

**faster-whisper: `CUDA failed: out of memory`** — уменьшите `MEETING_SCRIBE_ASR_COMPUTE` до `int8_float16` или `int8`. Либо используйте меньшую модель (`large-v3-turbo`, `medium`).

**Word-timestamps в логах показывают странные границы (все слова 0.0–0.0)** — в MLX Whisper это бывает на коротких артефактных сегментах. Fallback в `_dedup_overlap` использует `segment.end` — работает, просто менее точно.

**`uv sync` после апдейта ставит лишние пакеты или ломает окружение** — `rm -rf .venv && uv sync`. Полный ребилд.

**На macOS баннер обновления не появляется** — проверьте `curl http://127.0.0.1:8765/api/update/check` в терминале. Если `available: false` — вы на последней версии. Если ошибка сети — проверьте подключение к github.com.

**Нужен доступ к UI с другой машины в локалке** — `MEETING_SCRIBE_HOST=0.0.0.0 uv run python run.py`. **API не защищён** — не выставляйте наружу, только доверенная сеть.

**Системный звук (Zoom/Teams) на macOS** — поставьте [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole), создайте Multi-Output Device (`Audio MIDI Setup`) с BlackHole + вашими динамиками, выберите его как системный выход. В Транскрибаторе выбрать BlackHole как источник — пока только через системный выбор входа по умолчанию (UI-селектора устройства нет).

**Системный звук на Windows** — VB-Cable или Voicemeeter. Аналогично: делаете VB-Cable устройством по умолчанию, Транскрибатор пишет с него.

## Что не входит в коробку

- **Диаризация спикеров** (кто говорит). Планируется через pyannote.audio.
- **Захват системного звука** — нужны сторонние виртуальные аудиодрайверы.
- **GUI-упаковка** в `.app` / `.exe` / MSI — только скриптовая установка в venv.
- **Выбор аудио-устройства в UI** — используется системное устройство по умолчанию.
- **Онлайн-версия / облако** — намеренно: все данные остаются на машине.
