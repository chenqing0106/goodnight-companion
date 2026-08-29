# 后台与 ENV-S3 硬件调试

这份说明用于调试后台页面、FastAPI 后端和 ENV-S3 硬件。后台地址是
<http://localhost:3000/admin>。

## 1. 正常启动

打开两个终端，按顺序启动后端和前端。

终端 1，启动真实硬件后端：

```bash
cd /Users/qingchen/Code/goodnight-agent
uv run uvicorn goodnight_agent.api.app:app --reload --env-file .env.hardware
```

看到下面两类信息表示后端服务已启动：

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

终端 2，启动前端：

```bash
cd /Users/qingchen/Code/goodnight-companion/apps/web
pnpm dev
```

然后打开 <http://localhost:3000/admin>。停止服务时，在对应终端按 `Control + C`。

## 2. 先判断哪一层出了问题

按照下面的顺序检查，不要先反复点击灯带按钮。

### 页面打不开

访问 <http://localhost:3000/admin>。如果浏览器显示“拒绝访问”，说明前端没有启动，
或者 3000 端口被其他程序占用。回到前端终端确认 `pnpm dev` 仍在运行。

查看端口由谁占用：

```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

### 页面能打开，但提示后端不可用

访问 <http://127.0.0.1:8000/health>。正常结果是：

```json
{"status":"ok"}
```

如果打不开，说明 FastAPI 后端没有运行。重新执行终端 1 的启动命令。也可以查看
8000 端口：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

### 后端正常，但页面显示设备离线

这表示前后端都正常，离线的是 ENV-S3 硬件或它的 MQTT 连接。先运行只读检查：

```bash
cd /Users/qingchen/Code/goodnight-agent
make hardware-status
```

重点看三项：

- `online`：硬件已连接 Broker，可以继续测试。
- `offline`：硬件主动断开或 Broker 收到了遗嘱消息，需要检查开发板供电、网络和固件。
- `unknown`：没有收到状态，检查 `.env.hardware` 中的 Broker 地址、端口和认证信息。

这个命令只读取设备和传感器状态，不会控制灯。

## 3. 安全测试指示灯和灯带

只有页面显示设备在线时再测试。一次只发一个命令，等待页面显示成功或失败后再点下一个。

### RGB 指示灯

建议顺序：

1. 先点“关闭”。
2. 再分别测试红、绿、蓝。
3. 每次确认实体灯变化，并观察页面反馈。

RGB 值为：

| 值 | 效果 |
| --- | --- |
| 0 | 关闭 |
| 1 | 红色 |
| 2 | 绿色 |
| 3 | 蓝色 |

### WS2812B 灯带

当前前后端只使用固件已有的四个值：

| 值 | 前端名称 |
| --- | --- |
| 0 | 熄灭 |
| 7 | 模式 7 |
| 8 | 模式 8 |
| 9 | 模式 9 |

建议先测试 `0`，确认可以熄灭；再逐个测试 `7`、`8`、`9`。如果点击后设备立刻离线，
先停止测试并重启开发板，这通常是固件执行该模式时异常，不是前端或后端服务离线。

## 4. 页面控制失败时直接检查接口

以下命令用于区分“前端问题”和“后端/硬件问题”。先读取状态：

```bash
curl http://127.0.0.1:8000/api/devices
curl http://127.0.0.1:8000/api/devices/env-s3-01/sensors
```

仅在设备在线时，可以先用熄灭命令做最小控制测试：

```bash
curl -X POST http://127.0.0.1:8000/api/devices/env-s3-01/control \
  -H 'Content-Type: application/json' \
  -d '{"capability":"set_led_mode","mode":0}'
```

- 接口成功、实体灯也变化：后端和硬件正常，继续检查前端。
- 返回设备离线：检查开发板和 MQTT。
- 一直等待后超时：命令可能已发出，但固件没有返回执行回执。
- 返回拒绝原因：以硬件回执中的 `accepted` 和 `reason` 为准。

MQTT 的“发送成功”不等于灯已经执行，必须等硬件的 `state` 回执。

## 5. 常见现象速查

| 现象 | 最可能的原因 | 先做什么 |
| --- | --- | --- |
| `localhost:3000` 拒绝访问 | 前端未启动 | 运行 `pnpm dev` |
| 页面能打开，但全部数据请求失败 | 后端未启动 | 打开 `/health`，重启后端 |
| 后端正常，设备显示离线 | 硬件或 MQTT 离线 | 运行 `make hardware-status` |
| 有传感器数据，但某项一直不更新 | 对应传感器 Topic 未发布或数据无效 | 查看硬件状态输出和固件串口 |
| 点击后返回超时 | 固件没有发送执行器回执 | 检查 `actuator/+/state` 回执 |
| 点击某个灯带模式后设备离线 | 固件在该模式中异常或重启 | 停止点击，重启开发板并查固件 |
| 修改代码后页面没变化 | 开发服务未重载或浏览器缓存 | 刷新页面，必要时重启前端 |

## 6. 每次联调前的最短检查清单

1. 后端终端正在运行，`/health` 返回 `ok`。
2. 前端终端正在运行，`/admin` 可以打开。
3. `make hardware-status` 显示设备 `online`。
4. 五类传感器至少能收到预期数据。
5. 控灯时先发关闭命令，再逐个测试其他模式。
6. 每次等待硬件回执，不连续快速点击。

`.env.hardware` 包含 MQTT 认证信息，不要截图公开，也不要提交到 Git。
