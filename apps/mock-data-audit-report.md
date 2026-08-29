# Mock/真实数据判断逻辑扫描报告

## 扫描范围
- **项目路径**: `web/src`
- **框架**: Next.js (React + TypeScript)
- **扫描规则**: `mock|isMock|preview|fixtures|demo|fake|dummy|hardcoded|dataMode`

---

## 1. 数据层/配置层判断

### `web/src/features/agent/companion-config.ts`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L26-L32 | `pageDataMode: { tonight: "live", devices: "live", memory: "preview", profile: "preview" }` | 配置层 | ✅ 配置层（合理） |
| L37-L43 | `preview: { actionStatus: "succeeded", progress: 100, sleepState: "asleep", ... }` | 配置层 | ✅ 配置层（合理） |

**分析**: 这是整个应用的 mock/真实数据源开关中心。`pageDataMode` 决定了每个页面使用 `live` 还是 `preview` 数据。硬编码的 preview 默认值放在配置层是合理的，但这是一个**集中式开关**，所有页面的数据模式判断都依赖这个配置。

---

## 2. Service/API 层判断

### `web/src/features/agent/api/client.ts`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L133-L147 | `startMockActivity()` 调用 `/api/debug/mock-activity` | API Client | ✅ Service 层（合理） |
| L184-L210 | `startPickupDemo()` 硬编码 `source: "nextjs_f1_demo"` 和 facts 对象 | API Client | ⚠️ Service 层（边界问题） |

**分析**:
- `startMockActivity()` 是后端调试接口的封装，属于 Service 层，合理。
- `startPickupDemo()` 中**硬编码了演示场景的所有观测数据**（`person_in_bed: true`, `stable_for_seconds: 20*60`, `inferred_sleep_state: "asleep"` 等）。这实际上是**假数据生成逻辑**嵌在了 API Client 里。这些硬编码的演示数据应该上提到配置层或独立的 demo-data 模块，而不是埋在 Service 方法内部。

---

### `web/src/features/agent/api/schema.d.ts`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L307-L309 | `ActionRequest.device_id` 默认 `"mock-arm"` | 生成的 Schema | ⚠️ 数据源层（后端契约问题） |

**分析**: 这是 OpenAPI 生成的类型定义。后端在接口契约中就把默认值设成了 `"mock-arm"`，说明 mock 数据已经渗透到 API 契约层。这是**后端/数据源层的问题**。

---

## 3. Model/数据处理层判断

### `web/src/features/agent/model/agent-activity.ts`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L49-L52 | `payload.mock !== true` 作为解析条件 | Model | ⚠️ 数据源层（不应在前端判断） |

**分析**: 在解析 activity step 事件时，把 `payload.mock !== true` 作为**数据有效性校验条件**。这意味着后端发送的事件里有一个 `mock` 字段标记数据来源，而前端 Model 层需要理解并过滤这个字段。这属于**数据源层的标记泄露到了 Model 层**。理想情况下，后端应该在返回真实数据时就已经过滤掉 mock 事件，或者 mock 事件应该通过不同的 API 端点/通道返回，而不是让前端 Model 去判断。

---

## 4. Hooks/Runtime 层判断

### `web/src/features/agent/hooks/use-preview-runtime.ts`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L27-L44 | `PREVIEW_ACTION_ID`, `PREVIEW_RUN_ID`, `createPreviewAction()` | Hook | ❌ 数据源层（严重越界） |
| L46-L89 | `createPreviewSnapshot()` 硬编码整个 world 状态对象 | Hook | ❌ 数据源层（严重越界） |
| L91-L109 | `createInitialState()` 组合 preview 数据 | Hook | ❌ 数据源层（严重越界） |
| L112-L120 | `useState(() => PREVIEW_MEMORIES.map(...))` | Hook | ❌ 数据源层（严重越界） |

**分析**: 这是**最严重的越界**。整个文件是一个 Hook，但它实际上是在：
1. 生成硬编码的假 action（`createPreviewAction`）
2. 生成硬编码的假 world 快照（`createPreviewSnapshot`，包含所有设备状态、传感器状态、人员状态）
3. 生成硬编码的假初始状态（`createInitialState`）

这些**假数据生成逻辑**完全不应该在 Hook 层。Hook 层应该只负责状态管理和生命周期，数据应该来自：
- `data/preview-fixtures.ts`（已存在，但只被部分使用）
- 或一个独立的 `preview-data-provider` 服务层

当前的问题是 `use-preview-runtime.ts` 同时扮演了：
- **数据源提供者**（生成假数据）
- **状态管理者**（useState/useCallback）
- **业务逻辑编排者**（组合 snapshot、actions、automation）

这三个角色应该被拆分到不同层级。

---

### `web/src/features/agent/hooks/use-live-companion-runtime.ts`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L10-L13 | `LIVE_MEMORY_RUNTIME = { status: "unavailable", items: [] }` | Hook | ⚠️ 数据源层（默认值问题） |
| L15-L18 | `LIVE_PROFILE_RUNTIME = { status: "unavailable" }` | Hook | ⚠️ 数据源层（默认值问题） |

**分析**: 这里硬编码了 "unavailable" 的降级状态。虽然这不是 mock 数据，但属于**硬编码的降级/空状态**。这在 Hook 层是常见的做法，但如果这些空状态需要被多个地方共享，应该提取到配置层或 model 层。

---

## 5. 组件层判断

### `web/src/features/agent/components/goodnight-companion-app.tsx`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L66-L83 | `selectRuntime(mode)` 根据 `mode` 选择 runtime | 组件层 | ⚠️ 应用层（路由/编排层） |
| L172-L179 | `needsLiveAgent && needsPreview` 决定渲染哪个 App 组件 | 组件层 | ⚠️ 应用层（路由/编排层） |

**分析**: 
- `CompanionShell` 组件里做了 runtime 选择逻辑：`mode === "preview" ? previewRuntime : liveRuntime`。这是**在组件层做数据源路由决策**。这个决策应该上提到应用初始化层，由上层决定注入哪个 runtime，组件只接收一个统一的 `CompanionRuntime` 接口。
- `GoodnightCompanionApp` 根据配置决定渲染 `MixedDataApp`、`PreviewOnlyApp` 还是 `LiveOnlyApp`。这个应用级编排决策放在根组件里是合理的，但如果能进一步提取到应用配置层会更好。

---

### `web/src/features/agent/components/pages/tonight-page.tsx`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L129-L133 | `useSensorReadings({ enabled: dataMode === "live" })` | 组件层 | ❌ Service/Hooks 层 |
| L134 | `const previewReadings = useMemo(() => createPreviewSensorReadings(), [])` | 组件层 | ❌ 数据源层 |
| L136 | `const sensorReadings = dataMode === "preview" ? previewReadings : liveSensors.readings` | 组件层 | ❌ 数据源层 |
| L137 | `const sensorError = dataMode === "preview" ? null : liveSensors.error` | 组件层 | ❌ 数据源层 |
| L138 | `const sensorsLoading = dataMode === "live" && liveSensors.isLoading` | 组件层 | ❌ 数据源层 |
| L284 | `dataMode === "preview" ? "模拟状态" : \`${validSensorCount}/${SENSOR_ITEMS.length} 有效\`` | 组件层 | ❌ 展示层（UI文案不应耦合数据判断） |
| L317 | `readingMeta(reading, dataMode === "preview")` | 组件层 | ❌ 数据源层 |
| L500-L502 | `dataMode === "preview" ? "睡眠...来自本地预览数据" : "睡眠...直接读取自 Agent 环境快照"` | 组件层 | ❌ 展示层 |
| L543-L545 | `dataMode === "preview" ? "这只会更新本地预览状态" : "这会向现有后端提交..."` | 组件层 | ❌ 展示层 |
| L548 | `dataMode === "preview" ? "本地状态" : "真实状态"` | 组件层 | ❌ 展示层 |

**分析**: `tonight-page.tsx` 是**mock/真实数据判断最密集的组件**。它直接在 JSX 和组件逻辑中做了大量 `dataMode === "preview"` 的条件判断，涉及：

1. **数据源选择**: 传感器读数选择 preview 还是 live —— 应该由统一的 data provider 处理
2. **错误状态掩盖**: `dataMode === "preview" ? null : liveSensors.error` —— preview 模式下强制忽略错误，这在组件层做很危险
3. **UI 文案耦合**: 大量文案直接根据 dataMode 变化 —— 应该用国际化或文案配置表，而不是在组件里写死条件
4. **Loading 状态耦合**: `sensorsLoading` 只在 live 模式下有意义 —— 这是数据源层的特性，不应该让组件感知

**核心问题**: 组件层同时承担了**数据源路由**和**UI 渲染**两个职责。理想情况下，组件只应该看到一个统一的 `sensorReadings: SensorReading[]`，而不应该知道这些数据来自 preview 还是 live。

---

### `web/src/features/agent/components/pages/devices-page.tsx`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L36-L39 | `subtitle={dataMode === "preview" ? "本地预览设备..." : "后端已经登记的设备..."}` | 组件层 | ❌ 展示层 |
| L62-L65 | `dataMode === "preview" ? \`${onlineCount} 项能力可用\` : \`${onlineCount} 台设备在线\`` | 组件层 | ❌ 展示层 |
| L69-L74 | 设备列表副标题的多重 dataMode 判断 | 组件层 | ❌ 展示层 |
| L150-L153 | `dataMode === "preview" ? "已由本地预览数据提供" : "已由后端确认"` | 组件层 | ❌ 展示层 |

**分析**: devices-page 也有类似的文案耦合问题，但比 tonight-page 轻。主要是副标题和详情文案根据 dataMode 变化。这些文案判断不应该在组件层硬编码。

---

### `web/src/features/agent/components/pages/profile-page.tsx`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L12 | `if (runtime.status === "ready")` 条件渲染 | 组件层 | ✅ 组件层（合理） |
| L96 | `<span>过去 7 天主动询问 4 次，自动收尾 2 次</span>` | 组件层 | ❌ 数据源层（硬编码统计） |

**分析**: 
- `runtime.status === "ready"` 是一个正常的 UI 状态判断，合理。
- 但 L96 的**统计数字是硬编码的**（"4次询问，2次收尾"），这是假数据直接写死在组件层。应该来自 API 或配置。

---

## 6. 数据层判断

### `web/src/features/agent/data/preview-fixtures.ts`

| 位置 | 代码 | 当前层级 | 应属层级 |
|------|------|----------|----------|
| L7-L26 | `PREVIEW_MEMORIES` 硬编码数组 | 数据层 | ✅ 数据层（合理） |
| L28-L34 | `PREVIEW_PROFILE` 硬编码对象 | 数据层 | ✅ 数据层（合理） |
| L36-L73 | `PREVIEW_DEVICES` 硬编码设备列表 | 数据层 | ✅ 数据层（合理） |
| L75-L79 | `PROACTIVITY_COPY` 文案映射 | 数据层 | ⚠️ 展示层/国际化层 |
| L81-L98 | `createPreviewSensorReadings()` 假数据生成 | 数据层 | ✅ 数据层（合理） |

**分析**: 这个文件是**唯一合理放置 mock 数据的地方**。所有假数据都集中在这里，职责清晰。
- `PROACTIVITY_COPY` 是文案配置，严格来说属于展示层，但放在数据层也可以接受。
- `createPreviewSensorReadings()` 是假数据工厂函数，放在数据层合理。

**但是**: 这个文件虽然存在，但 `use-preview-runtime.ts` 并没有完全使用它，而是自己内部又硬编码了很多数据（如 `createPreviewSnapshot` 中的 world 状态）。这是**数据源层和 Hooks 层的职责重复**。

---

## 汇总: 各层级判断数量

| 层级 | 文件数 | 判断点数量 | 风险等级 |
|------|--------|-----------|----------|
| 配置层 | 1 | 2 | 🟢 低 |
| Service/API 层 | 1 | 2 | 🟡 中 |
| Model 层 | 1 | 1 | 🟡 中 |
| Hooks 层 | 2 | 6 | 🔴 高 |
| 组件层 | 4 | 15+ | 🔴 高 |
| 数据层 | 1 | 5 | 🟢 低 |

---

## 核心问题总结

### 🔴 最严重: Hooks 层直接生成假数据
`use-preview-runtime.ts` 同时是：
- 状态管理 Hook
- 假数据生成器
- 业务逻辑编排器

**应该**: 把假数据生成提取到 `data/preview-fixtures.ts` 或新建 `services/preview-data-provider.ts`，Hook 只负责消费。

### 🔴 严重: 组件层直接感知 dataMode 做数据源路由
`tonight-page.tsx` 和 `devices-page.tsx` 里有大量 `dataMode === "preview"` 判断，涉及：
- 选择哪个数据源
- 掩盖错误状态
- 切换 UI 文案

**应该**: 组件只接收统一格式的数据，数据源路由在上层（Hook 或 Service 层）完成。

### 🟡 中等: API Client 里硬编码演示数据
`client.ts` 的 `startPickupDemo()` 方法里写死了演示场景的观测数据。

**应该**: 提取到 `data/demo-scenarios.ts` 配置模块。

### 🟡 中等: Model 层需要判断 mock 标记
`agent-activity.ts` 的解析逻辑依赖 `payload.mock !== true`。

**应该**: 后端应该统一返回格式，前端 Model 层不需要关心数据是否来自 mock。

### 🟢 轻微: 硬编码统计数字
`profile-page.tsx` 里的 "4次询问，2次收尾" 是假数据。

**应该**: 接入真实 API 前，用 `preview-fixtures.ts` 中的配置替换。

---

## 重构建议优先级

### P0: 建立统一的数据源抽象
```typescript
// 目标: 组件层完全不感知 dataMode
interface SensorDataProvider {
  readings: SensorReading[];
  error: string | null;
  isLoading: boolean;
}

// 在 Hook/Service 层统一处理
function useSensorData(mode: DataMode): SensorDataProvider {
  const live = useSensorReadings({ enabled: mode === 'live', ... });
  const preview = useMemo(() => createPreviewSensorReadings(), []);
  
  return mode === 'preview' 
    ? { readings: preview, error: null, isLoading: false }
    : live;
}
```

### P1: 拆分 `use-preview-runtime.ts`
- `data/preview-fixtures.ts` — 扩展，包含所有假数据
- `services/preview-snapshot-builder.ts` — 组装 preview 状态
- `hooks/use-preview-runtime.ts` — 只保留状态管理

### P2: 清理组件层的 dataMode 判断
- 使用文案配置表替代组件内硬编码的条件文案
- 错误状态处理下沉到 Service 层

### P3: 后端契约清理
- 移除 `ActionRequest.device_id` 的 `"mock-arm"` 默认值
- 统一 mock/真实事件的返回格式，或分通道返回
