import type { AgentRuntime } from "../components/companion-types";
import type { CompanionDataMode } from "../companion-config";

export interface MemoryItem {
  id: number;
  title: string;
  body: string;
  source: string;
}

export type MemoryRuntime =
  | {
      status: "unavailable";
      items: [];
    }
  | {
      status: "ready";
      items: MemoryItem[];
      add: () => void;
      edit: (id: number, body: string) => void;
      remove: (id: number) => void;
    };

export type ProactivityMode = "安静" | "平衡" | "积极";

export type ProfileRuntime =
  | {
      status: "unavailable";
    }
  | {
      status: "ready";
      mode: ProactivityMode;
      cameraEnabled: boolean;
      setMode: (mode: ProactivityMode) => void;
      toggleCamera: () => void;
      showSafetyStatus: () => void;
      showActivityLog: () => void;
    };

export type CompanionRuntime = AgentRuntime & {
  dataMode: CompanionDataMode;
  memory: MemoryRuntime;
  profile: ProfileRuntime;
  notice: string | null;
};
