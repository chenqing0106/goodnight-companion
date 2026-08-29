# ENV-SENSING-S3 MQTT 接口说明

本文供软件工程师使用。设备 ID 为 `env-s3-01`。应用只需要连接 MQTT Broker、订阅传感器主题和状态主题，再向执行器主题发布命令。

## 1. 连接参数

当前公网联调参数：

| 项目 | 值 |
| --- | --- |
| Broker 主机 | `218.11.5.249` |
| MQTT TCP 端口 | `10317` |
| MQTT WebSocket 端口 | `10318` |
| 设备 ID | `env-s3-01` |
| 协议 | MQTT 3.1.1/5，用户名密码认证，当前为明文 TCP |

ESP32 使用：

```text
mqtt://218.11.5.249:10317
```

浏览器使用：

```text
ws://218.11.5.249:10318/mqtt
```

用户名和密码不要写死在业务代码、网页源码或 Git。当前联调账号由项目负责人通过安全渠道提供；生产环境应为每台设备建立独立账号和 ACL，并切换到 TLS/WSS。

所有主题均以设备 ID 开头：

```text
env-s3-01/<相对主题>
```

## 2. 主题总表

| 完整主题 | 方向 | QoS | Retain | 用途 |
| --- | --- | ---: | :---: | --- |
| `env-s3-01/status` | 设备 -> 软件 | 1 | 是 | 在线/离线状态，遗嘱消息 |
| `env-s3-01/sensor/temp` | 设备 -> 软件 | 0 | 否 | DHT11 温度 |
| `env-s3-01/sensor/humidity` | 设备 -> 软件 | 0 | 否 | DHT11 相对湿度 |
| `env-s3-01/sensor/light` | 设备 -> 软件 | 0 | 否 | KY-018 ADC 原始值，不是 lux |
| `env-s3-01/sensor/heart_rate` | 设备 -> 软件 | 0 | 否 | MAX30102 心率估计 |
| `env-s3-01/sensor/spo2` | 设备 -> 软件 | 0 | 否 | MAX30102 血氧估计 |
| `env-s3-01/actuator/rgb/set` | 软件 -> 设备 | 1 | 否 | KY-016 三色 LED 命令 |
| `env-s3-01/actuator/rgb/state` | 设备 -> 软件 | 1 | 否 | 三色 LED 执行回执 |
| `env-s3-01/actuator/led/set` | 软件 -> 设备 | 1 | 否 | WS2812B 灯带命令 |
| `env-s3-01/actuator/led/state` | 设备 -> 软件 | 1 | 否 | 灯带执行回执 |

以下主题已预留但当前固件不会发布：`sensor/presence`、`sensor/distance`、`sensor/sound`。

## 3. 传感器数据格式

温度、湿度、光敏、心率和血氧都使用同一个 JSON 外壳：

```json
{"value":25.0,"unit":"C","valid":true,"ts_ms":123456}
```

字段定义：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `value` | number | 数值。只有 `valid=true` 时才能作为有效测量使用 |
| `unit` | string | 单位，见下表 |
| `valid` | boolean | 数据是否有效，应用必须先判断此字段 |
| `ts_ms` | integer | 设备启动后的毫秒数，不是 Unix 时间戳 |
| `error` | string | `valid=false` 时的错误原因；成功消息没有该字段 |

各主题单位和采样周期：

| 主题 | unit | 典型周期 | 备注 |
| --- | --- | ---: | --- |
| `sensor/temp` | `C` | 2 秒 | DHT11 温度 |
| `sensor/humidity` | `%RH` | 2 秒 | DHT11 相对湿度 |
| `sensor/light` | `adc_count` | 1 秒 | 0 到 4095 的 ADC 原始计数，当前不换算 lux |
| `sensor/heart_rate` | `bpm` | 1 秒 | 需要手指稳定贴合，属于消费级估计 |
| `sensor/spo2` | `%` | 1 秒 | 需要手指稳定贴合，属于消费级估计 |

无效消息示例：

```json
{"value":0,"unit":"bpm","valid":false,"error":"finger_not_detected","ts_ms":123456}
```

常见 `error`：`finger_not_detected`、`collecting_or_unstable`、`ESP_ERR_TIMEOUT`、`ESP_ERR_INVALID_STATE`。无效消息不是零值，不能把 `value=0` 当成真实测量。

MAX30102 需要约 8 到 10 秒稳定采样后才可能得到有效心率和血氧。应用应显示“采集中/信号不稳定”，不要把无效结果显示成 0；该数据不能用于医疗诊断。

## 4. 在线状态

设备连接成功后发布并保留：

```json
{"state":"online"}
```

MQTT 非正常断开时由 Broker 发布遗嘱并保留：

```json
{"state":"offline"}
```

软件启动时订阅 `env-s3-01/status`，即可立即获得最后状态。不能只根据传感器消息判断在线，因为传感器消息不是 retained。

## 5. 执行器命令

### 5.1 KY-016 三色 LED

向 `env-s3-01/actuator/rgb/set` 发布纯文本单字符，QoS 1：

| Payload | 效果 |
| --- | --- |
| `0` | 熄灭 |
| `1` | 红色 |
| `2` | 绿色 |
| `3` | 蓝色 |

不要发布 JSON、空字符串或多字符数字。设备在 `env-s3-01/actuator/rgb/state` 返回：

```json
{"accepted":true,"command":2,"state":"green"}
```

### 5.2 WS2812B 灯带

向 `env-s3-01/actuator/led/set` 发布纯文本单字符，QoS 1。当前灯带配置为 10 颗：

| Payload | 效果 |
| --- | --- |
| `0` | 熄灭 |
| `1` | 暖色呼吸 |
| `2` | 冷蓝呼吸 |
| `3` | 多彩跑马灯 |
| `4` | 白色常亮 |
| `5` | 蓝色追逐 |
| `6` | 彩虹 |
| `7` | 自动循环 |

设备在 `env-s3-01/actuator/led/state` 返回：

```json
{"accepted":true,"command":3,"state":"marquee"}
```

错误回执示例：

```json
{"accepted":false,"reason":"payload_must_be_0_to_7"}
```

应用应以回执中的 `accepted` 为准。MQTT 的 `publish()` 返回成功只代表消息交给客户端队列，不代表灯已经执行。

## 6. 软件订阅和发布范围

软件平台通常订阅：

```text
env-s3-01/status
env-s3-01/sensor/#
env-s3-01/actuator/+/state
```

软件平台只向下面两个主题发布：

```text
env-s3-01/actuator/rgb/set
env-s3-01/actuator/led/set
```

生产环境不要用 `#` 作为业务订阅，也不要向 `sensor/#` 发布数据。每台设备使用自己的设备 ID，避免多台设备串数据。

## 7. JavaScript 示例

浏览器必须使用 WebSocket 地址，不能把 TCP 地址 `mqtt://...:10317` 传给浏览器：

```javascript
const client = mqtt.connect('ws://218.11.5.249:10318/mqtt', {
  username: '<从部署配置读取>',
  password: '<从部署配置读取>'
});

client.on('connect', () => {
  client.subscribe('env-s3-01/status', { qos: 1 });
  client.subscribe('env-s3-01/sensor/#');
  client.subscribe('env-s3-01/actuator/+/state', { qos: 1 });
});

client.on('message', (topic, buffer) => {
  const data = JSON.parse(buffer.toString());
  if (topic === 'env-s3-01/sensor/temp' && data.valid) {
    console.log(data.value, data.unit);
  }
});

client.publish('env-s3-01/actuator/led/set', '3', { qos: 1 });
```

## 8. Python 示例

```python
import json
import paho.mqtt.client as mqtt

DEVICE = "env-s3-01"

def on_connect(client, userdata, flags, reason_code, properties=None):
    client.subscribe(f"{DEVICE}/status", qos=1)
    client.subscribe(f"{DEVICE}/sensor/#")
    client.subscribe(f"{DEVICE}/actuator/+/state", qos=1)

def on_message(client, userdata, message):
    data = json.loads(message.payload.decode("utf-8"))
    if message.topic.endswith("/status"):
        print("device state:", data.get("state"))
    elif data.get("valid") is False:
        print("invalid reading:", message.topic, data.get("error"))
    else:
        print(message.topic, data["value"], data["unit"])

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set("<从部署配置读取>", "<从部署配置读取>")
client.on_connect = on_connect
client.on_message = on_message
client.connect("218.11.5.249", 10317, 60)
client.publish(f"{DEVICE}/actuator/rgb/set", "1", qos=1)
client.loop_forever()
```

## 9. 重连和安全要求

客户端应启用自动重连，并在重连成功后重新订阅所有主题。控制命令建议使用 QoS 1，但仍需等待对应的 `state` 回执；超时后由应用决定是否重发，避免无限重发造成重复效果切换。

当前 `10317` 是明文 MQTT，仅适合联调。生产环境应使用域名、TLS MQTT（通常 `8883`）或受信任的云 Broker，配置 CA 证书、密码文件、ACL 和防火墙；不要把 MQTT 密码提交到 Git 或打包进公开网页。

## 10. 与固件的边界

传感器驱动只负责读取硬件；`environment_application` 负责按周期采样；`mqtt_transport` 负责添加设备 ID、连接 Broker 和发布消息；`device_app` 负责校验命令并调用 LED 驱动。应用层不应直接操作 GPIO，也不应自行拼接另一套主题或 JSON 格式。
