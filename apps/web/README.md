# Goodnight Web

好梦鸟的 Next.js 正式前端。当前阶段只验证场景 1：用户稳定入睡后，Agent
检查安全条件并通过工具层让设备收起手机、关闭床头灯。

## 本地运行

先启动 FastAPI 后端：

```bash
cd /Users/qingchen/Code/goodnight-agent
uv run uvicorn goodnight_agent.api.app:app --reload
```

再启动前端：

```bash
cd /Users/qingchen/Code/goodnight-companion/apps/web
pnpm dev
```

打开 <http://127.0.0.1:3000>。普通 HTTP 请求通过 Next.js rewrite 把同源的
`/api/*` 转发到 FastAPI；SSE 通过 `/agent-events` 流式转发，因此浏览器不需要
直接跨域访问后端。

如需修改后端地址，复制 `.env.example` 为 `.env.local` 并调整
`AGENT_BACKEND_URL`。

## 接口契约

后端运行后，可重新生成 TypeScript 类型：

```bash
pnpm api:types
```

生成文件位于 `src/features/agent/api/schema.d.ts`，不要手动修改。

## 检查

```bash
pnpm lint
pnpm typecheck
pnpm build
```

## 目录边界

- `api`：FastAPI 请求、SSE 和自动生成类型。
- `model`：后端状态到界面状态的集中映射。
- `hooks`：页面使用的 Agent 运行时入口。
- `components`：当前最小联调页面，后续替换为正式 UI。

旧版 UI 原型仍在仓库根目录，这个阶段不要在原型里重复实现接口逻辑。

## 停止语义

“立即停止”调用 run 级取消接口。后端会停止当前设备动作，并把同一 run 中尚未
执行的后续 action 标记为 `skipped`，不会继续执行关灯等后续动作。重复停止请求
不会再次向设备下发停止命令。
