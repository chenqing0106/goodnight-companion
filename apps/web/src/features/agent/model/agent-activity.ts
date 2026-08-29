import type { AgentEvent } from "../api/types";

export type AgentActivityPhase =
  | "observation"
  | "evaluation"
  | "conclusion"
  | "plan"
  | "safety"
  | "action"
  | "verification";

export type AgentActivityStepKind = "narrative" | "checks" | "plan" | "tool";

export type AgentActivityThreadStatus = "running" | "completed" | "failed" | "stopped";

export interface AgentActivityToolView {
  name: string;
  parameters: Record<string, unknown>;
  execution: "real" | "simulated";
  deviceId: string;
  status: string;
  receipt: string | null;
}

export interface AgentActivityStepView {
  id: string;
  phase: AgentActivityPhase;
  phaseLabel: string;
  kind: AgentActivityStepKind;
  clock: string | null;
  title: string;
  detail: string;
  evidence: string[];
  checks: string[];
  plan: string[];
  tools: AgentActivityToolView[];
  toolStatus: "running" | "done" | "failed" | null;
  timestamp: string;
  status: "active" | "succeeded" | "failed";
}

export interface AgentActivityThreadView {
  runId: string;
  monitorId: string;
  subject: string;
  scenario: string | null;
  status: AgentActivityThreadStatus;
  steps: AgentActivityStepView[];
}

const PHASE_LABELS: Record<AgentActivityPhase, string> = {
  observation: "观察",
  evaluation: "判断",
  conclusion: "结论",
  plan: "计划",
  safety: "确认",
  action: "行动",
  verification: "验证",
};

const STEP_KINDS = new Set<AgentActivityStepKind>([
  "narrative",
  "checks",
  "plan",
  "tool",
]);

function isPhase(value: unknown): value is AgentActivityPhase {
  return typeof value === "string" && value in PHASE_LABELS;
}

function isThreadStatus(value: unknown): value is AgentActivityThreadStatus {
  return (
    value === "running" ||
    value === "completed" ||
    value === "failed" ||
    value === "stopped"
  );
}

type ToolStatus = NonNullable<AgentActivityStepView["toolStatus"]>;

function isToolStatus(value: unknown): value is ToolStatus {
  return value === "running" || value === "done" || value === "failed";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function parseTools(value: unknown): AgentActivityToolView[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const tool = item as Record<string, unknown>;
    if (
      typeof tool.name !== "string" ||
      (tool.execution !== "real" && tool.execution !== "simulated")
    ) {
      return [];
    }
    return [
      {
        name: tool.name,
        parameters:
          tool.parameters && typeof tool.parameters === "object"
            ? (tool.parameters as Record<string, unknown>)
            : {},
        execution: tool.execution,
        deviceId: typeof tool.device_id === "string" ? tool.device_id : "",
        status: typeof tool.status === "string" ? tool.status : "running",
        receipt: typeof tool.receipt === "string" ? tool.receipt : null,
      },
    ];
  });
}

function parseStep(event: AgentEvent) {
  const payload = event.payload;
  if (
    event.event_type !== "activity.step" ||
    !event.run_id ||
    typeof payload.monitor_id !== "string" ||
    typeof payload.subject !== "string" ||
    !isPhase(payload.phase) ||
    typeof payload.title !== "string" ||
    typeof payload.detail !== "string" ||
    !isThreadStatus(payload.thread_status)
  ) {
    return null;
  }
  const kind: AgentActivityStepKind =
    typeof payload.kind === "string" &&
    STEP_KINDS.has(payload.kind as AgentActivityStepKind)
      ? (payload.kind as AgentActivityStepKind)
      : "narrative";
  const stepIndex =
    typeof payload.step_index === "number" ? payload.step_index : null;
  const toolStatusValue = payload.tool_status;
  const toolStatus: ToolStatus | null = isToolStatus(toolStatusValue)
    ? toolStatusValue
    : null;
  return {
    event,
    runId: event.run_id,
    monitorId: payload.monitor_id,
    subject: payload.subject,
    scenario: typeof payload.scenario === "string" ? payload.scenario : null,
    phase: payload.phase,
    kind,
    stepIndex,
    clock: typeof payload.clock === "string" ? payload.clock : null,
    title: payload.title,
    detail: payload.detail,
    evidence: stringList(payload.evidence),
    checks: stringList(payload.checks),
    plan: stringList(payload.plan),
    tools: parseTools(payload.tools),
    toolStatus,
    threadStatus: payload.thread_status,
  };
}

export function buildLatestAgentActivity(
  events: AgentEvent[],
): AgentActivityThreadView | null {
  return buildAgentActivities(events).at(-1) ?? null;
}

export function buildAgentActivities(
  events: AgentEvent[],
): AgentActivityThreadView[] {
  const parsed = events.flatMap((event) => {
    const step = parseStep(event);
    return step ? [step] : [];
  });
  const grouped = new Map<string, typeof parsed>();
  parsed.forEach((step) => {
    const current = grouped.get(step.runId) ?? [];
    current.push(step);
    grouped.set(step.runId, current);
  });

  return [...grouped.values()].flatMap((threadSteps) => {
    const firstStep = threadSteps[0];
    const lastStep = threadSteps.at(-1);
    if (!firstStep || !lastStep) return [];

    // 同一步骤可能先推“进行中”再推“已完成”，按 step_index 去重，后到的覆盖先到的。
    const order: number[] = [];
    const latestByIndex = new Map<number, (typeof threadSteps)[number]>();
    threadSteps.forEach((step, position) => {
      const key = step.stepIndex ?? -(position + 1);
      if (!latestByIndex.has(key)) order.push(key);
      latestByIndex.set(key, step);
    });
    const steps = order.map((key) => latestByIndex.get(key)!);

    return [
      {
        runId: firstStep.runId,
        monitorId: firstStep.monitorId,
        subject: firstStep.subject,
        scenario: firstStep.scenario,
        status: lastStep.threadStatus,
        steps: steps.map((step, index) => ({
          id: step.event.event_id,
          phase: step.phase,
          phaseLabel: PHASE_LABELS[step.phase],
          kind: step.kind,
          clock: step.clock,
          title: step.title,
          detail: step.detail,
          evidence: step.evidence,
          checks: step.checks,
          plan: step.plan,
          tools: step.tools,
          toolStatus: step.toolStatus,
          timestamp: step.event.timestamp,
          status:
            (lastStep.threadStatus === "failed" ||
              lastStep.threadStatus === "stopped") &&
            index === steps.length - 1
              ? ("failed" as const)
              : lastStep.threadStatus === "completed" ||
                  index < steps.length - 1
                ? ("succeeded" as const)
                : ("active" as const),
        })),
      },
    ];
  });
}
