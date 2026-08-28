"use client";

import { useState } from "react";

import {
  COMPANION_CONFIG,
  type CompanionDataMode,
} from "../companion-config";
import {
  LIVE_MEMORY_RUNTIME,
  LIVE_PROFILE_RUNTIME,
  useLiveCompanionRuntime,
} from "../hooks/use-live-companion-runtime";
import { usePreviewRuntime } from "../hooks/use-preview-runtime";
import type { CompanionRuntime } from "../model/companion-runtime";
import type { TabId } from "./companion-types";
import { DevicesPage } from "./pages/devices-page";
import { MemoryPage } from "./pages/memory-page";
import { ProfilePage } from "./pages/profile-page";
import { TonightPage } from "./pages/tonight-page";
import { cx, Icon, type IconName } from "./shared/shared-ui";
import styles from "./goodnight-companion-app.module.css";

function BottomNav({
  active,
  onChange,
}: {
  active: TabId;
  onChange: (tab: TabId) => void;
}) {
  const items: Array<[TabId, IconName, string]> = [
    ["tonight", "moon", "好梦鸟"],
    ["devices", "devices", "设备"],
    ["memory", "memory", "记忆"],
    ["profile", "user", "鸟窝"],
  ];

  return (
    <nav className={styles.bottomNav} aria-label="主导航">
      {items.map(([id, icon, label]) => (
        <button
          key={id}
          type="button"
          className={cx(styles.navButton, active === id && styles.navButtonActive)}
          onClick={() => onChange(id)}
          aria-current={active === id ? "page" : undefined}
        >
          <span className={styles.navGlyph}>
            <Icon name={icon} size={19} />
          </span>
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}

function CompanionShell({
  liveRuntime,
  previewRuntime,
}: {
  liveRuntime?: CompanionRuntime;
  previewRuntime?: CompanionRuntime;
}) {
  const [activeTab, setActiveTab] = useState<TabId>("tonight");
  const modes = COMPANION_CONFIG.pageDataMode;

  const selectRuntime = (mode: CompanionDataMode) => {
    const selected = mode === "preview" ? previewRuntime : liveRuntime;
    if (!selected) throw new Error(`Missing ${mode} companion runtime`);
    return selected;
  };

  const tonightRuntime = selectRuntime(modes.tonight);
  const devicesRuntime = selectRuntime(modes.devices);
  const memoryRuntime =
    modes.memory === "preview"
      ? selectRuntime("preview").memory
      : LIVE_MEMORY_RUNTIME;
  const profileRuntime =
    modes.profile === "preview"
      ? selectRuntime("preview").profile
      : LIVE_PROFILE_RUNTIME;

  return (
    <div className={styles.stage}>
      <div className={styles.phoneShell}>
        <div
          className={cx(
            styles.toast,
            previewRuntime?.notice && styles.toastVisible,
          )}
          role="status"
          aria-live="polite"
        >
          {previewRuntime?.notice}
        </div>
        <div className={styles.appScroll}>
          <header className={styles.topbar}>
            <div className={styles.brandLockup}>
              <div className={styles.brandMark}>
                <Icon name="moon" size={19} />
              </div>
              <div>
                <div className={styles.brandName}>好梦鸟</div>
                <div className={styles.brandStatus}>人好，熬夜坏</div>
              </div>
            </div>
            <button
              className={styles.iconButton}
              type="button"
              onClick={() => setActiveTab("profile")}
              aria-label="打开鸟窝设置"
            >
              <Icon name="settings" />
            </button>
          </header>

          {activeTab === "tonight" && (
            <TonightPage runtime={tonightRuntime} dataMode={modes.tonight} />
          )}
          {activeTab === "devices" && (
            <DevicesPage runtime={devicesRuntime} dataMode={modes.devices} />
          )}
          {activeTab === "memory" && <MemoryPage runtime={memoryRuntime} />}
          {activeTab === "profile" && <ProfilePage runtime={profileRuntime} />}
        </div>

        {activeTab === "tonight" && (
          <div className={styles.composerWrap} aria-label="对话输入尚未接入">
            <div className={styles.composer}>
              <button type="button" disabled aria-label="语音输入尚未接入">
                <Icon name="mic" size={18} />
              </button>
              <input readOnly value="" placeholder="试试语音功能" />
              <button type="button" disabled aria-label="发送功能尚未接入">
                <Icon name="send" size={17} />
              </button>
            </div>
          </div>
        )}

        <BottomNav active={activeTab} onChange={setActiveTab} />
      </div>
    </div>
  );
}

function LiveOnlyApp() {
  const liveRuntime = useLiveCompanionRuntime();
  return <CompanionShell liveRuntime={liveRuntime} />;
}

function PreviewOnlyApp() {
  const previewRuntime = usePreviewRuntime();
  return <CompanionShell previewRuntime={previewRuntime} />;
}

function MixedDataApp() {
  const liveRuntime = useLiveCompanionRuntime();
  const previewRuntime = usePreviewRuntime();

  return (
    <CompanionShell
      liveRuntime={liveRuntime}
      previewRuntime={previewRuntime}
    />
  );
}

export function GoodnightCompanionApp() {
  const modes = COMPANION_CONFIG.pageDataMode;
  const needsLiveAgent = modes.tonight === "live" || modes.devices === "live";
  const needsPreview = Object.values(modes).includes("preview");

  if (needsLiveAgent && needsPreview) return <MixedDataApp />;
  if (needsPreview) return <PreviewOnlyApp />;
  return <LiveOnlyApp />;
}
