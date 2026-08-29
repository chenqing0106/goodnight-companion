import type { AgentEvent, AgentWorldState } from "../api/types";

export type ActivityTone = "quiet" | "active" | "success" | "failed";

export interface VitalsEvaluationView {
  label: string;
  detail: string;
  progress: string;
  tone: ActivityTone;
}

export interface ActivityStep {
  key: string;
  label: string;
  detail: string;
  tone: ActivityTone;
  timestamp: string;
}

export interface VitalsRunView {
  runId: string;
  title: string;
  detail: string;
  timestamp: string;
  tone: ActivityTone;
  steps: ActivityStep[];
}

const TERMINAL_EVENT_TYPES = new Set([
  "action.succeeded",
  "action.failed",
  "action.stopped",
  "action.skipped",
]);

function isVitalsEvent(event: AgentEvent) {
  return event.payload.rule === "vitals_signal_indicator";
}

function findLast(
  events: AgentEvent[],
  predicate: (event: AgentEvent) => boolean,
) {
  return [...events].reverse().find(predicate) ?? null;
}

function payloadNumber(event: AgentEvent | null, key: string) {
  const value = event?.payload[key];
  return typeof value === "number" ? value : null;
}

function payloadString(event: AgentEvent | null, key: string) {
  const value = event?.payload[key];
  return typeof value === "string" ? value : null;
}

function outcomeCopy(outcome: string | null) {
  if (outcome === "stable") {
    return {
      label: "心率与血氧信号稳定",
      detail: "两项数据均为有效读数",
      tone: "success" as const,
    };
  }
  if (outcome === "finger_not_detected") {
    return {
      label: "未检测到手指",
      detail: "保持移开后会关闭指示灯",
      tone: "active" as const,
    };
  }
  return {
    label: "正在采集信号",
    detail: "等待心率与血氧形成一组有效数据",
    tone: "quiet" as const,
  };
}

export function buildVitalsEvaluation(
  events: AgentEvent[],
  world: AgentWorldState | undefined,
  requiredSamples: number | null,
): VitalsEvaluationView {
  const event = findLast(
    events,
    (candidate) =>
      candidate.event_type === "condition.evaluated" && isVitalsEvent(candidate),
  );
  const outcome =
    payloadString(event, "outcome") ?? world?.vitals_signal_state ?? null;
  const current =
    payloadNumber(event, "consecutive_samples") ?? world?.vitals_valid_streak ?? 0;
  const required =
    payloadNumber(event, "required_samples") ?? requiredSamples ?? 3;
  const copy = outcomeCopy(outcome);

  return {
    ...copy,
    progress: `${Math.min(current, required)}/${required}`,
  };
}

function targetMode(event: AgentEvent) {
  const target = event.payload.target;
  if (!target || typeof target !== "object" || Array.isArray(target)) return null;
  const parameters = (target as Record<string, unknown>).parameters;
  if (!parameters || typeof parameters !== "object" || Array.isArray(parameters)) {
    return null;
  }
  const mode = (parameters as Record<string, unknown>).mode;
  return typeof mode === "number" ? mode : null;
}

export function buildLatestVitalsRun(events: AgentEvent[]): VitalsRunView | null {
  const satisfied = findLast(
    events,
    (event) =>
      event.event_type === "condition.satisfied" &&
      isVitalsEvent(event) &&
      event.run_id !== null,
  );
  if (!satisfied?.run_id) return null;

  const runEvents = events.filter((event) => event.run_id === satisfied.run_id);
  const safety = findLast(
    runEvents,
    (event) => event.event_type === "safety.checked",
  );
  const tool = findLast(runEvents, (event) => event.event_type === "tool.called");
  const terminal = findLast(runEvents, (event) =>
    TERMINAL_EVENT_TYPES.has(event.event_type),
  );
  const mode = targetMode(satisfied);
  const failed = terminal
    ? terminal.event_type !== "action.succeeded"
    : false;
  const completed = terminal?.event_type === "action.succeeded";
  const tone: ActivityTone = failed
    ? "failed"
    : completed
      ? "success"
      : "active";
  const title = failed
    ? "自动控制没有完成"
    : completed
      ? mode === 2
        ? "指示灯已切换为绿色"
        : "指示灯已经关闭"
      : mode === 2
        ? "正在开启绿色指示灯"
        : "正在关闭指示灯";
  const detail = failed
    ? payloadString(terminal, "reason") ?? "硬件没有确认目标结果"
    : completed
      ? "Agent 已收到硬件返回的目标状态"
      : "条件满足后，正在完成安全检查和硬件控制";

  const safetyAllowed = safety?.payload.allowed;
  const safetyFailed = safetyAllowed === false;
  const steps: ActivityStep[] = [
    {
      key: "condition",
      label: "信号条件满足",
      detail: mode === 2 ? "连续信号有效" : "连续未检测到手指",
      tone: "success",
      timestamp: satisfied.timestamp,
    },
    {
      key: "safety",
      label: "检查设备与安全条件",
      detail: safety
        ? safetyFailed
          ? payloadString(safety, "reason") ?? "安全检查未通过"
          : "设备在线且支持指示灯控制"
        : "等待检查",
      tone: safety ? (safetyFailed ? "failed" : "success") : "quiet",
      timestamp: safety?.timestamp ?? satisfied.timestamp,
    },
    {
      key: "tool",
      label: "发送硬件控制指令",
      detail: tool ? "指令已经交给 ENV-S3" : "等待发送",
      tone: tool ? "success" : safety ? "active" : "quiet",
      timestamp: tool?.timestamp ?? safety?.timestamp ?? satisfied.timestamp,
    },
    {
      key: "result",
      label: "确认硬件结果",
      detail: terminal
        ? completed
          ? "硬件已确认目标状态"
          : payloadString(terminal, "reason") ?? "执行失败"
        : "等待硬件返回",
      tone: terminal ? (completed ? "success" : "failed") : tool ? "active" : "quiet",
      timestamp:
        terminal?.timestamp ??
        tool?.timestamp ??
        safety?.timestamp ??
        satisfied.timestamp,
    },
  ];

  return {
    runId: satisfied.run_id,
    title,
    detail,
    timestamp: terminal?.timestamp ?? satisfied.timestamp,
    tone,
    steps,
  };
}
