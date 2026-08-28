"use client";

import { useEffect, useState } from "react";

import { getSensorReadings } from "../api/client";
import type { SensorReading } from "../api/types";

interface SensorReadingsState {
  readings: SensorReading[];
  error: string | null;
  isLoading: boolean;
  lastPolledAt: string | null;
}

const INITIAL_STATE: SensorReadingsState = {
  readings: [],
  error: null,
  isLoading: true,
  lastPolledAt: null,
};

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "读取传感器时发生未知错误";
}

export function useSensorReadings({
  deviceId,
  enabled,
  intervalMs,
}: {
  deviceId: string;
  enabled: boolean;
  intervalMs: number;
}) {
  const [state, setState] = useState<SensorReadingsState>(INITIAL_STATE);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;

    const poll = async () => {
      controller = new AbortController();
      try {
        const readings = await getSensorReadings(deviceId, controller.signal);
        if (!cancelled) {
          setState({
            readings,
            error: null,
            isLoading: false,
            lastPolledAt: new Date().toISOString(),
          });
        }
      } catch (error) {
        if (!cancelled && !(error instanceof DOMException && error.name === "AbortError")) {
          setState((current) => ({
            ...current,
            error: errorMessage(error),
            isLoading: false,
            lastPolledAt: new Date().toISOString(),
          }));
        }
      } finally {
        if (!cancelled) timer = setTimeout(poll, intervalMs);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, [deviceId, enabled, intervalMs]);

  return state;
}
