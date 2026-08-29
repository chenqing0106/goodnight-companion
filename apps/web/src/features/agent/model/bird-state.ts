import type { AgentPhase } from "./reducer";

export type BirdVisualState = "f1" | "f2" | "f3" | "f4" | "f5";

/** "auto" 表示跟随前台 Agent 状态自动切换；其余为后台强制指定的状态 */
export type BirdControlMode = "auto" | BirdVisualState;

export interface BirdStateMeta {
  id: BirdVisualState;
  label: string;
  subtitle: string;
  file: string;
  alt: string;
  /** 自动模式下，什么情况会触发这个状态 */
  trigger: string;
}

export const BIRD_STATES: BirdStateMeta[] = [
  {
    id: "f1",
    label: "F1 · 安静守夜",
    subtitle: "NIGHT WATCH",
    file: "/assets/bird/f1-night-watch-retro.svg",
    alt: "好梦鸟 F1 安静守夜状态",
    trigger: "空闲等待，或今晚的流程已经完成",
  },
  {
    id: "f2",
    label: "F2 · 生气阻止",
    subtitle: "BLOCKING",
    file: "/assets/bird/f2-blocking-retro.svg",
    alt: "好梦鸟 F2 生气阻止状态",
    trigger: "动作等待确认、被停止，或执行失败",
  },
  {
    id: "f3",
    label: "F3 · 讲故事陪伴",
    subtitle: "STORYTELLING",
    file: "/assets/bird/f3-storytelling-retro.svg",
    alt: "好梦鸟 F3 讲故事陪伴状态",
    trigger: "正在准备睡前陪伴内容",
  },
  {
    id: "f4",
    label: "F4 · 摇摆放松",
    subtitle: "RELAXING",
    file: "/assets/bird/f4-relaxing-retro.svg",
    alt: "好梦鸟 F4 摇摆放松状态",
    trigger: "正在执行或确认睡前动作",
  },
  {
    id: "f5",
    label: "F5 · 着急唤醒",
    subtitle: "WAKE UP",
    file: "/assets/bird/f5-wakeup-retro.svg",
    alt: "好梦鸟 F5 着急唤醒状态",
    trigger: "渐进唤醒场景正在运行",
  },
];

export const BIRD_STATE_MAP: Record<BirdVisualState, BirdStateMeta> =
  Object.fromEntries(BIRD_STATES.map((state) => [state.id, state])) as Record<
    BirdVisualState,
    BirdStateMeta
  >;

export function isBirdControlMode(value: unknown): value is BirdControlMode {
  return (
    value === "auto" ||
    (typeof value === "string" &&
      BIRD_STATES.some((state) => state.id === value))
  );
}

/**
 * 自动模式下的状态推导：
 * - 唤醒场景运行中优先展示 F5
 * - 其余跟随 Agent 阶段
 */
export function resolveAutoBirdState(input: {
  phase: AgentPhase;
  wakeUpRunning: boolean;
}): BirdVisualState {
  if (input.wakeUpRunning) return "f5";

  switch (input.phase) {
    case "preparing":
      return "f3";
    case "waiting_confirmation":
    case "stopped":
    case "failed":
      return "f2";
    case "executing":
    case "verifying":
      return "f4";
    case "idle":
    case "complete":
    default:
      return "f1";
  }
}
