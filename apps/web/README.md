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

## 当前限制

后端的停止接口目前只停止一个 action，同一 run 中尚未开始的后续 action
仍会继续。联调页因此使用“停止当前动作”的准确文案；正式 UI 使用“立即停止”前，
后端需要补充 run 级取消和 `stop_all_motion` 语义。
