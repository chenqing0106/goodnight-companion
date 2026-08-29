import createClient from "openapi-fetch";

import type { paths } from "./schema";
import type {
  AgentSnapshot,
  AgentWorldState,
  AgentEvent,
  AutomationStatus,
  MockActivityScenario,
  MockActivityStartResult,
  MockActivityStatus,
  MockActivityStopResult,
  RunStopResult,
  SensorReading,
  WorkflowResult,
} from "./types";

const client = createClient<paths>({ baseUrl: "" });

function requestError(operation: string, response: Response, detail: unknown) {
  const suffix = detail ? `: ${JSON.stringify(detail)}` : "";
  return new Error(`${operation}失败，HTTP ${response.status}${suffix}`);
}

function isWorldState(value: unknown): value is AgentWorldState {
  if (!value || typeof value !== "object") return false;
  const state = value as Record<string, unknown>;
  return (
    typeof state.person_motion === "string" &&
    typeof state.stable_for_seconds === "number" &&
    typeof state.phone_location === "string" &&
    typeof state.sleep_window === "boolean" &&
    typeof state.vitals_signal_state === "string" &&
    typeof state.vitals_valid_streak === "number" &&
    (typeof state.vitals_reason === "string" || state.vitals_reason === null) &&
    (typeof state.rgb_indicator_mode === "number" ||
      state.rgb_indicator_mode === null)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isAgentEvent(value: unknown): value is AgentEvent {
  if (!isRecord(value)) return false;
  return (
    typeof value.event_id === "string" &&
    typeof value.event_type === "string" &&
    typeof value.timestamp === "string" &&
    (typeof value.run_id === "string" || value.run_id === null) &&
    (typeof value.action_id === "string" || value.action_id === null) &&
    (typeof value.command_id === "string" || value.command_id === null) &&
    isRecord(value.payload)
  );
}

function isAutomationStatus(value: unknown): value is AutomationStatus {
  if (!isRecord(value)) return false;
  return (
    typeof value.enabled === "boolean" &&
    (typeof value.rule === "string" || value.rule === null) &&
    (typeof value.required_samples === "number" ||
      value.required_samples === null)
  );
}

const SENSOR_NAMES = new Set([
  "temp",
  "humidity",
  "light",
  "heart_rate",
  "spo2",
]);

function isSensorReading(value: unknown): value is SensorReading {
  if (!value || typeof value !== "object") return false;
  const reading = value as Record<string, unknown>;
  return (
    typeof reading.device_id === "string" &&
    typeof reading.sensor === "string" &&
    SENSOR_NAMES.has(reading.sensor) &&
    typeof reading.value === "number" &&
    typeof reading.unit === "string" &&
    typeof reading.valid === "boolean" &&
    typeof reading.ts_ms === "number" &&
    (typeof reading.error === "string" || reading.error === null) &&
    typeof reading.received_at === "string"
  );
}

export async function getSensorReadings(
  deviceId: string,
  signal?: AbortSignal,
): Promise<SensorReading[]> {
  const response = await fetch(
    `/api/devices/${encodeURIComponent(deviceId)}/sensors`,
    { cache: "no-store", signal },
  );
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw requestError("读取传感器状态", response, payload);
  }
  if (!Array.isArray(payload) || !payload.every(isSensorReading)) {
    throw new Error("传感器响应格式不正确");
  }
  return payload;
}

export async function getRecentAgentEvents(limit = 100): Promise<AgentEvent[]> {
  const { data, error, response } = await client.GET("/api/events/recent", {
    params: { query: { limit } },
  });
  if (error || !data) {
    throw requestError("读取 Agent 时间线", response, error);
  }
  if (!data.every(isAgentEvent)) {
    throw new Error("Agent 时间线响应格式不正确");
  }
  return data;
}

export async function getAutomationStatus(): Promise<AutomationStatus> {
  const { data, error, response } = await client.GET("/api/automation");
  if (error || !isAutomationStatus(data)) {
    throw requestError("读取自动感知状态", response, error ?? data);
  }
  return data;
}

export function parseAgentEvent(value: unknown): AgentEvent | null {
  return isAgentEvent(value) ? value : null;
}

export interface StartScenarioOptions {
  scenario?: MockActivityScenario;
  speed?: number;
  stepDelayMs?: number;
}

export async function startMockActivity(
  options: StartScenarioOptions = {},
): Promise<MockActivityStartResult> {
  const { data, error, response } = await client.POST(
    "/api/debug/mock-activity",
    {
      body: {
        scenario: options.scenario ?? "temperature_cooling",
        step_delay_ms: options.stepDelayMs ?? 2200,
        speed: options.speed ?? 1,
      },
    },
  );
  if (error || !data) {
    throw requestError("启动连续思考演示", response, error);
  }
  return data;
}

export async function stopMockActivity(): Promise<MockActivityStopResult> {
  const { data, error, response } = await client.POST(
    "/api/debug/mock-activity/stop",
  );
  if (error || !data) {
    throw requestError("停止场景演示", response, error);
  }
  return data;
}

export async function getMockActivityStatus(): Promise<MockActivityStatus> {
  const { data, error, response } = await client.GET("/api/debug/mock-activity");
  if (error || !data) {
    throw requestError("读取场景状态", response, error);
  }
  return data;
}

export async function getAgentSnapshot(): Promise<AgentSnapshot> {
  const [stateResult, devicesResult, actionsResult] = await Promise.all([
    client.GET("/api/state"),
    client.GET("/api/devices"),
    client.GET("/api/actions"),
  ]);

  if (stateResult.error || !isWorldState(stateResult.data)) {
    throw requestError("读取环境状态", stateResult.response, stateResult.error);
  }
  if (!devicesResult.response.ok) {
    throw requestError(
      "读取设备状态",
      devicesResult.response,
      undefined,
    );
  }
  if (!actionsResult.response.ok) {
    throw requestError(
      "读取动作记录",
      actionsResult.response,
      undefined,
    );
  }
  if (!devicesResult.data || !actionsResult.data) {
    throw new Error("后端响应缺少设备或动作数据");
  }

  return {
    world: stateResult.data,
    devices: devicesResult.data,
    actions: actionsResult.data,
  };
}

export async function startPickupDemo(): Promise<WorkflowResult> {
  const { data, error, response } = await client.POST(
    "/api/debug/observations",
    {
      body: {
        source: "nextjs_f1_demo",
        confidence: 1,
        facts: {
          person_in_bed: true,
          person_motion: "still",
          stable_for_seconds: 20 * 60,
          inferred_sleep_state: "asleep",
          person_in_restricted_zone: false,
          phone_location: "operation_zone",
          phone_being_used: false,
          light_on: true,
          sleep_window: true,
        },
      },
    },
  );

  if (error || !data) {
    throw requestError("启动场景 1", response, error);
  }
  return data;
}

export async function restoreNormalTemperatureState(): Promise<WorkflowResult> {
  const { data, error, response } = await client.POST(
    "/api/debug/observations",
    {
      body: {
        source: "nextjs_temperature_followup",
        confidence: 1,
        facts: {
          vitals_signal_state: "stable",
          vitals_valid_streak: 3,
          vitals_reason: "temperature_demo_restore_normal",
          rgb_indicator_mode: 3,
        },
      },
    },
  );

  if (error || !data) {
    throw requestError("恢复正常温度状态", response, error);
  }
  return data;
}

export async function stopAgentRun(runId: string): Promise<RunStopResult> {
  const { data, error, response } = await client.POST(
    "/api/runs/{run_id}/stop",
    { params: { path: { run_id: runId } } },
  );

  if (error || !data) {
    throw requestError("停止流程", response, error);
  }
  return data;
}
