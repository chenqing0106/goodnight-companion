# Goodnight Agent

好梦鸟具身睡眠 Agent 后端。

项目当前已完成 M1 领域核心和 M2 Mock MQTT 闭环的首个可运行版本。目标不是一次实现全部产品功能，而是先验证一条可停止、可验证、可替换真实硬件的最小链路。

## V0 目标

第一条纵向链路：

```text
模拟用户已入睡
→ 识别 sleep_cleanup 场景
→ 创建行动
→ 检查权限与安全条件
→ 通过 MQTT 下发设备命令
→ 接收设备执行状态
→ 验证现实结果
→ 记录并输出最终状态
```

首个产品场景为 F1：用户睡着后，将手机移动到固定收纳位置，并在灯具可控时关灯。

## 架构原则

- 安全、权限和状态转换使用确定性代码。
- LLM 只参与意图理解、故事生成和角色表达。
- Agent 只调用有限的高层硬件能力，不生成机械臂轨迹。
- 发出命令不等于执行成功，最终状态必须经过设备反馈和结果验证。
- 所有物理动作必须可停止，硬件急停不依赖 Agent 或前端在线。
- Mock 与真实硬件使用相同的 `DeviceGateway` 接口。
- 领域模型独立于 LangGraph、通信协议和数据库实现。

## V0 技术选择

| 部分 | 选择 |
| --- | --- |
| 语言 | Python 3.12 |
| API | FastAPI + Pydantic |
| 编排 | `SimpleWorkflow` 显式状态机 |
| 内部异步事件 | `asyncio.Queue` |
| 硬件协议 | MQTT |
| 设备实现 | `InMemoryDeviceGateway`、`MqttDeviceGateway` |
| 前端命令 | HTTP |
| 状态推送 | SSE，封装为可替换 Publisher |
| 存储 | 内存 Repository，后续可替换 SQLite 或 PostgreSQL |
| 测试 | pytest |

当前不引入 LangGraph、CrewAI、MCP、向量数据库、多 Agent 和复杂长期记忆。满足明确升级条件后再替换相应边界。

## 模块边界

```text
API / Event Ingress
        ↓
World State ← Device Registry ← MQTT availability / capabilities
        ↓
Scene Evaluator
        ↓
Workflow Runtime
        ↓
Permission + Safety Policy
        ↓
Device Gateway
        ↓ MQTT
硬件与传感器
        ↓ status / result
Result Verifier
        ↓
Domain Event Publisher
```

## 当前目录

```text
src/goodnight_agent/
├── api/                  # HTTP、SSE 和调试入口
├── agent/                # 场景判断、策略、World State、工作流
├── devices/              # 内存设备与 MQTT Gateway
├── domain/               # 领域模型和行动状态机
└── infrastructure/       # 事件发布与 Repository 接口
scripts/
├── mock_mqtt_device.py   # 独立 MQTT 模拟硬件
└── run_scenario.py       # 可直接观察结果的场景脚本
tests/                    # 核心、设备、工作流和 API 测试
```

## 最快验证

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
cd /Users/qingchen/Code/goodnight-agent
uv sync
uv run pytest -q
uv run python scripts/run_scenario.py success
```

成功场景应看到两个动作均为 `succeeded`，最终 `phone_location` 为 `dock`，`light_on` 为 `false`。

继续验证异常分支：

```bash
uv run python scripts/run_scenario.py device-failure
uv run python scripts/run_scenario.py user-stop
uv run python scripts/run_scenario.py device-timeout
uv run python scripts/run_scenario.py duplicate-command
uv run python scripts/run_scenario.py safety-block
```

## 验证 HTTP 和界面接入方式

启动 API，默认使用内存设备，不依赖 MQTT：

```bash
uv run uvicorn goodnight_agent.api.app:app --reload
```

打开 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)，调用 `POST /api/debug/observations`，请求示例：

```json
{
  "source": "manual",
  "facts": {
    "person_in_bed": true,
    "person_motion": "still",
    "stable_for_seconds": 960,
    "phone_location": "operation_zone",
    "light_on": true,
    "sleep_window": true
  }
}
```

前端后续接入时只需要：

- `POST /api/debug/observations` 在开发阶段模拟感知输入。
- `GET /api/state` 获取当前现实状态。
- `GET /api/devices` 获取设备在线状态和已声明能力。
- `GET /api/actions` 或 `GET /api/actions/{id}` 查询动作。
- `POST /api/actions/{id}/stop` 停止正在执行的单个动作。
- `GET /api/events` 通过 SSE 接收状态变化。

## 验证真实 MQTT 通道

需要 Docker，共开三个终端：

```bash
# 终端 1：启动本地 Broker
docker compose up -d broker

# 终端 2：启动模拟硬件
uv run python scripts/mock_mqtt_device.py

# 终端 3：Agent 通过 MQTT 执行完整场景
uv run python scripts/run_scenario.py success --transport mqtt
```

结束后执行：

```bash
docker compose down
```

API 也可以切换为 MQTT 设备：

```bash
GOODNIGHT_DEVICE_TRANSPORT=mqtt uv run uvicorn goodnight_agent.api.app:app --reload
```

## MQTT 主链路

当前 Mock 契约使用以下 Topic：

```text
goodnight/{device_id}/availability
goodnight/{device_id}/capabilities
goodnight/{device_id}/telemetry
goodnight/{device_id}/command
goodnight/{device_id}/command/status
goodnight/{device_id}/event
```

所有设备命令必须携带稳定的 `command_id`。设备收到重复 `command_id` 时返回已有状态，不重复执行物理动作。命令 Topic 不保留旧消息。完整消息示例和行为规则见 [docs/mqtt-contract.md](./docs/mqtt-contract.md)。

当 API 使用 MQTT transport 时，`MqttDeviceGateway` 同时维护 `DeviceRegistry`。每次动作进入安全检查前，Registry 会用 retained `availability` 和 `capabilities` 覆盖调试 Observation 中可能存在的设备状态。设备离线、状态未知或未声明目标能力时，动作不会下发。

## 当前验证结果

- 自动化测试覆盖成功、失败、安全拦截、停止、超时和幂等。
- 内存设备完整场景已通过。
- Mosquitto + 独立模拟设备 + `MqttDeviceGateway` 的本地端到端场景已通过。
- DeviceRegistry 会把 MQTT 在线状态和能力同步到 World State 与 Safety Policy。
- 真实硬件协议、认证、心跳、急停和结果感知信号仍待硬件组确认。

## 暂未实现

- 真实摄像头或传感器感知。
- 真实硬件控制和硬件级急停。
- 数据持久化和进程重启恢复。
- 全局停止整个工作流，目前停止接口只针对单个 Action。
- LLM、LangGraph、多 Agent 和长期记忆。

详细阶段划分和联调前置条件见 [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md)。
