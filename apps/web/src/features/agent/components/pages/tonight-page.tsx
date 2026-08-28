import Image from "next/image";
import { useMemo, useState } from "react";

import type { SensorName, SensorReading } from "../../api/types";
import {
  COMPANION_CONFIG,
  type CompanionDataMode,
} from "../../companion-config";
import { createPreviewSensorReadings } from "../../data/preview-fixtures";
import { useSensorReadings } from "../../hooks/use-sensor-readings";
import type { AgentPhase } from "../../model/reducer";
import type { AgentRuntime } from "../companion-types";
import { cx, Icon, PageIntro } from "../shared/shared-ui";
import styles from "./tonight-page.module.css";

const PHASE_LABELS: Record<AgentPhase, string> = {
  idle: "等你决定",
  preparing: "正在准备",
  waiting_confirmation: "等待确认",
  executing: "安静执行",
  verifying: "正在确认",
  complete: "已经完成",
  stopped: "已经停止",
  failed: "执行失败",
};

const TERMINAL_STATUSES = new Set([
  "succeeded",
  "failed",
  "stopped",
  "skipped",
]);

const SENSOR_ITEMS: Array<{ sensor: SensorName; label: string }> = [
  { sensor: "temp", label: "温度" },
  { sensor: "humidity", label: "湿度" },
  { sensor: "light", label: "光照" },
  { sensor: "heart_rate", label: "心率" },
  { sensor: "spo2", label: "血氧" },
];

const SENSOR_ERROR_LABELS: Record<string, string> = {
  finger_not_detected: "未检测到手指",
  collecting_or_unstable: "采集中 / 信号不稳定",
  ESP_ERR_TIMEOUT: "读取超时",
  ESP_ERR_INVALID_STATE: "设备状态异常",
};

function sensorValue(reading: SensorReading) {
  if (!reading.valid) return "暂无有效值";
  const units: Record<string, string> = {
    C: "°C",
    "%RH": "%",
    adc_count: "ADC",
    bpm: "bpm",
    "%": "%",
  };
  return `${reading.value} ${units[reading.unit] ?? reading.unit}`;
}

function readingMeta(reading: SensorReading, isPreview: boolean) {
  if (!reading.valid) {
    return reading.error
      ? (SENSOR_ERROR_LABELS[reading.error] ?? reading.error)
      : "数据无效";
  }
  if (isPreview) return "模拟数据";

  const receivedAt = Date.parse(reading.received_at);
  if (!Number.isFinite(receivedAt)) return "接收时间未知";
  const ageSeconds = Math.max(0, Math.floor((Date.now() - receivedAt) / 1000));
  return ageSeconds < 3 ? "刚刚收到" : `${ageSeconds} 秒前收到`;
}

function sensorConnectionMessage(error: string) {
  if (error.includes("device has no sensor data source")) {
    return "当前后端没有启用 env_s3_mqtt，暂时无法读取硬件传感器。";
  }
  if (error.includes("device not found")) {
    return `没有找到设备 ${COMPANION_CONFIG.sensors.deviceId}。`;
  }
  return "传感器连接暂时不可用，页面会继续自动重试。";
}

export function TonightPage({
  runtime,
  dataMode,
}: {
  runtime: AgentRuntime;
  dataMode: CompanionDataMode;
}) {
  const {
    state,
    currentAction,
    phase,
    refresh,
    runPickupDemo,
    stopCurrentRun,
  } = runtime;
  const [showEvidence, setShowEvidence] = useState(false);
  const liveSensors = useSensorReadings({
    deviceId: COMPANION_CONFIG.sensors.deviceId,
    enabled: dataMode === "live",
    intervalMs: COMPANION_CONFIG.sensors.pollIntervalMs,
  });
  const previewReadings = useMemo(() => createPreviewSensorReadings(), []);
  const sensorReadings =
    dataMode === "preview" ? previewReadings : liveSensors.readings;
  const sensorError = dataMode === "preview" ? null : liveSensors.error;
  const sensorsLoading = dataMode === "live" && liveSensors.isLoading;
  const validSensorCount = sensorReadings.filter((reading) => reading.valid).length;
  const world = state.snapshot?.world;
  const canStop = currentAction
    ? !TERMINAL_STATUSES.has(currentAction.status)
    : false;
  const isWorking = ["preparing", "executing", "verifying"].includes(phase);

  const companionLine =
    phase === "complete"
      ? "今晚也替你收好啦。"
      : phase === "failed"
        ? "这次没有完成，\n动作已经停下。"
        : phase === "stopped"
          ? "已经停下，\n今晚不再继续。"
          : isWorking
            ? "手机和灯，\n今晚交给我。"
            : "今晚，我守着。";

  const companionNote = state.error
    ? "连接没有完成，恢复后可以重新读取今晚的状态。"
    : world?.inferred_sleep_state === "asleep"
      ? "已确认你稳定入睡，正在根据真实设备状态完成睡前收尾。"
      : "我会先确认睡眠、手机和设备状态，再决定是否行动。";

  const phoneState = world
    ? world.phone_location === "operation_zone"
      ? "安全范围内"
      : world.phone_location || "未知"
    : "读取中";
  const lightState =
    world?.light_on === true
      ? "仍亮着"
      : world?.light_on === false
        ? "已关闭"
        : "读取中";
  const sleepState = world
    ? world.inferred_sleep_state === "asleep"
      ? "稳定入睡"
      : world.person_in_bed
        ? "仍在床上"
        : "尚未确认"
    : "读取中";

  return (
    <main data-screen-label="好梦鸟">
      <PageIntro eyebrow="Tonight" title="今晚，我守着。" />

      {state.error && (
        <section className={styles.errorCard} role="alert">
          <div>
            <strong>没有连接到睡眠 Agent</strong>
            <p>{state.error}</p>
          </div>
          <button type="button" onClick={() => void refresh()}>
            重新连接
          </button>
        </section>
      )}

      <section className={styles.companionCard} aria-label="好梦鸟当前状态">
        <div className={styles.companionCopy}>
          <div className={styles.statusPill}>
            <span
              className={cx(
                styles.statusDot,
                state.connection !== "connected" && styles.statusDotOffline,
              )}
            />
            {PHASE_LABELS[phase]}
          </div>
          <p className={styles.companionLine}>
            {companionLine.split("\n").map((line) => (
              <span key={line}>{line}</span>
            ))}
          </p>
          <p className={styles.companionNote}>{companionNote}</p>
        </div>
        <div
          className={cx(
            styles.robot,
            isWorking && styles.robotExecuting,
            phase === "complete" && styles.robotSleeping,
          )}
        >
          <Image
            className={styles.robotImage}
            src="/assets/haomeng-bird-arm.png"
            alt="红色小鸟造型的好梦鸟机械臂"
            width={1106}
            height={1422}
            priority
          />
        </div>
      </section>

      <section className={styles.sensorPanel} aria-label="实时获取的信息状态">
        <div className={styles.sensorHeader}>
          <div>
            <span className={styles.sensorKicker}>ENV-S3 · 实时感知</span>
            <h2>获取到的信息</h2>
          </div>
          <span
            className={cx(
              styles.sensorSummary,
              sensorError && styles.sensorSummaryError,
            )}
          >
            {sensorError
              ? "连接中断"
              : sensorsLoading
                ? "正在连接"
                : dataMode === "preview"
                  ? "模拟状态"
                  : `${validSensorCount}/${SENSOR_ITEMS.length} 有效`}
          </span>
        </div>

        {sensorError && (
          <p className={styles.sensorError} title={sensorError}>
            {sensorConnectionMessage(sensorError)}
          </p>
        )}

        <div className={styles.sensorGrid}>
          {SENSOR_ITEMS.map((item) => {
            const reading = sensorReadings.find(
              (candidate) => candidate.sensor === item.sensor,
            );
            return (
              <div className={styles.sensorItem} key={item.sensor}>
                <div className={styles.sensorItemHead}>
                  <span>{item.label}</span>
                  <i
                    className={cx(
                      styles.sensorValidity,
                      !reading && styles.sensorValidityWaiting,
                      reading && !reading.valid && styles.sensorValidityInvalid,
                    )}
                  />
                </div>
                <strong>{reading ? sensorValue(reading) : "等待数据"}</strong>
                <small>
                  {reading
                    ? readingMeta(reading, dataMode === "preview")
                    : sensorsLoading
                      ? "首次读取中"
                      : "尚未收到"}
                </small>
              </div>
            );
          })}
        </div>
      </section>

      <div className={styles.sectionLabel}>
        <h2>今晚的时间线</h2>
        <span>状态与真实动作同步</span>
      </div>

      <div className={styles.timeline}>
        <div className={styles.timelineItem}>
          <div className={styles.timelineDot} />
          <div className={styles.timelineCard}>
            <div className={styles.timelineMeta}>
              <span>观察到的事实</span>
              <span>{state.connection === "connected" ? "已同步" : "等待连接"}</span>
            </div>
            <div className={styles.timelineTitle}>{sleepState}</div>
            <p className={styles.timelineText}>
              {dataMode === "preview"
                ? "睡眠、手机和灯光状态来自本地预览数据，不会连接后端。"
                : "睡眠、手机和灯光状态均直接读取自 Agent 环境快照。"}
            </p>
            <button
              className={styles.evidenceToggle}
              type="button"
              onClick={() => setShowEvidence((visible) => !visible)}
              aria-expanded={showEvidence}
            >
              {showEvidence ? "收起依据" : "发生了什么"}
            </button>
            {showEvidence && (
              <div className={styles.evidenceGrid}>
                <div className={styles.evidence}>
                  <b>{sleepState}</b>
                  <span>睡眠状态</span>
                </div>
                <div className={styles.evidence}>
                  <b>{phoneState}</b>
                  <span>手机位置</span>
                </div>
                <div className={styles.evidence}>
                  <b>{lightState}</b>
                  <span>床头灯</span>
                </div>
                <div className={styles.evidence}>
                  <b>{state.latestEvent?.event_type ?? "等待事件"}</b>
                  <span>最新事件</span>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className={styles.timelineItem}>
          <div className={cx(styles.timelineDot, styles.timelineDotAccent)} />
          <div>
            {(phase === "idle" || phase === "stopped" || phase === "failed") && (
              <section className={styles.decisionCard}>
                <span className={styles.decisionKicker}>场景演示</span>
                <h3 className={styles.decisionTitle}>模拟稳定入睡后的睡前收尾</h3>
                <p className={styles.decisionCopy}>
                  {dataMode === "preview"
                    ? "这只会更新本地预览状态，用于调试执行中和停止后的界面。"
                    : "这会向现有后端提交一条调试观察，由 Agent 判断是否收手机和关灯。"}
                </p>
                <div className={styles.decisionOptions}>
                  <span>{dataMode === "preview" ? "本地状态" : "真实状态"}</span>
                  <span>安全检查</span>
                  <span>随时停止</span>
                </div>
                <button
                  className={styles.primaryButton}
                  type="button"
                  disabled={
                    state.connection !== "connected" ||
                    state.isStarting ||
                    state.isStopping ||
                    canStop
                  }
                  onClick={() => void runPickupDemo()}
                >
                  {state.isStarting ? "正在启动" : "模拟已经稳定入睡"}
                </button>
              </section>
            )}

            {phase === "waiting_confirmation" && (
              <section className={styles.timelineCard}>
                <div className={styles.timelineMeta}>
                  <span>需要确认</span>
                  <span>动作未开始</span>
                </div>
                <div className={styles.timelineTitle}>Agent 正在等待行动确认</div>
                <p className={styles.timelineText}>
                  这次确认入口还未接入，动作不会自行开始。你仍然可以停止这次运行。
                </p>
                <button
                  className={styles.stopTextButton}
                  type="button"
                  disabled={!canStop || state.isStopping}
                  onClick={() => void stopCurrentRun()}
                >
                  {state.isStopping ? "正在停止" : "停止这次运行"}
                </button>
              </section>
            )}

            {isWorking && (
              <section className={styles.progressCard}>
                <div className={styles.progressHead}>
                  <strong>{currentAction?.capability ?? "正在准备动作"}</strong>
                  <span className={styles.progressPercent}>
                    {state.progress === null ? "同步中" : `${state.progress}%`}
                  </span>
                </div>
                <div className={styles.progressTrack} aria-label="动作进度">
                  {state.progress === null ? (
                    <span className={styles.progressIndeterminate} />
                  ) : (
                    <span
                      className={styles.progressFill}
                      style={{ width: `${state.progress}%` }}
                    />
                  )}
                </div>
                <p className={styles.progressCaption}>
                  {currentAction?.reason || "持续检查设备状态和停止条件。"}
                </p>
                <button
                  className={styles.stopButton}
                  type="button"
                  disabled={!canStop || state.isStopping}
                  onClick={() => void stopCurrentRun()}
                >
                  <Icon name="stop" size={14} />
                  {state.isStopping ? "正在停止整条运行" : "立即停止"}
                </button>
              </section>
            )}

            {phase === "complete" && (
              <section className={styles.timelineCard}>
                <div className={styles.timelineMeta}>
                  <span>已完成</span>
                  <span>结果已同步</span>
                </div>
                <div className={styles.timelineTitle}>目标结果已经确认</div>
                <p className={styles.timelineText}>
                  手机位置为“{phoneState}”，床头灯“{lightState}”。
                </p>
                <button
                  className={styles.evidenceToggle}
                  type="button"
                  disabled={
                    state.connection !== "connected" || state.isStarting
                  }
                  onClick={() => void runPickupDemo()}
                >
                  再次演示
                </button>
              </section>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
