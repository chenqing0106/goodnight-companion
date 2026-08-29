"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

import {
  getAutomationStatus,
  getAgentSnapshot,
  getRecentAgentEvents,
  restoreNormalTemperatureState,
  startMockActivity,
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

  const hydrateActivity = useCallback(async () => {
    const [eventsResult, automationResult] = await Promise.allSettled([
      getRecentAgentEvents(),
      getAutomationStatus(),
    ]);
    if (eventsResult.status === "fulfilled") {
      dispatch({ type: "event_history", events: eventsResult.value });
    }
    if (automationResult.status === "fulfilled") {
      dispatch({ type: "automation", status: automationResult.value });
    }
    const failure =
      eventsResult.status === "rejected"
        ? eventsResult.reason
        : automationResult.status === "rejected"
          ? automationResult.reason
          : null;
    dispatch({
      type: "trace_error",
      message: failure ? errorMessage(failure) : null,
    });
  }, []);

  useEffect(() => {
    void refresh();
    const unsubscribe = subscribeAgentEvents({
      onOpen: () => {
        dispatch({ type: "connection", status: "connected" });
        scheduleRefresh();
        void hydrateActivity();
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
  }, [hydrateActivity, refresh, scheduleRefresh]);

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

  const runMockActivityDemo = useCallback(async () => {
    dispatch({ type: "activity_starting", active: true });
    dispatch({ type: "trace_error", message: null });
    try {
      await startMockActivity();
      await hydrateActivity();
    } catch (error) {
      dispatch({ type: "trace_error", message: errorMessage(error) });
    } finally {
      dispatch({ type: "activity_starting", active: false });
    }
  }, [hydrateActivity]);

  const restoreNormalState = useCallback(async () => {
    dispatch({ type: "starting", active: true });
    dispatch({ type: "error", message: null });
    try {
      await restoreNormalTemperatureState();
      await Promise.all([refresh(), hydrateActivity()]);
    } catch (error) {
      dispatch({ type: "error", message: errorMessage(error) });
    } finally {
      dispatch({ type: "starting", active: false });
    }
  }, [hydrateActivity, refresh]);

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
    runMockActivityDemo,
    restoreNormalState,
    stopCurrentRun,
  };
}
