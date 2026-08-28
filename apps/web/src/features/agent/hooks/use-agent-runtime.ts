"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

import {
  getAgentSnapshot,
  startPickupDemo,
  stopAgentRun,
} from "../api/client";
import { subscribeAgentEvents } from "../api/events";
import {
  agentRuntimeReducer,
  getCurrentAction,
  initialAgentRuntimeState,
  mapActionPhase,
} from "../model/reducer";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "发生未知错误";
}

export function useAgentRuntime() {
  const [state, dispatch] = useReducer(
    agentRuntimeReducer,
    initialAgentRuntimeState,
  );
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const snapshot = await getAgentSnapshot();
      dispatch({ type: "snapshot", snapshot });
    } catch (error) {
      dispatch({ type: "error", message: errorMessage(error) });
    }
  }, []);

  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      void refresh();
    }, 80);
  }, [refresh]);

  useEffect(() => {
    void refresh();
    const unsubscribe = subscribeAgentEvents({
      onOpen: () => {
        dispatch({ type: "connection", status: "connected" });
        scheduleRefresh();
      },
      onEvent: (event) => {
        dispatch({ type: "event", event });
        if (event.event_type !== "action.progress") scheduleRefresh();
      },
      onError: () => {
        dispatch({ type: "connection", status: "disconnected" });
      },
    });
    return () => {
      unsubscribe();
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [refresh, scheduleRefresh]);

  const runPickupDemo = useCallback(async () => {
    dispatch({ type: "starting", active: true });
    dispatch({ type: "error", message: null });
    try {
      await startPickupDemo();
      await refresh();
    } catch (error) {
      dispatch({ type: "error", message: errorMessage(error) });
    } finally {
      dispatch({ type: "starting", active: false });
    }
  }, [refresh]);

  const currentAction = getCurrentAction(state.snapshot);

  const stopCurrentRun = useCallback(async () => {
    if (!currentAction?.run_id) return;
    dispatch({ type: "stopping", active: true });
    dispatch({ type: "error", message: null });
    try {
      await stopAgentRun(currentAction.run_id);
      await refresh();
    } catch (error) {
      dispatch({ type: "error", message: errorMessage(error) });
    } finally {
      dispatch({ type: "stopping", active: false });
    }
  }, [currentAction, refresh]);

  return {
    state,
    currentAction,
    phase: mapActionPhase(currentAction),
    refresh,
    runPickupDemo,
    stopCurrentRun,
  };
}
