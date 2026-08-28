import createClient from "openapi-fetch";

import type { paths } from "./schema";
import type {
  AgentAction,
  AgentSnapshot,
  AgentWorldState,
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
    typeof state.sleep_window === "boolean"
  );
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

export async function stopAgentAction(actionId: string): Promise<AgentAction> {
  const { data, error, response } = await client.POST(
    "/api/actions/{action_id}/stop",
    { params: { path: { action_id: actionId } } },
  );

  if (error || !data) {
    throw requestError("停止动作", response, error);
  }
  return data;
}
