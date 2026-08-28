# Goodnight Companion

好梦鸟前端仓库。目前同时保留两部分：

- 根目录的 React CDN 页面是 UI 原型，供界面与交互细节继续调整。
- `apps/web` 是 Next.js 正式前端，负责类型安全的后端接入和后续页面迁移。

两部分暂时并行，等正式 UI 融合完成后再移除旧原型。

## 当前开发

```bash
cd apps/web
pnpm dev
```

浏览器打开 <http://127.0.0.1:3000>。默认连接运行在
`http://127.0.0.1:8000` 的 Goodnight Agent 后端。

更完整的联调说明见 [`apps/web/README.md`](apps/web/README.md)。
