import type { components } from "./schema";

export type AgentAction = components["schemas"]["Action"];
export type AgentActionStatus = components["schemas"]["ActionStatus"];
export type AgentDevice = components["schemas"]["DeviceRecord"];
export type WorkflowResult = components["schemas"]["WorkflowResult"];

// FastAPI currently exposes /api/state as an open dictionary. Keep the
// temporary hand-written shape beside the generated contract until the
// backend publishes WorldState as an explicit response model.
export interface AgentWorldState {
  person_in_bed: boolean | null;
  person_motion: string;
  stable_for_seconds: number;
  inferred_sleep_state: string;
  person_in_restricted_zone: boolean;
  phone_location: string;
  phone_being_used: boolean | null;
  light_on: boolean | null;
  sleep_window: boolean;
  device_states: Record<string, string>;
  device_capabilities: Record<string, string[]>;
  active_action_id: string | null;
  last_observation_at: string | null;
  updated_at: string;
}

export interface AgentEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  run_id: string | null;
  action_id: string | null;
  command_id: string | null;
  payload: Record<string, unknown>;
}

export interface AgentSnapshot {
  world: AgentWorldState;
  devices: AgentDevice[];
  actions: AgentAction[];
}
