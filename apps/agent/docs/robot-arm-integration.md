# 机械臂（Panthera / ASUS）接入与联调

后端通过 HTTP 调用 ASUS 上的机械臂场景服务（见《机械臂 Agent HTTP 调用契约》）。
客户端不发送关节角度、夹爪参数或 sleep 姿态，只触发场景；回落由 ASUS 侧完成。

## 1. 启用

在 `.env.hardware`（或任意 env 文件）中设置：

```bash
GOODNIGHT_ARM_BASE_URL=http://100.67.212.112:8000
```

不设置该变量时机械臂网关完全不启用，现有行为不变。可选配置：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `GOODNIGHT_ARM_BASE_URL` | 无（关闭） | ASUS 场景服务地址（Tailscale） |
| `GOODNIGHT_ARM_POLL_INTERVAL` | `1.0` | 轮询 `/api/status` 的间隔秒数 |
| `GOODNIGHT_ARM_REQUEST_TIMEOUT` | `5.0` | 单次 HTTP 请求超时秒数 |
| `GOODNIGHT_COMMAND_TIMEOUT_MS` | 启用机械臂时 `120000`，否则 `30000` | 单次动作最长等待时间 |

## 2. 五个动作

| 后端能力名 | ASUS 场景 | 类型 | 说明 |
| --- | --- | --- | --- |
| `arm_take_phone` | `take_phone02` | 一次性 | 拿手机，完成后自动回落 sleep2 |
| `arm_shake_toy` | `shake_toy02` | 一次性 | 摇玩具，完成后自动回落 sleep2 |
| `arm_pull_blanket` | `blanket01` | 一次性 | 盖被子，完成后自动回落 sleep2 |
| `arm_insert_item` | `insert02` | 一次性 | 收纳物品，完成后自动回落 sleep2 |
| `arm_storytelling` | `plant2` | 持续 | 讲故事摆动，**必须显式停止** |

同一时间只允许一个动作；重复触发返回 409。

## 3. 触发方式

后台页面 <http://localhost:3000/admin> 的「机械臂动作」面板选择动作并触发，
或直接调接口：

```bash
# 触发（202 立即返回，动作在后台经 workflow 执行）
curl -X POST http://127.0.0.1:8000/api/arm/actions \
  -H 'Content-Type: application/json' \
  -d '{"capability":"arm_shake_toy"}'
# => {"run_id":"run-...","capability":"arm_shake_toy","device_id":"panthera-arm","status":"accepted"}

# 跟踪进度
curl http://127.0.0.1:8000/api/actions
curl -N http://127.0.0.1:8000/api/events   # action.accepted / executing / succeeded

# 停止（讲故事必须手动停止；一次性动作也可中途停止，机械臂自动回落）
curl -X POST http://127.0.0.1:8000/api/runs/<run_id>/stop
```

## 4. 错误码速查

| error_code | 含义 | 先做什么 |
| --- | --- | --- |
| `ARM_UNREACHABLE` | 连不上 ASUS 服务 | 确认 Tailscale 在线，`curl $GOODNIGHT_ARM_BASE_URL/api/health` |
| `SCENE_NOT_DEPLOYED` | 轨迹未部署（上游 404） | 检查 ASUS 上 `records/trajectories/<scene>.jsonl` |
| `ARM_BUSY` | 机械臂被占用（上游 409） | 等当前动作结束或先停止 |
| `ARM_SERVICE_ERROR` | 上游 5xx | 查看 ASUS 侧服务日志 |
| `ARM_TIMEOUT` | 超过命令超时仍未完成 | 调大 `GOODNIGHT_COMMAND_TIMEOUT_MS` |
| `ARM_SCENE_FAILED` | 上游回放失败 | 查看 ASUS 侧服务日志 |
| `ARM_STATUS_UNKNOWN` | 连续多次读不到状态 | 检查网络与服务存活 |

## 5. 实现位置

- `src/goodnight_agent/devices/robot_arm.py` — `RobotArmHttpGateway`，实现 `DeviceGateway` 协议
- `src/goodnight_agent/api/app.py` — env 装配、路由覆盖、`POST /api/arm/actions`
- `src/goodnight_agent/tools/registry.py` — 五个 `arm_*` 工具注册
- `src/goodnight_agent/agent/policies.py` — 权限放行（默认 FORBIDDEN）
- `src/goodnight_agent/agent/verifier.py` — 按回执 `arm_scene` 验证结果
- `tests/test_robot_arm.py` — 网关单元测试 + 端点集成测试（MockTransport，无需硬件）

验证：`uv run pytest -q && uv run ruff check .`
