# Goodnight Agent Tool 层

Tool 层把“Agent 想做什么”和“设备协议如何执行”隔开。场景规则或未来的 LLM 只能选择已注册工具并提供参数，不能直接构造 MQTT Topic、设备命令或机械臂轨迹。

## 调用链

```text
Decision / ActionRequest
        ↓
ToolRegistry
名称存在 + 参数 Schema 校验
        ↓
PermissionPolicy + SafetyPolicy
        ↓
ToolCall
        ↓
ToolExecutor
        ↓
DeviceCommand
        ↓
DeviceGateway → MQTT
```

工作流仍然拥有 Action 状态机、权限、安全和结果验证。ToolExecutor 只负责把通过检查的 ToolCall 转换成设备命令，不具有绕过 Policy 的入口。

## 当前工具

| Tool | 风险 | 参数 | 说明 |
| --- | --- | --- | --- |
| `move_phone_to_dock` | `physical_low` | `speed_profile` | 将手机移动到固定收纳位置 |
| `turn_off_light` | `physical_low` | 无 | 关闭已确认可控的灯光 |
| `stop_all_motion` | `safety_control` | `target_command_id` | 停止目标设备命令 |

可以通过 `GET /api/tools` 获取机器可读的 JSON Schema。

## ToolCall 示例

```json
{
  "tool_call_id": "cmd_01",
  "action_id": "act_01",
  "tool_name": "move_phone_to_dock",
  "device_id": "mock-arm",
  "arguments": {
    "speed_profile": "night_slow"
  }
}
```

`device_id` 由受信任的场景或后端上下文绑定，不应由 LLM 自由选择。`tool_call_id` 同时作为下游稳定 `command_id`，保证 MQTT 重复投递不会重复执行物理动作。

## 增加新工具

1. 为参数创建 Pydantic Model，并设置 `extra="forbid"`。
2. 在 `build_default_tool_registry()` 中注册名称、描述和风险等级。
3. 在 PermissionPolicy 中明确 automatic、ask 或 forbidden。
4. 在 SafetyPolicy 中增加对应现实安全条件。
5. 在 DeviceGateway 和真实硬件中实现同名高层 capability。
6. 在 ResultVerifier 中增加独立结果验证规则。
7. 增加正常、非法参数、安全失败、停止和验证失败测试。

不能只注册 Tool 就直接获得物理执行权限。Registry、Permission、Safety、设备能力声明和 ResultVerifier 必须同时认可该能力。

## 与 MCP 的关系

当前 ToolRegistry 与 Agent 运行在同一进程，结构简单且容易测试。MCP 未来只作为 ToolRegistry 外部的适配器，用于跨进程发现和调用工具，不替代领域模型、安全策略或 DeviceGateway。
