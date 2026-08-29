import type {
  AgentAction,
  AgentActionStatus,
  AgentEvent,
  AgentSnapshot,
  AutomationStatus,
} from "../api/types";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";
export type AgentPhase =
  | "idle"
  | "preparing"
  | "waiting_confirmation"
  | "executing"
  | "verifying"
  | "complete"
  | "stopped"
  | "failed";

export interface AgentRuntimeState {
  connection: ConnectionStatus;
  snapshot: AgentSnapshot | null;
  latestEvent: AgentEvent | null;
  events: AgentEvent[];
  automation: AutomationStatus | null;
  traceError: string | null;
  progress: number | null;
  error: string | null;
  isStarting: boolean;
  isStartingActivity: boolean;
  isStopping: boolean;
}

export const initialAgentRuntimeState: AgentRuntimeState = {
  connection: "connecting",
  snapshot: null,
  latestEvent: null,
  events: [],
  automation: null,
  traceError: null,
  progress: null,
  error: null,
  isStarting: false,
  isStartingActivity: false,
  isStopping: false,
};

type RuntimeAction =
  | { type: "connection"; status: ConnectionStatus }
  | { type: "snapshot"; snapshot: AgentSnapshot }
  | { type: "event"; event: AgentEvent }
  | { type: "event_history"; events: AgentEvent[] }
  | { type: "automation"; status: AutomationStatus }
  | { type: "trace_error"; message: string | null }
  | { type: "starting"; active: boolean }
  | { type: "activity_starting"; active: boolean }
  | { type: "stopping"; active: boolean }
  | { type: "error"; message: string | null };

export function agentRuntimeReducer(
  state: AgentRuntimeState,
  action: RuntimeAction,
): AgentRuntimeState {
  switch (action.type) {
    case "connection":
      return { ...state, connection: action.status };
    case "snapshot":
      return { ...state, snapshot: action.snapshot, error: null };
    case "event": {
      const rawProgress = action.event.payload.progress;
      const progress =
        typeof rawProgress === "number"
          ? Math.round(Math.min(1, Math.max(0, rawProgress)) * 100)
          : state.progress;
      return {
        ...state,
        latestEvent: action.event,
        events: mergeEvents(state.events, [action.event]),
        progress,
      };
    }
    case "event_history":
      return {
        ...state,
        events: mergeEvents(state.events, action.events),
        latestEvent: latestEvent(state.latestEvent, action.events),
        traceError: null,
      };
    case "automation":
      return { ...state, automation: action.status, traceError: null };
    case "trace_error":
      return { ...state, traceError: action.message };
    case "starting":
      return { ...state, isStarting: action.active };
    case "activity_starting":
      return { ...state, isStartingActivity: action.active };
    case "stopping":
      return { ...state, isStopping: action.active };
    case "error":
      return { ...state, error: action.message };
  }
}

const MAX_EVENTS = 100;

function mergeEvents(current: AgentEvent[], incoming: AgentEvent[]) {
  const byId = new Map(current.map((event) => [event.event_id, event]));
  for (const event of incoming) byId.set(event.event_id, event);
  return [...byId.values()]
    .sort((left, right) => left.timestamp.localeCompare(right.timestamp))
    .slice(-MAX_EVENTS);
}

function latestEvent(current: AgentEvent | null, incoming: AgentEvent[]) {
  return incoming.reduce<AgentEvent | null>((latest, event) => {
    if (!latest || event.timestamp > latest.timestamp) return event;
    return latest;
  }, current);
}

export function getCurrentAction(snapshot: AgentSnapshot | null) {
  if (!snapshot?.actions.length) return null;
  const activeId = snapshot.world.active_action_id;
  if (activeId) {
    const active = snapshot.actions.find((item) => item.action_id === activeId);
    if (active) return active;
  }
  return [...snapshot.actions].sort((a, b) =>
    (b.updated_at ?? "").localeCompare(a.updated_at ?? ""),
  )[0];
}

export function mapActionPhase(action: AgentAction | null): AgentPhase {
  if (!action) return "idle";
  const phases: Record<AgentActionStatus, AgentPhase> = {
    pending: "preparing",
    evaluating: "preparing",
    checking: "preparing",
    waiting_confirmation: "waiting_confirmation",
    executing: "executing",
    verifying: "verifying",
    succeeded: "complete",
    failed: "failed",
    stopped: "stopped",
    skipped: "stopped",
  };
  return phases[action.status];
}
