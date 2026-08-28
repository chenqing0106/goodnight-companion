"use client";

import { useAgentRuntime } from "./use-agent-runtime";
import type {
  CompanionRuntime,
  MemoryRuntime,
  ProfileRuntime,
} from "../model/companion-runtime";

export const LIVE_MEMORY_RUNTIME: MemoryRuntime = {
  status: "unavailable",
  items: [],
};

export const LIVE_PROFILE_RUNTIME: ProfileRuntime = {
  status: "unavailable",
};

export function useLiveCompanionRuntime(): CompanionRuntime {
  const agentRuntime = useAgentRuntime();

  return {
    ...agentRuntime,
    dataMode: "live",
    memory: LIVE_MEMORY_RUNTIME,
    profile: LIVE_PROFILE_RUNTIME,
    notice: null,
  };
}
