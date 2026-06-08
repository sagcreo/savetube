# SaveTube Job API — Design Spec

## Контекст

SaveTube уже имеет Web UI и SSE-эндпоинт для скачивания. Задача — добавить job-based API поверх существующего кода, чтобы n8n мог вызывать SaveTube без SSE/стриминга.

Существующие эндпоинты (`/api/info`, `/api/download`, `/files/`) не трогаем.

## Новые эндпоинты

```
POST /api/jobs
  Body: { "url": "https://...", "quality": 1080, "callback_url": "https://..." }
  → 201  { "id": "job_abc123", "status": "pending" }
  → 400  { "error": "..." }  — неподдерживаемая ссылка или невалидный запрос
  → 429  { "error": "..." }  — семафор заполнен

GET /api/jobs/{job_id}
  → 200  {
           "id": "job_abc123",
           "status": "pending" | "processing" | "done" | "failed",
           "progress": 45,
           "file_url": "/files/video.mp4",
           "filename": "video.mp4",
           "filesize": 12345678,
           "error": null
         }
  → 404  { "error": "Job not found" }

GET /api/jobs/{job_id}/download
  → 302  редирект на /files/{filename}  (когда status == "done")
  → 400  { "error": "Job not completed yet" }
  → 404  { "error": "Job not found" }
```

## Архитектура

### job_store.py

Новый модуль `src/job_store.py`:

- In-memory dict: `{ job_id: JobRecord }`
- `asyncio.Lock` для безопасного доступа из нескольких корутин
- `JobRecord` — датакласс: `id, status, progress, file_url, filename, filesize, error, created_at`
- ID генерируется как `job_` + `uuid4().hex[:12]`
- Автоочистка: jobs старше 2 часов удаляются фоновой задачей (вместе с файлами через существующий `FileCache`)

### Изменения в main.py

Добавить в `create_app()`:
- `handle_create_job` — POST /api/jobs
- `handle_get_job` — GET /api/jobs/{job_id}
- `handle_download_job` — GET /api/jobs/{job_id}/download

Фоновое скачивание запускается через `asyncio.create_task` (паттерн уже используется в `handle_download`). Семафор переиспользуется.

### callback_url

Если в запросе указан `callback_url`, после завершения job (статус `done` или `failed`) SaveTube делает POST:

```json
{ "id": "job_abc123", "status": "done", "file_url": "/files/video.mp4" }
```

Callback fire-and-forget через `aiohttp.ClientSession` (уже в зависимостях).

## Флоу в n8n

**Вариант 1 — polling:**
```
POST /api/jobs → job_id
    ↓ (loop пока status не "done"/"failed")
GET /api/jobs/{job_id}
    ↓
GET /api/jobs/{job_id}/download → файл
```

**Вариант 2 — callback:**
```
POST /api/jobs  { callback_url: "https://n8n.../webhook/abc" }
    ↓
(SaveTube сам делает POST на webhook когда готово)
```

## Что не меняется

- `GET /` — Web UI
- `POST /api/info` — метаданные видео
- `POST /api/download` — SSE стриминг для Web UI
- `GET /files/` — отдача файлов
- Логика скачивания (`Downloader`)
- Кэш файлов (`FileCache`)

## Статусы job

| Статус | Когда |
|--------|-------|
| `pending` | Job создан, ещё не взят в работу |
| `processing` | Скачивание запущено |
| `done` | Файл готов, `file_url` заполнен |
| `failed` | Ошибка, `error` заполнен |
