import type { AgentActionStatus } from "./api/types";

export type CompanionDataMode = "live" | "preview";

interface CompanionConfig {
  pageDataMode: {
    tonight: CompanionDataMode;
    devices: CompanionDataMode;
    memory: CompanionDataMode;
    profile: CompanionDataMode;
  };
  sensors: {
    deviceId: string;
    pollIntervalMs: number;
  };
  preview: {
    actionStatus: AgentActionStatus | null;
    progress: number | null;
    sleepState: string;
    phoneLocation: string;
    lightOn: boolean | null;
  };
}

// Each page can independently use the real backend or the legacy UI fixtures.
export const COMPANION_CONFIG: CompanionConfig = {
  pageDataMode: {
    tonight: "live",
    devices: "preview",
    memory: "preview",
    profile: "preview",
  },
  sensors: {
    deviceId: "env-s3-01",
    pollIntervalMs: 1000,
  },
  preview: {
    actionStatus: "succeeded",
    progress: 100,
    sleepState: "asleep",
    phoneLocation: "operation_zone",
    lightOn: false,
  },
};
