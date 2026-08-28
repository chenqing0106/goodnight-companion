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
- 所有可调用能力先注册为 Tool，并通过参数 Schema 校验。
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
| 设备实现 | 内存设备、通用 Mock MQTT、ENV-S3 MQTT 适配器 |
| 工具层 | `ToolRegistry` + `ToolExecutor` |
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
Tool Registry + Tool Executor
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
├── tools/                # Tool 定义、注册、参数校验和执行
└── infrastructure/       # 事件发布与 Repository 接口
scripts/
├── mock_mqtt_device.py   # 独立 MQTT 模拟硬件
├── mock_env_s3_device.py # 按真实固件协议运行的 ENV-S3 模拟器
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
- `GET /api/tools` 查看 Agent 允许调用的工具及其参数 Schema。
- `GET /api/actions` 或 `GET /api/actions/{id}` 查询动作。
- `POST /api/actions/{id}/stop` 停止正在执行的单个动作。
- `POST /api/runs/{id}/stop` 停止整个流程，并跳过尚未执行的后续动作。
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

这套 Topic 只用于已经跑通的机械臂 Mock，不代表 ENV-S3 固件协议。真实环境感知硬件使用独立的 `EnvS3MqttGateway`，避免两套协议互相污染。

## ENV-S3 硬件联调

ENV-S3 通道订阅设备在线状态、五类传感器和两个执行器回执：

```text
{device_id}/status
{device_id}/sensor/#
{device_id}/actuator/+/state
```

后端只向 `actuator/rgb/set` 和 `actuator/led/set` 发布单字符命令，并等待相应的 `state` 回执。由于当前固件回执没有 `command_id`，后端会把同一执行器的命令串行处理，避免回执对应错误。

先用本地 Broker 验证适配器：

```bash
# 终端 1
docker compose up -d broker

# 终端 2
uv run python scripts/mock_env_s3_device.py

# 终端 3
GOODNIGHT_DEVICE_TRANSPORT=env_s3_mqtt \
GOODNIGHT_MQTT_HOST=127.0.0.1 \
GOODNIGHT_MQTT_PORT=1883 \
uv run uvicorn goodnight_agent.api.app:app --reload
```

打开 `/docs` 后可用 `GET /api/devices` 查看在线状态，用 `GET /api/devices/env-s3-01/sensors` 查看最新传感器读数。`GET /api/tools` 会显示 `set_rgb_indicator` 和 `set_led_mode` 的参数范围。

也可以直接检查完整 MQTT 通道。下面的命令会读取状态和传感器，并把本地模拟灯带切到模式 3：

```bash
uv run python scripts/check_env_s3_connection.py --led-mode 3
```

连接硬件组公网 Broker 时，只需把 transport 改为 `env_s3_mqtt`，并通过部署环境注入主机、端口、设备 ID、用户名和密码。认证信息不能提交到 Git。

## Tool 主链路

场景规则或未来的 LLM 只能提出 ToolCall，不能直接创建 MQTT 命令：

```text
SceneEvaluator / LLM
→ ToolCall
→ ToolRegistry 名称与参数校验
→ Permission + Safety Policy
→ ToolExecutor
→ DeviceGateway
→ MQTT
```

当前还注册了 ENV-S3 的 `set_rgb_indicator` 和 `set_led_mode`。完整边界与扩展方式见 [docs/tool-layer.md](./docs/tool-layer.md)。当前不使用 MCP；当工具需要跨进程或供多个 Agent 发现时再增加 MCP Adapter。

当 API 使用 MQTT transport 时，`MqttDeviceGateway` 同时维护 `DeviceRegistry`。每次动作进入安全检查前，Registry 会用 retained `availability` 和 `capabilities` 覆盖调试 Observation 中可能存在的设备状态。设备离线、状态未知或未声明目标能力时，动作不会下发。

## 当前验证结果

- 自动化测试覆盖成功、失败、安全拦截、Action 停止、Run 停止、超时和幂等。
- 内存设备完整场景已通过。
- Mosquitto + 独立模拟设备 + `MqttDeviceGateway` 的本地端到端场景已通过。
- DeviceRegistry 会把 MQTT 在线状态和能力同步到 World State 与 Safety Policy。
- ToolRegistry 会拒绝未注册工具、非法枚举参数和多余参数。
- ENV-S3 的 Topic、认证配置入口、在线状态、传感器解析和灯光回执已适配；公网账号仍需由项目负责人单独提供后再实机联调。

## 暂未实现

- 将 ENV-S3 原始传感器读数转换为睡眠场景判断。
- 机械臂真实硬件控制和硬件级急停。
- 数据持久化和进程重启恢复。
- LLM、LangGraph、多 Agent 和长期记忆。

详细阶段划分和联调前置条件见 [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md)。
