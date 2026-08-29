# Goodnight Agent MQTT Mock 契约

> 本文只描述机械臂 Mock 使用的通用协议，不是 ENV-SENSING-S3 固件协议。ENV-S3 由独立适配器接入，两套 Topic 不兼容。

这份契约用于当前 Agent、独立模拟设备和后续真实硬件并行开发。它是可运行的 V0 草案，不代表认证、设备证书、真实传感器和硬件急停方案已经确认。

## Topic

| Topic | 方向 | QoS | Retain | 说明 |
| --- | --- | --- | --- | --- |
| `goodnight/{device_id}/availability` | 设备 → Agent | 1 | 是 | `online`、`offline`，并作为遗嘱消息 |
| `goodnight/{device_id}/capabilities` | 设备 → Agent | 1 | 是 | 当前高层能力列表 |
| `goodnight/{device_id}/command` | Agent → 设备 | 1 | 否 | 动作命令，禁止保留旧命令 |
| `goodnight/{device_id}/command/status` | 设备 → Agent | 1 | 否 | 命令生命周期和最终结果 |

预留但当前代码未使用：`telemetry` 和 `event`。

## DeviceCommand

```json
{
  "command_id": "cmd_01",
  "action_id": "act_01",
  "device_id": "mock-arm",
  "capability": "move_phone_to_dock",
  "parameters": {"speed_profile": "night_slow"},
  "timeout_ms": 30000
}
```

`command_id` 由 Agent 生成，在一次动作的重试或重复投递中保持不变。设备必须缓存最终结果，收到相同 ID 时返回已有结果，不得重复执行物理动作。

## DeviceStatus

```json
{
  "command_id": "cmd_01",
  "device_id": "mock-arm",
  "status": "executing",
  "progress": 0.5,
  "result": {},
  "error_code": null,
  "message": null,
  "timestamp": "2026-08-28T17:00:00+08:00"
}
```

状态顺序：

```text
accepted → executing → succeeded
                     ↘ failed
                     ↘ stopped
```

`succeeded` 只表示设备完成了命令。Agent 仍要根据 `result.facts` 或独立感知信号验证现实结果，验证失败时 Action 进入 `failed`。

成功结果示例：

```json
{
  "command_id": "cmd_01",
  "device_id": "mock-arm",
  "status": "succeeded",
  "progress": 1,
  "result": {"facts": {"phone_location": "dock"}},
  "error_code": null,
  "message": null,
  "timestamp": "2026-08-28T17:00:03+08:00"
}
```

## 停止动作

Agent 向同一设备发布高层停止命令：

```json
{
  "command_id": "cmd_stop_01",
  "action_id": "act_01",
  "device_id": "mock-arm",
  "capability": "stop_all_motion",
  "parameters": {"target_command_id": "cmd_01"},
  "timeout_ms": 5000
}
```

设备应先停止目标动作，再把目标命令状态报告为 `stopped`。软件停止不能代替物理急停，真实硬件必须提供不依赖 Agent、前端和 Broker 的本地急停链路。

## Availability 与 Capabilities

```json
{"status": "online"}
```

```json
{
  "capabilities": [
    "move_phone_to_dock",
    "turn_off_light",
    "stop_all_motion"
  ]
}
```

设备连接后发布 retained `online`，异常断线由 Broker 发布 retained `offline` 遗嘱。Agent 不得向已知离线设备开始新动作。

## 联调前必须继续确认

- Broker 部署位置、TLS、账号或设备证书。
- `device_id` 的生成和绑定规则。
- 心跳频率、离线判定和重连后的状态恢复。
- 每个能力的参数类型、单位、边界和稳定错误码。
- 真实设备的停止确认、复位流程和物理急停反馈。
- `ResultVerifier` 可读取的真实感知信号。
