import { PROACTIVITY_COPY } from "../../data/preview-fixtures";
import type {
  ProactivityMode,
  ProfileRuntime,
} from "../../model/companion-runtime";
import { EmptyCapability, Icon, PageIntro } from "../shared/shared-ui";
import styles from "./profile-page.module.css";

const MODES: ProactivityMode[] = ["安静", "平衡", "积极"];

export function ProfilePage({ runtime }: { runtime: ProfileRuntime }) {
  if (runtime.status === "ready") {
    return (
      <main data-screen-label="鸟窝">
        <PageIntro
          eyebrow="设置"
          title="主动程度与权限"
          subtitle="拒绝、停止、关闭摄像头，都不会影响你继续使用其他能力。"
        />

        <section className={styles.panelCard}>
          <div className={styles.sectionLabel}>
            <h2>主动程度</h2>
            <span>当前：{runtime.mode}</span>
          </div>
          <div className={styles.modeControl}>
            {MODES.map((mode) => (
              <button
                key={mode}
                type="button"
                className={mode === runtime.mode ? styles.modeButtonActive : styles.modeButton}
                onClick={() => runtime.setMode(mode)}
              >
                {mode}
              </button>
            ))}
          </div>
          <p className={styles.modeCopy}>{PROACTIVITY_COPY[runtime.mode]}</p>
        </section>

        <section className={styles.panelCard}>
          <div className={styles.privacyRow}>
            <div className={styles.listRowCompact}>
              <div className={styles.listIcon}>
                <Icon name="camera" />
              </div>
              <div className={styles.listMain}>
                <strong>床头相机</strong>
                <span>
                  {runtime.cameraEnabled
                    ? "仅本地识别，不保存原始画面"
                    : "已关闭，物理动作不会自动启动"}
                </span>
              </div>
            </div>
            <button
              className={
                runtime.cameraEnabled ? styles.switchOn : styles.switch
              }
              type="button"
              onClick={runtime.toggleCamera}
              role="switch"
              aria-checked={runtime.cameraEnabled}
              aria-label="摄像头开关"
            />
          </div>
        </section>

        <section className={styles.panelCard}>
          <div className={styles.listRow}>
            <div className={styles.listIcon}>
              <Icon name="shield" />
            </div>
            <div className={styles.listMain}>
              <strong>设备访问与安全</strong>
              <span>相机、机械臂、灯光与声音权限</span>
            </div>
            <button
              className={styles.rowAction}
              type="button"
              onClick={runtime.showSafetyStatus}
              aria-label="查看设备访问与安全"
            >
              <Icon name="chevron" size={17} />
            </button>
          </div>
        </section>

        <section className={styles.panelCard}>
          <div className={styles.listRow}>
            <div className={styles.listIcon}>
              <Icon name="clock" />
            </div>
            <div className={styles.listMain}>
              <strong>主动行动记录</strong>
              <span>过去 7 天主动询问 4 次，自动收尾 2 次</span>
            </div>
            <button
              className={styles.rowAction}
              type="button"
              onClick={runtime.showActivityLog}
              aria-label="查看主动行动记录"
            >
              <Icon name="chevron" size={17} />
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main data-screen-label="鸟窝">
      <PageIntro
        eyebrow="设置"
        title="主动程度与权限"
        subtitle="设置需要真实保存后才算生效。当前版本不会用本地开关模拟设备权限。"
      />
      <section className={styles.panelCard}>
        <div className={styles.listRow}>
          <div className={styles.listIcon}>
            <Icon name="shield" />
          </div>
          <div className={styles.listMain}>
            <strong>停止优先</strong>
            <span>进行中的动作可以从好梦鸟页面停止整条运行。</span>
          </div>
        </div>
      </section>
      <EmptyCapability
        icon="settings"
        title="偏好设置还没有接入"
        copy="主动程度、相机开关和权限管理需要对应的后端接口。接入前不提供看似生效的本地控件。"
      />
    </main>
  );
}
