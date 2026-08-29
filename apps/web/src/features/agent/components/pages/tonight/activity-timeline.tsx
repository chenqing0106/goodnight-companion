import { useEffect, useMemo, useRef, type ReactNode, type Ref } from "react";

import type {
  AgentActivityStepView,
  AgentActivityThreadView,
} from "../../../model/agent-activity";
import type { ActivityStep } from "../../../model/vitals-activity";
import { cx } from "../../shared/shared-ui";
import styles from "./activity-timeline.module.css";

type FinalState = "done" | "failed" | null;

type StreamEntry =
  | {
      kind: "activity";
      id: string;
      timestamp: string;
      step: AgentActivityStepView;
    }
  | { kind: "vitals"; id: string; timestamp: string; step: ActivityStep };

export interface ActivityTimelineProps {
  activity: AgentActivityThreadView | null;
  vitalsSteps: ActivityStep[];
}

function eventTime(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function stepClock(step: AgentActivityStepView) {
  return step.clock ?? eventTime(step.timestamp);
}

function stripOrdinal(item: string) {
  return item.replace(/^\s*\d+\s*[.、．)]\s*/, "");
}

function Row({
  clock,
  className,
  rowRef,
  children,
}: {
  clock: string;
  className?: string;
  rowRef?: Ref<HTMLLIElement>;
  children: ReactNode;
}) {
  return (
    <li ref={rowRef} className={cx(styles.row, className)}>
      <time className={styles.rowTime}>{clock}</time>
      <div className={styles.rowBody}>{children}</div>
    </li>
  );
}

interface StepRowProps {
  step: AgentActivityStepView;
  rowRef?: Ref<HTMLLIElement>;
}

/** 感知 / 决策叙事行：普通行是背景音，判断与结论加粗成全墨色 */
function NarrativeRow({
  step,
  final,
  rowRef,
}: StepRowProps & { final: FinalState }) {
  const emphasized =
    step.phase === "evaluation" ||
    step.phase === "conclusion" ||
    step.phase === "verification";
  const body = (
    <p
      className={cx(
        styles.narrative,
        emphasized && styles.narrativeKey,
        final === "done" && styles.narrativeFinal,
      )}
    >
      {final === "done" && <span className={styles.finalMark}>✓</span>}
      {final === "failed" && <span className={styles.finalMarkFailed}>✕</span>}
      <span className={step.status === "active" ? styles.shimmer : undefined}>
        {step.detail || step.title}
      </span>
    </p>
  );
  return (
    <Row clock={stepClock(step)} rowRef={rowRef}>
      {final === "done" ? (
        <div className={styles.finalCard}>{body}</div>
      ) : final === "failed" ? (
        <div className={styles.failedCard}>{body}</div>
      ) : (
        body
      )}
    </Row>
  );
}

/** 安全检查块：标题 + ✓ 网格，左竖线表示附属于决策 */
function ChecksRow({ step, rowRef }: StepRowProps) {
  return (
    <Row clock={stepClock(step)} rowRef={rowRef}>
      <div className={styles.block}>
        <p className={styles.blockLabel}>
          {step.status === "active" && <span className={styles.liveDot} />}
          {step.title || "执行前安全检查"}
          <span className={styles.blockCount}>{step.checks.length} 项</span>
        </p>
        <ul className={styles.checkList}>
          {step.checks.map((item) => (
            <li key={item}>
              <span className={styles.checkMark}>✓</span>
              {item}
            </li>
          ))}
        </ul>
      </div>
    </Row>
  );
}

/** 行动计划块：清单兼任进度条（✓ 完成 / → 进行中 / ○ 未开始） */
function PlanRow({ step, rowRef }: StepRowProps) {
  return (
    <Row clock={stepClock(step)} rowRef={rowRef}>
      <div className={styles.block}>
        <p className={styles.blockLabel}>
          {step.status === "active" && <span className={styles.liveDot} />}
          {step.title || "行动计划"}
          <span className={styles.blockCount}>{step.plan.length} 步</span>
        </p>
        <ol className={styles.planList}>
          {step.plan.map((item, index) => {
            const state =
              step.status === "succeeded"
                ? "done"
                : step.status === "active" && index === 0
                  ? "current"
                  : "todo";
            return (
              <li key={item} data-state={state}>
                <span className={styles.planMark} aria-hidden="true" />
                {stripOrdinal(item)}
              </li>
            );
          })}
        </ol>
      </div>
    </Row>
  );
}

function ToolMark({
  status,
  final,
}: {
  status: AgentActivityStepView["status"];
  final: FinalState;
}) {
  if (final === "failed" || status === "failed") {
    return <span className={cx(styles.toolMark, styles.toolMarkFailed)}>✕</span>;
  }
  if (status === "active") {
    return (
      <span className={cx(styles.toolMark, styles.liveDot)} aria-hidden="true" />
    );
  }
  return <span className={cx(styles.toolMark, styles.toolMarkDone)}>✓</span>;
}

/** 工具执行行：状态符号 + 动词文案，缩进挂工具回执 */
function ToolRow({
  step,
  final,
  rowRef,
}: StepRowProps & { final: FinalState }) {
  const body = (
    <div>
      <p className={styles.toolLine}>
        <ToolMark status={step.status} final={final} />
        <span className={step.status === "active" ? styles.shimmer : undefined}>
          {step.detail || step.title}
        </span>
      </p>
      {step.tools.length > 0 && (
        <ul className={styles.toolMeta}>
          {step.tools.map((tool) => (
            <li key={`${tool.name}-${tool.deviceId}`}>
              <code>{tool.name}</code>
              <span>
                {tool.status === "running"
                  ? "等待设备回执…"
                  : (tool.receipt ?? "")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
  return (
    <Row clock={stepClock(step)} rowRef={rowRef}>
      {final === "done" ? (
        <div className={styles.finalCard}>{body}</div>
      ) : final === "failed" ? (
        <div className={styles.failedCard}>{body}</div>
      ) : (
        body
      )}
    </Row>
  );
}

/** 生命体征感知行：整条流里最轻的背景音 */
function VitalsRow({ step }: { step: ActivityStep }) {
  return (
    <Row clock={eventTime(step.timestamp)}>
      <p className={styles.vitals}>
        <span className={styles.vitalsLabel}>{step.label}</span>
        {step.detail}
      </p>
    </Row>
  );
}

export function ActivityTimeline({
  activity,
  vitalsSteps,
}: ActivityTimelineProps) {
  const lastRowRef = useRef<HTMLLIElement | null>(null);
  const running = activity?.status === "running";
  const stepCount = activity?.steps.length ?? 0;

  useEffect(() => {
    if (!running) return;
    lastRowRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [running, stepCount]);

  const entries = useMemo<StreamEntry[]>(() => {
    const activityEntries: StreamEntry[] = (activity?.steps ?? []).map(
      (step) => ({
        kind: "activity",
        id: step.id,
        timestamp: step.timestamp,
        step,
      }),
    );
    const vitalsEntries: StreamEntry[] = vitalsSteps.map((step) => ({
      kind: "vitals",
      id: `vitals-${step.key}`,
      timestamp: step.timestamp,
      step,
    }));
    return [...activityEntries, ...vitalsEntries].sort(
      (left, right) =>
        Date.parse(left.timestamp) - Date.parse(right.timestamp),
    );
  }, [activity, vitalsSteps]);

  if (!activity && entries.length === 0) {
    return (
      <p className={styles.empty}>
        还没有过程记录。感知、判断、计划和执行会随事件逐条出现在这里。
      </p>
    );
  }

  const lastActivityStepId = activity?.steps.at(-1)?.id;

  return (
    <section className={styles.run} aria-label="任务过程">
      <ol className={styles.stream}>
        {entries.map((entry) => {
          if (entry.kind === "vitals") {
            return <VitalsRow key={entry.id} step={entry.step} />;
          }
          const { step } = entry;
          const isLast = step.id === lastActivityStepId;
          const final: FinalState =
            !isLast || !activity
              ? null
              : activity.status === "completed"
                ? "done"
                : activity.status === "failed" || activity.status === "stopped"
                  ? "failed"
                  : null;
          const rowRef = running && isLast ? lastRowRef : undefined;
          switch (step.kind) {
            case "checks":
              return <ChecksRow key={step.id} step={step} rowRef={rowRef} />;
            case "plan":
              return <PlanRow key={step.id} step={step} rowRef={rowRef} />;
            case "tool":
              return (
                <ToolRow
                  key={step.id}
                  step={step}
                  final={final}
                  rowRef={rowRef}
                />
              );
            default:
              return (
                <NarrativeRow
                  key={step.id}
                  step={step}
                  final={final}
                  rowRef={rowRef}
                />
              );
          }
        })}
      </ol>
    </section>
  );
}
