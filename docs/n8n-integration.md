# SaveTube — интеграция с n8n

Базовый URL: `http://savetube:6060` (внутри Docker-сети)

---

## Эндпоинты

### POST /api/jobs — запустить скачивание

```
POST /api/jobs
Content-Type: application/json

{
  "url": "https://www.youtube.com/watch?v=...",
  "quality": 1080,
  "callback_url": "https://n8n.example.com/webhook/abc"  // опционально
}
```

Ответ `201`:
```json
{
  "id": "job_a1b2c3d4e5f6",
  "status": "pending",
  "progress": 0,
  "file_url": null,
  "filename": null,
  "filesize": null,
  "error": null
}
```

Поля: `quality` — высота в пикселях (480 / 720 / 1080). По умолчанию 1080.

---

### GET /api/jobs/{id} — статус задачи

```
GET /api/jobs/job_a1b2c3d4e5f6
```

Ответ `200`:
```json
{
  "id": "job_a1b2c3d4e5f6",
  "status": "done",
  "progress": 100,
  "file_url": "/files/dQw4w9WgXcQ_1080p.mp4",
  "filename": "dQw4w9WgXcQ_1080p.mp4",
  "filesize": 47185920,
  "error": null
}
```

Статусы: `pending` → `processing` → `done` / `failed`

---

### GET /api/jobs/{id}/download — скачать файл

```
GET /api/jobs/job_a1b2c3d4e5f6/download
```

Редирект `302` на `/files/{filename}` когда `status == "done"`.  
Возвращает `400` если ещё не готово, `404` если job не найден.

---

## Вариант 1: polling (без callback)

Сборка из 4 нод в n8n:

### Нода 1 — HTTP Request (создать job)
- Method: `POST`
- URL: `http://savetube:6060/api/jobs`
- Body (JSON):
  ```json
  {
    "url": "{{ $json.video_url }}",
    "quality": 1080
  }
  ```
- Сохраняет `id` из ответа

### Нода 2 — Wait
- Подождать 15 секунд (среднее время скачивания)

### Нода 3 — HTTP Request (проверить статус)
- Method: `GET`
- URL: `http://savetube:6060/api/jobs/{{ $json.id }}`

### Нода 4 — IF (проверить готовность)
- Условие: `{{ $json.status }} === "done"`
- True → следующий шаг (скачать файл)
- False + `status === "failed"` → ветка ошибки
- False иначе → вернуться к Ноде 2 (Loop)

### Нода 5 — HTTP Request (получить файл)
- Method: `GET`
- URL: `http://savetube:6060/api/jobs/{{ $json.id }}/download`
- Response Format: `File`

---

## Вариант 2: callback (рекомендую)

Передай `callback_url` при создании job — SaveTube сам пошлёт POST на твой webhook когда готово.

### Нода 1 — HTTP Request (создать job)
```json
{
  "url": "{{ $json.video_url }}",
  "quality": 1080,
  "callback_url": "https://n8n.example.com/webhook/savetube-done"
}
```

### Webhook нода (ждёт колбэк)
Получает:
```json
{ "id": "job_abc", "status": "done", "file_url": "/files/video.mp4" }
```
или
```json
{ "id": "job_abc", "status": "failed", "error": "Видео недоступно." }
```

### Нода скачивания
- URL: `http://savetube:6060/api/jobs/{{ $json.id }}/download`
- Response Format: `File`

---

## Коды ошибок

| Код | Причина |
|-----|---------|
| 400 | Неподдерживаемая ссылка или job ещё не готов |
| 404 | Job не найден |
| 429 | Очередь переполнена (retry через ~30 сек) |
| 500 | Внутренняя ошибка скачивания |
