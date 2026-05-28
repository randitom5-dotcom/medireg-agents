# MediReg Agents Frontend

React + Vite + Tailwind CSS + Ant Design frontend for the MediReg Agents FastAPI backend.

前端用于医疗器械注册知识库问答场景，支持任务提交、文件上传、WebSocket 事件流展示、回答查看和生成文件下载。

## Run

```bash
pnpm install
pnpm dev
```

By default the app talks to `http://localhost:8000` and `ws://localhost:8000`.
Override with `.env.local`:

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

## Backend Contract

- `POST /api/task`
- `POST /api/upload`
- `GET /api/files`
- `GET /api/download`
- `WebSocket /ws/{thread_id}`

The backend also exposes `/api/v1` integration endpoints for outsourced frontend or external systems:

- `POST /api/v1/tasks/qa`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`
- `POST /api/v1/documents/upload`
- `GET /api/v1/datasets`
