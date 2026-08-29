# Goodnight Companion

好梦鸟仓库，包含正式前后端：

- `apps/web` 是 Next.js 正式前端，负责类型安全的后端接入和页面呈现。
- `apps/agent` 是 Goodnight Agent 后端（FastAPI），由独立仓库合并而来。

## 当前开发

```bash
cd apps/web
pnpm dev
```

浏览器打开 <http://127.0.0.1:3000>。默认连接运行在
`http://127.0.0.1:8000` 的 Goodnight Agent 后端。

更完整的联调说明见 [`apps/web/README.md`](apps/web/README.md)。
