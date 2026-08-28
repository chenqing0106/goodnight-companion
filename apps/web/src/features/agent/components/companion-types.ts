import type { useAgentRuntime } from "../hooks/use-agent-runtime";

export type AgentRuntime = ReturnType<typeof useAgentRuntime>;
export type TabId = "tonight" | "devices" | "memory" | "profile";
