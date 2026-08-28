import type { AgentDevice, SensorReading } from "../api/types";
import type {
  MemoryItem,
  ProactivityMode,
} from "../model/companion-runtime";

export const PREVIEW_MEMORIES: MemoryItem[] = [
  {
    id: 1,
    title: "通常在 00:10 前准备睡觉",
    body: "超过这个时间仍在使用手机时，先温柔提醒一次。",
    source: "来自你过去 7 晚的选择",
  },
  {
    id: 2,
    title: "更喜欢没有情节冲突的故事",
    body: "优先选择自然、旅行和微小日常，不讲悬疑内容。",
    source: "来自你在 8 月 26 日的对话",
  },
  {
    id: 3,
    title: "收手机不需要叫醒我",
    body: "稳定入睡后可自动执行；如果位置不确定，直接跳过。",
    source: "由你在主动性设置中确认",
  },
];

export const PREVIEW_PROFILE: {
  mode: ProactivityMode;
  cameraEnabled: boolean;
} = {
  mode: "平衡",
  cameraEnabled: true,
};

export const PREVIEW_DEVICES: AgentDevice[] = [
  {
    device_id: "床头相机",
    availability: "online",
    capabilities: ["画面仅在本地识别，不保存卧室视频"],
    capabilities_known: true,
  },
  {
    device_id: "六轴机械臂",
    availability: "online",
    capabilities: ["安全区正常，急停按钮可用"],
    capabilities_known: true,
  },
  {
    device_id: "床头灯",
    availability: "online",
    capabilities: ["红外控制已连接，当前亮度 18%"],
    capabilities_known: true,
  },
  {
    device_id: "床垫压力传感器",
    availability: "online",
    capabilities: ["已检测到在床状态，信号稳定"],
    capabilities_known: true,
  },
  {
    device_id: "角色声音",
    availability: "online",
    capabilities: ["音量已限制为夜间 24%"],
    capabilities_known: true,
  },
  {
    device_id: "拉被子能力",
    availability: "offline",
    capabilities: ["等待硬件安全评估，本次仅保留灯光唤醒"],
    capabilities_known: true,
  },
];

export const PROACTIVITY_COPY: Record<ProactivityMode, string> = {
  安静: "只响应你的主动指令，不主动询问。",
  平衡: "重要场景先询问，安全的睡后收尾可自动执行。",
  积极: "在更多场景主动提醒，但仍会先征得同意。",
};

export function createPreviewSensorReadings(): SensorReading[] {
  const receivedAt = new Date().toISOString();
  const common = {
    device_id: "env-s3-01",
    valid: true,
    error: null,
    ts_ms: 185400,
    received_at: receivedAt,
  } as const;

  return [
    { ...common, sensor: "temp", value: 24, unit: "C" },
    { ...common, sensor: "humidity", value: 56, unit: "%RH" },
    { ...common, sensor: "light", value: 738, unit: "adc_count" },
    { ...common, sensor: "heart_rate", value: 68, unit: "bpm" },
    { ...common, sensor: "spo2", value: 98, unit: "%" },
  ];
}
