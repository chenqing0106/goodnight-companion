"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  AgentAction,
  AgentActionStatus,
  AgentSnapshot,
} from "../api/types";
import { COMPANION_CONFIG } from "../companion-config";
import {
  PREVIEW_DEVICES,
  PREVIEW_MEMORIES,
  PREVIEW_PROFILE,
} from "../data/preview-fixtures";
import {
  getCurrentAction,
  mapActionPhase,
  type AgentRuntimeState,
} from "../model/reducer";
import type {
  CompanionRuntime,
  MemoryItem,
  ProactivityMode,
} from "../model/companion-runtime";

const PREVIEW_ACTION_ID = "preview-pickup-action";
const PREVIEW_RUN_ID = "preview-sleep-run";

function createPreviewAction(status: AgentActionStatus): AgentAction {
  const now = new Date().toISOString();

  return {
    action_id: PREVIEW_ACTION_ID,
    run_id: PREVIEW_RUN_ID,
    capability: "pickup_phone",
    device_id: "bedside-arm",
    parameters: { target: "phone-dock" },
    status,
    reason: "确认稳定入睡后，将手机收回安全位置并关闭床头灯。",
    created_at: now,
    updated_at: now,
  };
}

function createPreviewSnapshot(
  status: AgentActionStatus | null,
): AgentSnapshot {
  const now = new Date().toISOString();
  const action = status ? createPreviewAction(status) : null;
  const isActive =
    status !== null &&
    !["succeeded", "failed", "stopped", "skipped"].includes(status);

  return {
    world: {
      person_in_bed: true,
      person_motion: "still",
      stable_for_seconds: 1260,
      inferred_sleep_state: COMPANION_CONFIG.preview.sleepState,
      person_in_restricted_zone: false,
      phone_location: COMPANION_CONFIG.preview.phoneLocation,
      phone_being_used: false,
      light_on: COMPANION_CONFIG.preview.lightOn,
      sleep_window: true,
      vitals_signal_state: "stable",
      vitals_valid_streak: 3,
      vitals_reason: "heart_rate_and_spo2_valid",
      rgb_indicator_mode: 2,
      device_states: {
        床头相机: "在线",
        六轴机械臂: "可执行",
        床头灯: "在线",
        床垫压力传感器: "在线",
        角色声音: "可播放",
        拉被子能力: "未开放",
      },
      device_capabilities: {
        六轴机械臂: ["pickup_phone", "return_phone"],
        床头灯: ["turn_on", "turn_off"],
      },
      active_action_id: isActive ? PREVIEW_ACTION_ID : null,
      last_observation_at: now,
      updated_at: now,
    },
    devices: PREVIEW_DEVICES.map((device) => ({ ...device, updated_at: now })),
    actions: action ? [action] : [],
  };
}

function createInitialState(): AgentRuntimeState {
  return {
    connection: "connected",
    snapshot: createPreviewSnapshot(COMPANION_CONFIG.preview.actionStatus),
    latestEvent: null,
    events: [],
    automation: {
      enabled: true,
      rule: "vitals_signal_indicator",
      required_samples: 3,
    },
    traceError: null,
    progress: COMPANION_CONFIG.preview.progress,
    error: null,
    isStarting: false,
    isStartingActivity: false,
    isStopping: false,
  };
}

export function usePreviewRuntime(): CompanionRuntime {
  const [state, setState] = useState<AgentRuntimeState>(createInitialState);
  const [memories, setMemories] = useState<MemoryItem[]>(() =>
    PREVIEW_MEMORIES.map((memory) => ({ ...memory })),
  );
  const [mode, setModeState] = useState<ProactivityMode>(PREVIEW_PROFILE.mode);
  const [cameraEnabled, setCameraEnabled] = useState(
    PREVIEW_PROFILE.cameraEnabled,
  );
  const [notice, setNotice] = useState<string | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showNotice = useCallback((message: string) => {
    setNotice(message);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => {
      setNotice(null);
      noticeTimer.current = null;
    }, 2200);
  }, []);

  useEffect(
    () => () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    },
    [],
  );

  const refresh = useCallback(async () => {
    setState(createInitialState());
  }, []);

  const runPickupDemo = useCallback(async () => {
    setState((current) => ({
      ...current,
      snapshot: createPreviewSnapshot("executing"),
      progress: 48,
      error: null,
      isStarting: false,
      isStopping: false,
    }));
    showNotice("已开始执行，随时可以停止");
  }, [showNotice]);

  const runMockActivityDemo = useCallback(async () => {
    showNotice("连续思考演示需要连接 Agent 后端");
  }, [showNotice]);

  const restoreNormalState = useCallback(async () => {
    showNotice("恢复正常状态需要连接 Agent 后端");
  }, [showNotice]);

  const stopCurrentRun = useCallback(async () => {
    setState((current) => ({
      ...current,
      snapshot: createPreviewSnapshot("stopped"),
      progress: current.progress,
      error: null,
      isStarting: false,
      isStopping: false,
    }));
    showNotice("已停止，机械臂正在安全复位");
  }, [showNotice]);

  const currentAction = useMemo(
    () => getCurrentAction(state.snapshot),
    [state.snapshot],
  );

  const addMemory = useCallback(() => {
    setMemories((current) => [
      ...current,
      {
        id: Date.now(),
        title: "新增的睡眠偏好",
        body: "点击编辑，把它改成你希望我记住的内容。",
        source: "由你刚刚手动添加",
      },
    ]);
    showNotice("已添加一条可编辑记忆");
  }, [showNotice]);

  const editMemory = useCallback(
    (id: number, body: string) => {
      setMemories((current) =>
        current.map((memory) =>
          memory.id === id ? { ...memory, body } : memory,
        ),
      );
      showNotice("记忆已更新");
    },
    [showNotice],
  );

  const removeMemory = useCallback(
    (id: number) => {
      setMemories((current) =>
        current.filter((memory) => memory.id !== id),
      );
      showNotice("这条记忆已删除");
    },
    [showNotice],
  );

  const setMode = useCallback(
    (nextMode: ProactivityMode) => {
      setModeState(nextMode);
      showNotice(`主动程度已设为${nextMode}`);
    },
    [showNotice],
  );

  const toggleCamera = useCallback(() => {
    setCameraEnabled((enabled) => {
      showNotice(enabled ? "摄像头已关闭" : "摄像头已开启");
      return !enabled;
    });
  }, [showNotice]);

  return {
    state,
    currentAction,
    phase: mapActionPhase(currentAction),
    refresh,
    runPickupDemo,
    runMockActivityDemo,
    restoreNormalState,
    stopCurrentRun,
    dataMode: "preview",
    memory: {
      status: "ready",
      items: memories,
      add: addMemory,
      edit: editMemory,
      remove: removeMemory,
    },
    profile: {
      status: "ready",
      mode,
      cameraEnabled,
      setMode,
      toggleCamera,
      showSafetyStatus: () =>
        showNotice("所有物理动作均已启用急停保护"),
      showActivityLog: () =>
        showNotice("最近一次：昨晚 00:36 收好手机并关灯"),
    },
    notice,
  };
}
