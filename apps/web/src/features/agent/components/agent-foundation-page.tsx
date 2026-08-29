"use client";

import styles from "@/app/page.module.css";
import { useAgentRuntime } from "../hooks/use-agent-runtime";

const PHASE_LABELS = {
  idle: "等待场景",
  preparing: "正在准备",
  waiting_confirmation: "等待确认",
  executing: "正在执行",
  verifying: "正在验证",
  complete: "已经完成",
  stopped: "已经停止",
  failed: "执行失败",
} as const;

const CONNECTION_LABELS = {
  connecting: "正在连接",
  connected: "后端已连接",
  disconnected: "后端未连接",
} as const;

function formatValue(value: unknown) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

export function AgentFoundationPage() {
  const {
    state,
    currentAction,
    phase,
    refresh,
    runPickupDemo,
    stopCurrentRun,
  } = useAgentRuntime();

  const world = state.snapshot?.world;
  const device = state.snapshot?.devices[0];
  const canStop = currentAction
    ? !["succeeded", "failed", "stopped", "skipped"].some(
        (status) => status === currentAction.status,
      )
    : false;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Goodnight · F1 integration</p>
          <h1>睡后收手机，先跑通真实链路。</h1>
          <p className={styles.intro}>
            这个页面只验证 Next.js、FastAPI、Agent 工具层与设备状态。正式 UI
            完成后会复用下面这套数据逻辑。
          </p>
        </div>
        <div
          className={`${styles.connection} ${styles[state.connection]}`}
          role="status"
        >
          <span aria-hidden="true" />
          {CONNECTION_LABELS[state.connection]}
        </div>
      </header>

      {state.error && (
        <section className={styles.error} role="alert">
          <strong>连接没有完成</strong>
          <span>{state.error}</span>
          <button type="button" onClick={() => void refresh()}>
            重新连接
          </button>
        </section>
      )}

      <section className={styles.signalPanel} aria-label="Agent 执行链路">
        <div className={styles.signalHead}>
          <span>当前链路</span>
          <strong>{PHASE_LABELS[phase]}</strong>
        </div>
        <div className={styles.signalPath}>
          {[
            ["01", "感知", "人在床上、稳定入睡"],
            ["02", "判断", "需要收手机并关灯"],
            ["03", "安全", "设备、区域与冲突检查"],
            ["04", "执行", "工具调用到硬件"],
            ["05", "验证", "确认手机与灯光结果"],
          ].map(([index, title, copy]) => (
            <div className={styles.signalStep} key={index}>
              <span>{index}</span>
              <strong>{title}</strong>
              <small>{copy}</small>
            </div>
          ))}
        </div>
      </section>

      <div className={styles.grid}>
        <section className={styles.actionCard}>
          <div className={styles.sectionTitle}>
            <div>
              <p>场景 1</p>
              <h2>稳定入睡后完成睡前收尾</h2>
            </div>
            <span className={styles.phase}>{PHASE_LABELS[phase]}</span>
          </div>

          <dl className={styles.facts}>
            <div>
              <dt>睡眠状态</dt>
              <dd>{formatValue(world?.inferred_sleep_state)}</dd>
            </div>
            <div>
              <dt>手机位置</dt>
              <dd>{formatValue(world?.phone_location)}</dd>
            </div>
            <div>
              <dt>床头灯</dt>
              <dd>{world?.light_on === true ? "亮着" : "已关闭"}</dd>
            </div>
          </dl>

          {currentAction && (
            <div className={styles.currentAction}>
              <span>最近动作</span>
              <strong>{currentAction.capability}</strong>
              <code>{currentAction.status}</code>
              {state.progress !== null && (
                <div className={styles.progress} aria-label="动作进度">
                  <i style={{ width: `${state.progress}%` }} />
                </div>
              )}
              {currentAction.reason && <small>{currentAction.reason}</small>}
            </div>
          )}

          <div className={styles.actions}>
            <button
              className={styles.primaryButton}
              type="button"
              disabled={
                state.isStarting ||
                state.isStopping ||
                state.connection !== "connected" ||
                canStop
              }
              onClick={() => void runPickupDemo()}
            >
              {state.isStarting
                ? "正在启动"
                : "标记为已稳定入睡"}
            </button>
            <button
              className={styles.stopButton}
              type="button"
              disabled={!canStop || state.isStopping}
              onClick={() => void stopCurrentRun()}
            >
              {state.isStopping ? "正在停止" : "立即停止"}
            </button>
          </div>
        </section>

        <aside className={styles.sideColumn}>
          <section className={styles.detailCard}>
            <div className={styles.detailHead}>
              <h2>设备</h2>
              <span>{device?.availability ?? "unknown"}</span>
            </div>
            <strong>{device?.device_id ?? "等待设备"}</strong>
            <p>
              {device?.capabilities?.length
                ? device.capabilities.join(" · ")
                : "能力信息尚未同步"}
            </p>
          </section>

          <section className={styles.detailCard}>
            <div className={styles.detailHead}>
              <h2>最新事件</h2>
              <span>SSE</span>
            </div>
            <strong>{state.latestEvent?.event_type ?? "等待事件"}</strong>
            <p className={styles.eventId}>
              {state.latestEvent?.event_id ?? "连接后会在这里显示事件"}
            </p>
          </section>
        </aside>
      </div>
    </main>
  );
}
