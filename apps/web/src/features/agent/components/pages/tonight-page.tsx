import Image from "next/image";
import { useEffect, useMemo, useRef } from "react";

import type { SensorName, SensorReading } from "../../api/types";
import {
  COMPANION_CONFIG,
  type CompanionDataMode,
} from "../../companion-config";
import { createPreviewSensorReadings } from "../../data/preview-fixtures";
import { useSensorReadings } from "../../hooks/use-sensor-readings";
import {
  buildAgentActivities,
  buildLatestAgentActivity,
  type AgentActivityStepView,
  type AgentActivityThreadView,
} from "../../model/agent-activity";
import {
  buildLatestVitalsRun,
  buildVitalsEvaluation,
  type ActivityStep,
  type ActivityTone,
} from "../../model/vitals-activity";
import type { AgentPhase } from "../../model/reducer";
import type { AgentRuntime } from "../companion-types";
import { cx, PageIntro } from "../shared/shared-ui";
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

const ACTIVE_PHASE_COPY: Record<AgentActivityStepView["phase"], string> = {
  observation: "正在感知环境变化",
  evaluation: "正在结合连续信号判断",
  conclusion: "正在形成当前结论",
  plan: "正在规划下一步行动",
  safety: "正在确认执行条件",
  action: "正在等待设备响应",
  verification: "正在核对执行结果",
};

const SHOW_SENSOR_PANEL = false;

type TonightTimelineEntry =
  | {
      kind: "activity";
      id: string;
      timestamp: string;
      activity: AgentActivityThreadView;
      step: AgentActivityStepView;
      isLastStep: boolean;
      isLatestRun: boolean;
    }
  | {
      kind: "vitals";
      id: string;
      timestamp: string;
      step: ActivityStep;
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

function activityToneClass(tone: ActivityTone) {
  const classes = {
    quiet: styles.activityQuiet,
    active: styles.activityActive,
    success: styles.activitySuccess,
    failed: styles.activityFailed,
  };
  return classes[tone];
}

function eventTime(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
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
    restoreNormalState,
    runMockActivityDemo,
  } = runtime;
  const latestActivityNodeRef = useRef<HTMLDivElement | null>(null);
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
  const requiredSamples = state.automation?.required_samples ?? null;
  const vitalsEvaluation = useMemo(
    () => buildVitalsEvaluation(state.events, world, requiredSamples),
    [requiredSamples, state.events, world],
  );
  const vitalsRun = useMemo(
    () => buildLatestVitalsRun(state.events),
    [state.events],
  );
  const agentActivity = useMemo(
    () => buildLatestAgentActivity(state.events),
    [state.events],
  );
  const agentActivities = useMemo(
    () => buildAgentActivities(state.events).slice(-1),
    [state.events],
  );
  const timelineEntries = useMemo<TonightTimelineEntry[]>(() => {
    const activityEntries: TonightTimelineEntry[] = agentActivities.flatMap(
      (activity) =>
        activity.steps.map((step, index) => ({
          kind: "activity",
          id: step.id,
          timestamp: step.timestamp,
          activity,
          step,
          isLastStep: index === activity.steps.length - 1,
          isLatestRun: activity.runId === agentActivity?.runId,
        })),
    );
    const vitalsEntries: TonightTimelineEntry[] = (vitalsRun?.steps ?? [])
      .filter((step) => step.tone !== "quiet")
      .map((step) => ({
        kind: "vitals",
        id: `${vitalsRun?.runId ?? "vitals"}-${step.key}`,
        timestamp: step.timestamp,
        step,
      }));

    return [...activityEntries, ...vitalsEntries].sort(
      (left, right) =>
        Date.parse(left.timestamp) - Date.parse(right.timestamp),
    );
  }, [agentActivities, agentActivity?.runId, vitalsRun]);
  const activityRunning = agentActivity?.status === "running";
  const activityStepCount = agentActivity?.steps.length ?? 0;
  const isVitalsAction = currentAction?.capability === "set_rgb_indicator";
  const automationLabel =
    state.automation === null
      ? "检查自动感知"
      : state.automation.enabled
        ? `自动感知 · ${state.automation.required_samples ?? 3} 次确认`
        : "自动感知未开启";
  const isWorking = ["preparing", "executing", "verifying"].includes(phase);

  useEffect(() => {
    if (!activityRunning) return;
    latestActivityNodeRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, [activityRunning, activityStepCount]);

  const companionLine =
    phase === "complete"
      ? isVitalsAction
        ? world?.rgb_indicator_mode === 2
          ? "信号稳定，\n指示灯已亮起。"
          : "没有检测到手指，\n指示灯已关闭。"
        : "今晚也替你收好啦。"
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

      {SHOW_SENSOR_PANEL && (
        <section className={styles.sensorPanel} aria-label="实时获取的信息状态">
        <div className={styles.sensorHeader}>
          <div>
            <span className={styles.sensorKicker}>ENV-S3 · 实时感知</span>
            <h2>获取到的信息</h2>
          </div>
          <div className={styles.sensorBadges}>
            <span
              className={cx(
                styles.automationBadge,
                state.automation?.enabled === false && styles.automationBadgeOff,
              )}
            >
              {automationLabel}
            </span>
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

        <div
          className={cx(
            styles.signalStatus,
            activityToneClass(vitalsEvaluation.tone),
          )}
          aria-live="polite"
        >
          <i />
          <div>
            <strong>{vitalsEvaluation.label}</strong>
            <span>{vitalsEvaluation.detail}</span>
          </div>
          <b>{vitalsEvaluation.progress}</b>
        </div>
        </section>
      )}

      <div className={styles.sectionLabel}>
        <div>
          <h2>今晚的时间线</h2>
          <span>观察、判断和行动会连续保留</span>
        </div>
        {(!agentActivity || activityRunning) && (
          <button
            className={styles.activityDemoButton}
            type="button"
            disabled={
              state.connection !== "connected" ||
              state.isStartingActivity ||
              activityRunning
            }
            onClick={() => void runMockActivityDemo()}
          >
            {state.isStartingActivity
              ? "正在启动"
              : activityRunning
                ? "感知进行中"
                : "播放动态过程"}
          </button>
        )}
      </div>

      <div className={styles.timeline}>
        {timelineEntries.length > 0 ? (
          timelineEntries.map((entry) => {
            if (entry.kind === "vitals") {
              return (
                <div className={styles.timelineItem} key={entry.id}>
                  <div
                    className={cx(
                      styles.timelineDot,
                      styles.timelineDotAccent,
                      activityToneClass(entry.step.tone),
                    )}
                  />
                  <section className={styles.timelineCard} aria-live="polite">
                    <div className={styles.timelineMeta}>
                      <span>生命体征感知</span>
                      <time>{eventTime(entry.timestamp)}</time>
                    </div>
                    <div className={styles.timelineTitle}>
                      {entry.step.label}
                    </div>
                    <p className={styles.timelineText}>{entry.step.detail}</p>
                  </section>
                </div>
              );
            }

            const { activity, step } = entry;
            return (
              <div
                className={styles.timelineItem}
                key={entry.id}
                ref={
                  entry.isLatestRun && entry.isLastStep
                    ? latestActivityNodeRef
                    : undefined
                }
              >
                <div
                  className={cx(
                    styles.timelineDot,
                    styles.timelineDotAccent,
                    step.status === "active" && styles.activityActive,
                    step.status === "succeeded" && styles.activitySuccess,
                    step.status === "failed" && styles.activityFailed,
                  )}
                />
                <article
                  className={cx(
                    styles.timelineCard,
                    styles.activityTimelineCard,
                    step.status === "active" &&
                      styles.activityTimelineCardActive,
                    activity.status === "completed" &&
                      entry.isLastStep &&
                      styles.activityResultCard,
                    activity.status === "failed" &&
                      entry.isLastStep &&
                      styles.activityFailedCard,
                  )}
                  aria-current={step.status === "active" ? "step" : undefined}
                >
                  <div className={styles.timelineMeta}>
                    <span>{step.phaseLabel}</span>
                    <time>{eventTime(step.timestamp)}</time>
                  </div>
                  <div className={styles.timelineTitle}>{step.title}</div>
                  <p className={styles.timelineText}>{step.detail}</p>
                  <div className={styles.timelineEvidence}>
                    {step.evidence.map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                  {step.status === "active" && (
                    <span className={styles.activityTimelineProgress}>
                      {ACTIVE_PHASE_COPY[step.phase]}
                    </span>
                  )}
                  {entry.isLatestRun &&
                    activity.status !== "running" &&
                    entry.isLastStep && (
                      <div className={styles.resultActions}>
                        <button
                          className={styles.resultPrimaryAction}
                          type="button"
                          disabled={
                            state.connection !== "connected" ||
                            state.isStartingActivity ||
                            state.isStarting
                          }
                          onClick={() => void runMockActivityDemo()}
                        >
                          {activity.status === "failed"
                            ? "重新尝试控制"
                            : "开始新一轮监测"}
                        </button>
                        <button
                          className={styles.resultSecondaryAction}
                          type="button"
                          disabled={
                            state.connection !== "connected" || state.isStarting
                          }
                          onClick={() => void restoreNormalState()}
                        >
                          {state.isStarting ? "正在恢复" : "恢复正常状态"}
                        </button>
                      </div>
                    )}
                </article>
              </div>
            );
          })
        ) : (
          <div className={styles.timelineItem}>
            <div className={styles.timelineDot} />
            <section
              className={cx(
                styles.timelineCard,
                styles.activityTimelineEmpty,
              )}
            >
              <div className={styles.timelineMeta}>
                <span>连续过程演示</span>
                <span>尚未开始</span>
              </div>
              <div className={styles.timelineTitle}>等待播放连续过程</div>
              <p className={styles.timelineText}>
                点击上方按钮后，观察、判断、计划、执行和验证会逐条加入这条时间线。
              </p>
              <span className={styles.activityTimelineProgress}>
                新的观察和判断会随着事件发生继续加入。
              </span>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
