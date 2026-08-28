import type { AgentEvent } from "./types";

const EVENT_TYPES = [
  "observation.updated",
  "decision.created",
  "decision.skipped",
  "action.created",
  "action.status_changed",
  "action.confirmation_required",
  "action.started",
  "action.progress",
  "action.stop_requested",
  "action.stopped",
  "action.succeeded",
  "action.failed",
  "action.skipped",
  "run.stop_requested",
  "run.stopped",
  "safety.checked",
  "tool.called",
  "device.registry_synced",
  "device.registry_failed",
] as const;

interface EventCallbacks {
  onOpen: () => void;
  onEvent: (event: AgentEvent) => void;
  onError: () => void;
}

export function subscribeAgentEvents(callbacks: EventCallbacks) {
  const source = new EventSource("/agent-events");
  const handlers = EVENT_TYPES.map((eventType) => {
    const handler = (message: MessageEvent<string>) => {
      try {
        callbacks.onEvent(JSON.parse(message.data) as AgentEvent);
      } catch {
        callbacks.onError();
      }
    };
    source.addEventListener(eventType, handler as EventListener);
    return [eventType, handler] as const;
  });

  source.onopen = callbacks.onOpen;
  source.onerror = callbacks.onError;

  return () => {
    for (const [eventType, handler] of handlers) {
      source.removeEventListener(eventType, handler as EventListener);
    }
    source.close();
  };
}
