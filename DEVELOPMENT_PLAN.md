# Goodnight Agent 开发计划

## 1. 当前目标

先完成 F1 的 Mock MQTT 最小闭环，再接真实硬件。前端、完整感知算法、LLM 故事能力和其他产品场景暂不阻塞第一阶段。

第一阶段完成的判断标准：

```text
Observation
→ Decision
→ Action
→ DeviceCommand
→ MQTT Status
→ Verification
→ DomainEvent
```

链路中的每一步都能通过 `run_id`、`action_id` 和 `command_id` 关联和排查。

当前进度：M1 和 M2 的首个可运行版本已完成，并通过内存设备自动化测试与本地 Mosquitto 端到端联调。M0 中涉及真实硬件的参数仍需和硬件组确认，因此当前 MQTT 契约是可执行草案，不是生产协议终稿。

## 2. 开发边界

### 本阶段包含

- 核心领域模型。
- World State。
- F1 场景规则。
- Permission 与 Safety Policy 最小实现。
- 行动状态机。
- Mock MQTT 设备。
- `MqttDeviceGateway`。
- 设备命令幂等、超时和停止。
- 领域事件记录。
- 最小 HTTP 调试接口。
- 自动化测试。

### 本阶段不包含

- 正式前端适配。
- 完整睡眠识别算法。
- LangGraph 或 CrewAI。
- 多 Agent。
- MCP 工具服务。
- 向量数据库。
- 多模型动态路由。
- F2、F4、F5 的真实动作。
- 生产级多实例部署。

## 3. M0：冻结最小契约

目标：让 Agent、设备模拟器和真实硬件可以根据同一契约独立开发。

### MQTT

- [ ] 确认 Broker 地址、端口和部署位置。
- [ ] 确认是否使用 TLS、用户名密码或设备证书。
- [ ] 确认 `device_id` 规则。
- [ ] 确认 Topic 命名。
- [ ] 确认各 Topic 的 QoS。
- [ ] 确认 availability 心跳和遗嘱消息。
- [ ] 确认设备重连后的状态恢复方式。
- [ ] 确认命令 Topic 不使用 retained message。

### 设备能力

- [ ] 确认第一个可用能力名称。
- [ ] 确认输入参数、类型和单位。
- [ ] 确认 accepted、executing、succeeded、failed、stopped 格式。
- [ ] 确认错误码和是否允许重试。
- [ ] 确认停止与复位方式。
- [ ] 确认动作超时和硬件安全条件。

### 领域模型

- [x] 定义 `Observation`。
- [x] 定义 `Decision`。
- [x] 定义 `Action`。
- [x] 定义 `DeviceCommand`。
- [x] 定义 `DeviceStatus`。
- [x] 定义 `DomainEvent`。

### M0 完成标准

- Agent 和硬件组认可同一份 JSON 示例。
- Mock 设备和真实设备可以订阅相同命令 Topic。
- 每个命令具有稳定 `command_id`。
- 停止、超时、离线和失败语义明确。

## 4. M1：领域核心与状态机

目标：不依赖 MQTT、LLM 和真实硬件，完成确定性业务核心。

- [x] 创建 Python 项目和基础测试配置。
- [x] 实现核心 Pydantic 模型。
- [x] 实现 `WorldState`。
- [x] 实现 `SceneEvaluator` 的 F1 规则。
- [x] 实现最小 Permission Policy。
- [x] 实现最小 Safety Policy。
- [x] 实现行动状态机。
- [x] 实现 `WorkflowRuntime` 接口。
- [x] 实现 `SimpleWorkflow`。
- [ ] 实现结构化日志上下文。

### 必测状态

```text
pending
evaluating
checking
waiting_confirmation
executing
verifying
succeeded
failed
stopped
skipped
```

### M1 完成标准

- 单元测试能够覆盖所有合法状态转换。
- 非法状态转换被拒绝并记录。
- 用户拒绝、安全失败和执行停止不会进入后续动作。
- 不调用 LLM 也能完成 F1 的决策。

## 5. M2：Mock MQTT 闭环

目标：在没有真实机械臂的情况下验证完整 MQTT 协议和行动生命周期。

### Mock 设备

- [x] 订阅 `goodnight/{device_id}/command`。
- [x] 发布 availability 和 capabilities。
- [x] 返回 accepted、executing 和 succeeded。
- [x] 支持配置执行延迟。
- [x] 支持模拟失败。
- [x] 支持模拟超时。
- [x] 支持通过设备退出模拟离线。
- [x] 支持执行中停止。
- [x] 对重复 `command_id` 返回已有状态，不重复执行。

### Agent

- [x] 实现 `DeviceGateway` 接口。
- [x] 实现 `MqttDeviceGateway`。
- [x] 订阅 availability 和 capabilities 并维护 `DeviceRegistry`。
- [x] 在 Safety Policy 前同步真实设备状态和能力。
- [x] 实现 command/status 关联。
- [x] 实现等待、超时和停止。
- [x] 实现 `ResultVerifier` 的 Mock 验证。
- [x] 实现领域事件记录。
- [x] 提供触发 F1 的最小调试接口。

### M2 完成标准

- 一个模拟 Observation 能完整进入 succeeded。
- 设备失败时 Action 进入 failed。
- 执行中停止时 Action 进入 stopped。
- MQTT 断线时不会提前显示成功。
- 重复命令不会重复执行。
- 所有步骤可以通过三个 ID 串联排查。

## 6. M3：真实硬件联调

目标：不修改 Agent Core，只将 Mock 设备替换为真实设备。

- [ ] 真实设备发布 availability。
- [ ] 真实设备发布 capabilities。
- [ ] 真实设备订阅 command。
- [ ] 真实设备返回完整状态。
- [ ] 验证重复命令幂等。
- [ ] 验证 Agent stop。
- [ ] 验证硬件急停。
- [ ] 验证超时和断线安全状态。
- [ ] 固定摆位完成第一个真实动作。
- [ ] 接入结果验证信号。

### M3 完成标准

- Mock 与真机切换不修改场景规则和状态机。
- 硬件未确认成功时，Agent 不进入 succeeded。
- 停止后没有后续动作继续执行。
- 设备重连不会执行旧命令。
- 一次真实动作的日志和事件完整可追踪。

## 7. M4：API 与前端联调

前端结构确认后再开始，不反向影响 Agent Core。

- [ ] `POST /api/commands`
- [ ] `POST /api/actions/{id}/confirm`
- [ ] `POST /api/actions/{id}/reject`
- [ ] `POST /api/actions/{id}/stop`
- [ ] `GET /api/state`
- [ ] `GET /api/actions/{id}`
- [ ] `GET /api/capabilities`
- [ ] `GET /api/events`
- [ ] SSE 断线后重新获取最新状态。
- [ ] 前端只根据后端真实状态显示成功。

## 8. M5：LLM 与 F3

在 F1 确定性闭环稳定后开始。

- [ ] 定义 `ModelProvider` 接口。
- [ ] 接入一个模型实现。
- [ ] 实现用户意图结构化解析。
- [ ] 实现故事生成。
- [ ] 实现预设故事降级。
- [ ] 实现停止、换一个和降低音量。
- [ ] 确保 LLM 无法绕过 Permission 与 Safety Policy。

## 9. 第一批开发任务

建议按以下顺序提交，避免一个改动同时引入过多变量：

1. `chore: initialize python project and test setup`
2. `feat: add core domain models`
3. `feat: add action state machine`
4. `feat: add world state and F1 scene evaluator`
5. `feat: add workflow runtime and safety policy`
6. `feat: add mock mqtt device`
7. `feat: add mqtt device gateway`
8. `feat: add F1 mock workflow`
9. `feat: add stop timeout and idempotency`
10. `test: add end-to-end mock scenarios`

## 10. 测试矩阵

| 场景 | 期望结果 |
| --- | --- |
| 正常执行 | `succeeded` |
| 权限禁止 | `skipped` 或 `failed`，不下发命令 |
| 需要确认后拒绝 | `stopped`，不下发命令 |
| 需要确认后同意 | 继续执行 |
| 设备离线 | `failed`，不下发或停止等待 |
| 硬件超时 | `failed`，触发安全停止 |
| 执行中用户停止 | `stopped` |
| 硬件急停 | `stopped`，记录安全事件 |
| 重复 `command_id` | 不重复执行 |
| 设备报告成功但验证失败 | `failed` |
| MQTT 重连 | 不执行 retained 旧命令 |

## 11. 进入下一阶段的条件

### 引入 LangGraph

出现两项以上再评估：

- 一个行动包含多个复杂分支。
- 需要长时间暂停等待确认。
- 进程重启后需要从中间节点恢复。
- 出现多个 LLM 或工具步骤的动态路由。
- 自定义 Runtime 的持久化和恢复代码明显增加。

### 切换 PostgreSQL

- 多用户或多设备。
- 后端需要多实例运行。
- 需要稳定并发修改和历史查询。
- SQLite 已经限制联调或部署。

### 使用 WebSocket 或 WebRTC

- 浏览器实时上传音频。
- 出现持续双向流。
- 需要高频控制或二进制数据。

## 12. 当前阻塞项

- [ ] MQTT Broker 与认证方式未确认。
- [ ] Topic 和 QoS 未最终确认。
- [ ] 第一个真实硬件能力未确认。
- [ ] 硬件停止和急停反馈未确认。
- [ ] Result Verifier 可使用的感知信号未确认。

这些事项阻塞真实硬件联调，但不阻塞 M1 和 Mock MQTT 开发。

## 13. 当前实现仍需补齐

- [ ] 持久化结构化日志，目前使用可订阅的内存领域事件。
- [ ] 自动恢复 SSE 断线期间遗漏的事件，当前前端需重新查询 State 和 Action。
- [ ] 全局取消整个 Run，当前停止语义是停止单个 Action。
- [ ] MQTT Broker 断线和重连的自动化集成测试。
- [ ] 进程重启后的 Action 和命令恢复。
