import { useState } from "react";

import type { CompanionDataMode } from "../../companion-config";
import type { AgentRuntime } from "../companion-types";
import { cx, Icon, PageIntro } from "../shared/shared-ui";
import styles from "./devices-page.module.css";

export function DevicesPage({
  runtime,
  dataMode,
}: {
  runtime: AgentRuntime;
  dataMode: CompanionDataMode;
}) {
  const { state, refresh } = runtime;
  const [expanded, setExpanded] = useState<string | null>(null);
  const devices = state.snapshot?.devices ?? [];
  const deviceStates = state.snapshot?.world.device_states ?? {};
  const onlineCount = devices.filter(
    (device) => device.availability === "online",
  ).length;
  const allExpectedDevicesReady =
    devices.length > 0 &&
    devices.every(
      (device) =>
        device.availability === "online" ||
        deviceStates[device.device_id] === "未开放",
    );

  return (
    <main data-screen-label="设备">
      <PageIntro
        eyebrow=""
        title="设备与能力"
        subtitle={
          dataMode === "preview"
            ? "这里显示本地预览设备，用于独立调试设备列表和状态。"
            : "这里只显示后端已经登记的设备与能力。所有进行中的物理动作都能立即停止。"
        }
      />

      {state.error && (
        <section className={styles.errorCard} role="alert">
          <div>
            <strong>设备状态没有同步</strong>
            <p>{state.error}</p>
          </div>
          <button type="button" onClick={() => void refresh()}>
            重新读取
          </button>
        </section>
      )}

      <section className={styles.panelCard}>
        <div className={styles.listRow}>
          <div className={styles.listIcon}>
            <Icon name="check" />
          </div>
          <div className={styles.listMain}>
            <strong>
              {devices.length
                ? dataMode === "preview"
                  ? `${onlineCount} 项能力可用`
                  : `${onlineCount} 台设备在线`
                : "等待设备"}
            </strong>
            <span>
              {devices.length
                ? dataMode === "preview"
                  ? `共准备 ${devices.length} 台本地预览设备`
                  : `共登记 ${devices.length} 台设备，状态来自 Agent 设备注册表`
                : dataMode === "preview"
                  ? "可以在预览 Runtime 中补充设备"
                  : "连接后会在这里显示真实设备"}
            </span>
          </div>
          <div
            className={cx(
              styles.availability,
              !allExpectedDevicesReady && styles.availabilityOff,
            )}
          >
            <i />
            {allExpectedDevicesReady ? "正常" : "检查中"}
          </div>
          <span className={styles.rowActionSpacer} aria-hidden="true" />
        </div>
      </section>

      {devices.map((device) => {
        const isExpanded = expanded === device.device_id;
        const normalizedId = device.device_id.toLowerCase();
        const icon = normalizedId.includes("light") || device.device_id.includes("灯")
          ? "light"
          : normalizedId.includes("camera") || device.device_id.includes("相机")
            ? "camera"
            : "arm";
        const stateLabel =
          deviceStates[device.device_id] ??
          (device.availability === "online"
            ? "在线"
            : device.availability === "offline"
              ? "离线"
              : "未知");
        const isUnavailable =
          device.availability !== "online" || stateLabel === "未开放";
        const isEnvS3 = normalizedId.includes("env-s3");
        const rgbMode = state.snapshot?.world.rgb_indicator_mode;
        const rgbState =
          rgbMode === 2 ? "绿色" : rgbMode === 0 ? "关闭" : "尚未同步";
        return (
          <section className={styles.panelCard} key={device.device_id}>
            <div className={styles.listRow}>
              <div className={styles.listIcon}>
                <Icon name={icon} />
              </div>
              <div className={styles.listMain}>
                <strong>{device.device_id}</strong>
                <span>
                  {device.capabilities?.length
                    ? device.capabilities.join(" · ")
                    : device.capabilities_known
                      ? "暂未登记可用能力"
                      : "能力信息尚未同步"}
                </span>
              </div>
              <div
                className={cx(
                  styles.availability,
                  isUnavailable && styles.availabilityOff,
                )}
              >
                <i />
                {stateLabel}
              </div>
              <button
                className={styles.rowAction}
                type="button"
                onClick={() => setExpanded(isExpanded ? null : device.device_id)}
                aria-expanded={isExpanded}
                aria-label={`查看 ${device.device_id} 详情`}
              >
                <Icon name="chevron" size={17} />
              </button>
            </div>
            {isExpanded && (
              <div className={styles.deviceDetails}>
                能力信息
                {device.capabilities_known
                  ? dataMode === "preview"
                    ? "已由本地预览数据提供"
                    : "已由后端确认"
                  : "仍在等待同步"}
                。
                {device.updated_at && <span> 最近更新时间已记录。</span>}
                {isEnvS3 && <span> RGB 指示灯：{rgbState}。</span>}
              </div>
            )}
          </section>
        );
      })}
    </main>
  );
}
