import type { AgentEvent } from "../api/types";

export type AgentActivityPhase =
  | "observation"
  | "evaluation"
  | "conclusion"
  | "plan"
  | "safety"
  | "action"
  | "verification";

export interface AgentActivityStepView {
  id: string;
  phase: AgentActivityPhase;
  phaseLabel: string;
  title: string;
  detail: string;
  evidence: string[];
  timestamp: string;
  status: "active" | "succeeded" | "failed";
}

export interface AgentActivityThreadView {
  runId: string;
  monitorId: string;
  subject: string;
  status: "running" | "completed" | "failed";
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

function isPhase(value: unknown): value is AgentActivityPhase {
  return typeof value === "string" && value in PHASE_LABELS;
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
    (payload.thread_status !== "running" &&
      payload.thread_status !== "completed" &&
      payload.thread_status !== "failed")
  ) {
    return null;
  }
  const evidence = Array.isArray(payload.evidence)
    ? payload.evidence.filter((item): item is string => typeof item === "string")
    : [];
  const threadStatus = payload.thread_status as
    | "running"
    | "completed"
    | "failed";
  return {
    event,
    runId: event.run_id,
    monitorId: payload.monitor_id,
    subject: payload.subject,
    phase: payload.phase,
    title: payload.title,
    detail: payload.detail,
    evidence,
    threadStatus,
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

    return [
      {
        runId: firstStep.runId,
        monitorId: firstStep.monitorId,
        subject: firstStep.subject,
        status: lastStep.threadStatus,
        steps: threadSteps.map((step, index) => ({
          id: step.event.event_id,
          phase: step.phase,
          phaseLabel: PHASE_LABELS[step.phase],
          title: step.title,
          detail: step.detail,
          evidence: step.evidence,
          timestamp: step.event.timestamp,
          status:
            lastStep.threadStatus === "failed" &&
            index === threadSteps.length - 1
              ? ("failed" as const)
              : lastStep.threadStatus === "completed" ||
                  index < threadSteps.length - 1
                ? ("succeeded" as const)
                : ("active" as const),
        })),
      },
    ];
  });
}
