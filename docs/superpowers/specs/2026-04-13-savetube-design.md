# SaveTube — Design Spec

Slack-бот для скачивания видео из YouTube и TikTok в канале creo-tools.

## Контекст и проблема

Команде нужен инструмент для скачивания видео прямо из Slack. Сторонние сервисы работают нестабильно. Предыдущая попытка (MeTube / yt-dlp) провалилась из-за cookie-проблемы YouTube: куки истекали каждые 2-4 часа.

### Результаты research

- **OAuth2 для YouTube в yt-dlp мёртв.** Google убил YouTube TV OAuth client ID в ноябре 2024. Код удалён из yt-dlp.
- **PO Token (Proof of Origin)** — текущее решение. YouTube требует PO-токены, yt-dlp не может генерировать их сам, но плагин **bgutil-ytdlp-pot-provider** делает это автоматически через BotGuard.
- **Куки нужны только для age-restricted / private / members-only контента.** Для публичных видео достаточно PO Token.
- **TikTok** — yt-dlp работает из коробки, антибот минимален.
- **Cobalt.tools отключил YouTube** в mid-2025. Invidious/Piped ненадёжны. Альтернатив лучше yt-dlp нет.
- **YouTube Premium** — снижает трение, но не критичен для публичного контента.

Источники:
- [yt-dlp Extractors wiki](https://github.com/yt-dlp/yt-dlp/wiki/Extractors) (обновлено Jun 2025)
- [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
- [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)

## Стек

| Компонент | Технология |
|-----------|-----------|
| Slack-бот | Python + Slack Bolt SDK (Socket Mode) |
| Скачивание YouTube | yt-dlp + bgutil-ytdlp-pot-provider |
| Скачивание TikTok | yt-dlp (из коробки) |
| Очередь задач | asyncio (встроенная) |
| Деплой | Docker Compose, один контейнер, VPS |

## Архитектура

```
Slack (creo-tools workspace)
    │
    ▼
┌──────────────────────────┐
│  Slack Bolt App (Python)  │  ← Socket Mode, не нужен публичный URL
│                           │
│  ┌──────────────────────┐ │
│  │  Task Queue (asyncio)│ │
│  │                      │ │
│  │  Worker 1 → yt-dlp + PO Token → YouTube  │
│  │  Worker 2 → yt-dlp           → TikTok   │
│  │  Worker 3 → ...              │ │
│  └──────────────────────┘ │
│                           │
│  /tmp/downloads/          │  ← временное хранилище
│  File cache (1 час TTL)   │
│  Static file server       │  ← fallback если Slack upload не работает
└──────────────────────────┘
```

## Пользовательский флоу

### Основной сценарий

1. Пользователь кидает ссылку (YouTube или TikTok) в канал creo-tools
2. Бот распознаёт URL, запрашивает метаданные через yt-dlp (без скачивания, ~1-2 сек)
3. Бот отвечает в тред: название видео, длительность, кнопки выбора качества с размерами файлов
4. Пользователь нажимает кнопку (например "1080p · 45 MB")
5. Бот обновляет сообщение: "Скачиваю..."
6. Воркер скачивает видео через yt-dlp
7. Бот загружает файл в Slack в тот же тред
8. Файл удаляется с диска (или остаётся в кэше на 1 час)

### Несколько ссылок

Несколько ссылок в одном сообщении — каждая обрабатывается отдельно, каждая в своём треде.

### Пример взаимодействия

```
Пользователь: https://www.youtube.com/watch?v=dQw4w9WgXcQ

Бот (в треде):
🎬 Rick Astley — Never Gonna Give You Up · 3:32

[480p · 9 MB]  [720p · 18 MB]  [1080p · 45 MB]
    ← интерактивные кнопки (Slack Block Kit)

Пользователь нажимает [1080p · 45 MB]

Бот (обновляет сообщение):
⏳ Скачиваю 1080p...

Бот (когда готово):
✅ Готово
[video.mp4 — 45.2 MB]
```

## Распознаваемые URL

| Платформа | Паттерны |
|-----------|----------|
| YouTube | `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/` |
| TikTok | `tiktok.com/`, `vm.tiktok.com/` |

Неизвестные ссылки — бот молчит (не спамит).

## Качество видео

- По умолчанию: лучшее доступное до 1080p
- Пользователь выбирает через кнопки (Block Kit)
- Бот показывает только реально доступные качества для конкретного видео

## Ограничения

| Параметр | Значение | Настраивается |
|----------|----------|---------------|
| Максимум параллельных скачиваний | 3 | Да (env) |
| Максимальная длина видео | 60 минут | Да (env) |
| Размер очереди | 10 | Да (env) |
| Пауза между скачиваниями (YouTube rate limit) | 5-10 сек | Да (env) |
| Качество по умолчанию | 1080p | Да (env) |
| TTL кэша файлов | 1 час | Да (env) |
| TTL временных HTTP-ссылок | 1 час | Да (env) |

## Slack-интеграция

### Подключение: Socket Mode

- Бот подключается к Slack через WebSocket
- Не нужен публичный URL, HTTPS, nginx
- Требуется: `SLACK_BOT_TOKEN` (xoxb-) и `SLACK_APP_TOKEN` (xapp-)

### Загрузка файлов

- Основной путь: `files.upload_v2` Slack API
- Если Slack отказал (план не поддерживает / файл слишком большой): бот отдаёт временную HTTP-ссылку на файл (статический файл-сервер внутри контейнера, TTL 1 час)
- Определяем возможности по факту (пробуем upload, ловим ошибку)

### Необходимые Slack App permissions

- `chat:write` — отправка сообщений
- `files:write` — загрузка файлов
- `links:read` — чтение ссылок в сообщениях
- `app_mentions:read` или подписка на `message` events в канале

## Обработка ошибок

| Ситуация | Реакция бота | Действие |
|----------|-------------|----------|
| Видео удалено / приватное | "Видео недоступно" в тред | — |
| Таймаут скачивания (>5 мин) | "Не удалось скачать" в тред | Чистит tmp |
| PO Token не сгенерировался | Retry 1 раз через 10 сек, потом ошибка | Лог |
| yt-dlp упал / YouTube обновился | "Загрузчик сломался" | Алерт в канал |
| Slack отказал upload | Временная HTTP-ссылка | — |
| Диск заполнен | Ошибка пользователю | Алерт в канал |
| Очередь заполнена (>10) | "Очередь заполнена, попробуйте позже" | — |
| Видео длиннее лимита | "Видео слишком длинное (макс. 60 мин)" | — |

## Кэширование

- Ключ кэша: URL + выбранное качество
- TTL: 1 час
- При повторном запросе того же видео — отдаёт из кэша без повторного скачивания

## Деплой

### Docker Compose

```yaml
services:
  savetube:
    build: .
    environment:
      - SLACK_BOT_TOKEN=xoxb-...
      - SLACK_APP_TOKEN=xapp-...
      - DOWNLOAD_DIR=/tmp/downloads
      - MAX_CONCURRENT_DOWNLOADS=3
      - MAX_VIDEO_DURATION=3600
      - MAX_QUEUE_SIZE=10
      - DEFAULT_QUALITY=1080
      - FILE_TTL_MINUTES=60
      - DOWNLOAD_DELAY_SECONDS=7
    volumes:
      - downloads:/tmp/downloads
    restart: unless-stopped

volumes:
  downloads:
```

### Dockerfile (концептуально)

```dockerfile
FROM python:3.12-slim
RUN pip install slack-bolt yt-dlp bgutil-ytdlp-pot-provider
COPY . /app
WORKDIR /app
CMD ["python", "main.py"]
```

### Обновление yt-dlp

- Cron раз в неделю: пересборка Docker-образа
- Или ручное обновление при поломке (алерт в канал подскажет)

## Мониторинг

- Бот логирует: что скачал, время, размер, ошибки
- При критической ошибке (PO Token не работает, yt-dlp сломан) — алерт в канал creo-tools
- Простой healthcheck: если бот не отвечает на ping в Slack > 5 минут — контейнер рестартится

## Осознанно за scope

- Веб-UI — не нужен, всё через Slack
- OAuth2 YouTube — мёртв
- Куки YouTube — не нужны для публичного контента
- Другие платформы (Instagram, X) — можно добавить позже, архитектура позволяет
- YouTube Premium аккаунт — не критичен, можно добавить позже
- Аудио-скачивание (mp3) — за scope, но тривиально добавить
