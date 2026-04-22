# Модели

## Whisper (ASR) → `models/whisper/`

Рекомендованная модель для русского: **`mlx-community/whisper-large-v3-turbo`** (~1.6 ГБ, точность ≈ large-v3, но в 2-3 раза быстрее).
Более лёгкий вариант: **`mlx-community/whisper-medium-mlx-fp16`** (~1.5 ГБ) или `mlx-community/whisper-small-mlx` (~480 МБ) — качество пониже.

### Вариант 1 — huggingface-cli (рекомендуется)
```bash
pip install -U huggingface_hub
huggingface-cli download mlx-community/whisper-large-v3-turbo \
    --local-dir models/whisper --local-dir-use-symlinks False
```

### Вариант 2 — git + git-lfs
```bash
brew install git-lfs && git lfs install
git clone https://huggingface.co/mlx-community/whisper-large-v3-turbo models/whisper
```

### Вариант 3 — вручную через браузер
Страница модели: <https://huggingface.co/mlx-community/whisper-large-v3-turbo/tree/main>
Скачайте **все** файлы из репозитория (включая `*.safetensors`, `config.json`, `tokenizer.json`) в `models/whisper/`.

### Проверка
После скачивания структура должна быть такой:
```
models/whisper/
├── config.json
├── tokenizer.json
├── weights.npz        (или *.safetensors)
└── ...
```

Код автоматически подхватит папку, если в ней есть `*.safetensors` или `weights.npz`.
Переопределить путь можно переменной `MEETING_SCRIBE_WHISPER=/абсолютный/путь`.

## LLM → через LM Studio

LLM работает через **LM Studio** (OpenAI-совместимый API на `http://127.0.0.1:1234`).
Скачайте любую подходящую модель в LM Studio (рекомендуется Qwen2.5-7B-Instruct или больше),
запустите «Local Server» → код сам её подхватит.
