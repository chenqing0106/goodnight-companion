"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";

import styles from "./page.module.css";

type SensorName = "temp" | "humidity" | "light" | "heart_rate" | "spo2";
type Availability = "unknown" | "online" | "offline";
type LightCapability = "set_rgb_indicator" | "set_led_mode";

interface SensorReading {
  device_id: string;
  sensor: SensorName;
  value: number;
  unit: string;
  valid: boolean;
  error: string | null;
  received_at: string;
}

interface DeviceRecord {
  device_id: string;
  availability: Availability;
  capabilities: string[];
}

interface HardwareState {
  rgb_indicator_mode: number | null;
  led_mode: number | null;
}

interface WorkflowResult {
  actions: Array<{
    status: string;
    reason: string | null;
  }>;
}

interface Feedback {
  tone: "success" | "error";
  message: string;
}

const SENSOR_ITEMS: Array<{
  sensor: SensorName;
  label: string;
  shortLabel: string;
}> = [
  { sensor: "temp", label: "环境温度", shortLabel: "TEMP" },
  { sensor: "humidity", label: "相对湿度", shortLabel: "HUM" },
  { sensor: "light", label: "环境光线", shortLabel: "LIGHT" },
  { sensor: "heart_rate", label: "心率", shortLabel: "BPM" },
  { sensor: "spo2", label: "血氧", shortLabel: "SPO₂" },
];

const RGB_MODES = [
  { mode: 0, label: "熄灭", color: "#38434d" },
  { mode: 1, label: "红色", color: "#f06a5f" },
  { mode: 2, label: "绿色", color: "#58c79a" },
  { mode: 3, label: "蓝色", color: "#55a9e8" },
] as const;

const LED_MODES = [
  { mode: 0, label: "熄灭" },
  { mode: 7, label: "模式 7" },
  { mode: 8, label: "模式 8" },
  { mode: 9, label: "模式 9" },
] as const;

const RAIL_COLORS = [
  "#f06a5f",
  "#f2b56b",
  "#f0df75",
  "#58c79a",
  "#4bc7c7",
  "#55a9e8",
  "#8f83df",
  "#d977b8",
  "#f06a5f",
  "#f2b56b",
];

function detailFromPayload(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const detail = (payload as Record<string, unknown>).detail;
  return typeof detail === "string" ? detail : null;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(detailFromPayload(payload) ?? `请求失败，HTTP ${response.status}`);
  }
  return payload as T;
}

function displayValue(reading: SensorReading | undefined) {
  if (!reading?.valid) return "—";
  return Number.isInteger(reading.value)
    ? String(reading.value)
    : reading.value.toFixed(1);
}

function railDotStyle(index: number, mode: number | null): CSSProperties {
  if (!mode) return { backgroundColor: "#26323b", opacity: 0.45 };
  if (mode === 7) return { backgroundColor: "#f2b56b" };
  if (mode === 8) return { backgroundColor: "#55a9e8" };
  if (mode === 9) {
    return { backgroundColor: RAIL_COLORS[index] };
  }
  return { backgroundColor: "#4bc7c7" };
}

export default function AdminPage() {
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [availability, setAvailability] = useState<Availability>("unknown");
  const [readings, setReadings] = useState<SensorReading[]>([]);
  const [hardware, setHardware] = useState<HardwareState>({
    rgb_indicator_mode: null,
    led_mode: null,
  });
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [pending, setPending] = useState<LightCapability | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const [devices, state] = await Promise.all([
          requestJson<DeviceRecord[]>("/api/devices"),
          requestJson<HardwareState>("/api/state"),
        ]);
        if (disposed) return;

        const device =
          devices.find((item) => item.capabilities.includes("set_led_mode")) ??
          devices[0];
        setHardware(state);
        setDeviceId(device?.device_id ?? null);
        setAvailability(device?.availability ?? "unknown");

        if (device) {
          const sensorResponse = await requestJson<SensorReading[]>(
            `/api/devices/${encodeURIComponent(device.device_id)}/sensors`,
          );
          if (!disposed) setReadings(sensorResponse);
        }

        if (!disposed) {
          setConnectionError(null);
          setLastSyncedAt(new Date());
        }
      } catch (error) {
        if (!disposed) {
          setConnectionError(
            error instanceof Error ? error.message : "无法读取后端状态",
          );
        }
      } finally {
        if (!disposed) {
          setLoading(false);
          timer = setTimeout(poll, 1000);
        }
      }
    }

    void poll();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  async function controlLight(capability: LightCapability, mode: number) {
    if (!deviceId || pending) return;
    setPending(capability);
    setFeedback(null);

    try {
      const result = await requestJson<WorkflowResult>(
        `/api/devices/${encodeURIComponent(deviceId)}/control`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ capability, mode }),
        },
      );
      const action = result.actions[0];
      if (!action || action.status !== "succeeded") {
        throw new Error(action?.reason ?? "硬件没有确认这次操作");
      }

      const label =
        capability === "set_rgb_indicator"
          ? RGB_MODES.find((item) => item.mode === mode)?.label
          : LED_MODES.find((item) => item.mode === mode)?.label;
      setHardware((current) => ({
        ...current,
        ...(capability === "set_rgb_indicator"
          ? { rgb_indicator_mode: mode }
          : { led_mode: mode }),
      }));
      setFeedback({ tone: "success", message: `已切换为${label}` });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "灯光控制失败",
      });
    } finally {
      setPending(null);
    }
  }

  const readingByName = new Map(readings.map((reading) => [reading.sensor, reading]));
  const controlsDisabled = availability !== "online" || pending !== null;
  const currentLedLabel =
    LED_MODES.find((item) => item.mode === hardware.led_mode)?.label ?? "等待状态";

  return (
    <main className={styles.console}>
      <div className={styles.shell}>
        <header className={styles.header}>
          <div>
            <div className={styles.kicker}>GOODNIGHT / CONTROL</div>
            <h1>灯光与感知</h1>
            <p>查看实时数据，直接测试两组灯光。</p>
          </div>
          <div className={styles.deviceStatus} data-status={availability}>
            <span className={styles.statusDot} />
            <div>
              <strong>{deviceId ?? "等待设备"}</strong>
              <span>
                {availability === "online"
                  ? "设备在线"
                  : availability === "offline"
                    ? "设备离线"
                    : "状态未知"}
              </span>
            </div>
          </div>
        </header>

        <section className={styles.lightRail} aria-label={`当前灯带：${currentLedLabel}`}>
          <div className={styles.railMeta}>
            <span>WS2812B / 10 PIXELS</span>
            <strong>{currentLedLabel}</strong>
          </div>
          <div className={styles.railDots}>
            {Array.from({ length: 10 }, (_, index) => (
              <i
                className={`${styles.railDot} ${
                  hardware.led_mode === 7 || hardware.led_mode === 8
                    ? styles.breathing
                    : ""
                }`}
                key={index}
                style={{
                  ...railDotStyle(index, hardware.led_mode),
                  animationDelay: `${index * 80}ms`,
                }}
              />
            ))}
          </div>
        </section>

        {connectionError ? (
          <div className={styles.connectionError} role="status">
            <strong>后端连接异常</strong>
            <span>{connectionError}</span>
          </div>
        ) : null}

        <div className={styles.contentGrid}>
          <section className={styles.panel}>
            <div className={styles.sectionHeading}>
              <div>
                <span>LIVE INPUT</span>
                <h2>传感器数据</h2>
              </div>
              <small>{loading ? "连接中" : "每秒刷新"}</small>
            </div>

            <div className={styles.sensorGrid}>
              {SENSOR_ITEMS.map((item) => {
                const reading = readingByName.get(item.sensor);
                return (
                  <article className={styles.sensorCard} key={item.sensor}>
                    <div className={styles.sensorLabel}>
                      <span>{item.shortLabel}</span>
                      <i data-valid={reading?.valid ?? false} />
                    </div>
                    <strong>{displayValue(reading)}</strong>
                    <div className={styles.sensorFooter}>
                      <span>{item.label}</span>
                      <small>{reading?.valid ? reading.unit : reading?.error ?? "暂无数据"}</small>
                    </div>
                  </article>
                );
              })}
            </div>

            <div className={styles.syncLine}>
              <span>最近同步</span>
              <time>{lastSyncedAt?.toLocaleTimeString("zh-CN") ?? "—"}</time>
            </div>
          </section>

          <section className={`${styles.panel} ${styles.controlPanel}`}>
            <div className={styles.sectionHeading}>
              <div>
                <span>HARDWARE OUTPUT</span>
                <h2>灯光控制</h2>
              </div>
              <small>{pending ? "等待硬件回执" : "手动控制"}</small>
            </div>

            <div className={styles.controlGroup}>
              <div className={styles.controlTitle}>
                <div>
                  <h3>RGB 指示灯</h3>
                  <p>三色状态灯</p>
                </div>
                <span>模式 {hardware.rgb_indicator_mode ?? "—"}</span>
              </div>
              <div className={styles.rgbOptions}>
                {RGB_MODES.map((item) => (
                  <button
                    aria-pressed={hardware.rgb_indicator_mode === item.mode}
                    className={styles.rgbButton}
                    disabled={controlsDisabled}
                    key={item.mode}
                    onClick={() => void controlLight("set_rgb_indicator", item.mode)}
                    type="button"
                  >
                    <i style={{ backgroundColor: item.color }} />
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className={styles.controlGroup}>
              <div className={styles.controlTitle}>
                <div>
                  <h3>灯带模式</h3>
                  <p>10 颗 WS2812B</p>
                </div>
                <span>模式 {hardware.led_mode ?? "—"}</span>
              </div>
              <div className={styles.ledOptions}>
                {LED_MODES.map((item) => (
                  <button
                    aria-pressed={hardware.led_mode === item.mode}
                    disabled={controlsDisabled}
                    key={item.mode}
                    onClick={() => void controlLight("set_led_mode", item.mode)}
                    type="button"
                  >
                    <span>{String(item.mode).padStart(2, "0")}</span>
                    <strong>{item.label}</strong>
                  </button>
                ))}
              </div>
            </div>

            {feedback ? (
              <div className={styles.feedback} data-tone={feedback.tone} role="status">
                {feedback.message}
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </main>
  );
}
