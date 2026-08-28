import type { ReactNode } from "react";

import styles from "./shared-ui.module.css";

export type IconName =
  | "moon"
  | "settings"
  | "devices"
  | "memory"
  | "user"
  | "camera"
  | "arm"
  | "light"
  | "shield"
  | "chevron"
  | "mic"
  | "send"
  | "stop"
  | "check"
  | "clock"
  | "plus";

export function cx(
  ...classNames: Array<string | false | null | undefined>
) {
  return classNames.filter(Boolean).join(" ");
}

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    moon: <path d="M20 15.1A8 8 0 0 1 8.9 4 8 8 0 1 0 20 15.1Z" />,
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.82 2.82-.06-.06a1.7 1.7 0 0 0-1.88-.34A1.7 1.7 0 0 0 14 20.91V21h-4v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06-2.82-2.82.06-.06A1.7 1.7 0 0 0 4.64 15 1.7 1.7 0 0 0 3.09 14H3v-4h.09A1.7 1.7 0 0 0 4.64 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.82-2.82.06.06A1.7 1.7 0 0 0 9 4.64 1.7 1.7 0 0 0 10 3.09V3h4v.09A1.7 1.7 0 0 0 15 4.64a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.82 2.82-.06.06A1.7 1.7 0 0 0 19.36 9 1.7 1.7 0 0 0 20.91 10H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z" />
      </>
    ),
    devices: (
      <>
        <rect x="5" y="3" width="14" height="18" rx="3" />
        <path d="M9 17h6M9 7h6" />
      </>
    ),
    memory: (
      <>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5v13Z" />
        <path d="M8 7h7M8 11h5" />
      </>
    ),
    user: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4.5 21a7.5 7.5 0 0 1 15 0" />
      </>
    ),
    camera: (
      <>
        <path d="M15 8.5 20 6v12l-5-2.5" />
        <rect x="3" y="5" width="12" height="14" rx="2" />
      </>
    ),
    arm: (
      <>
        <circle cx="8" cy="16" r="2.5" />
        <circle cx="15" cy="8" r="2.5" />
        <path d="m9.7 14.1 3.6-4.2M17 10l3 4v5M17 19h5M5.5 18.5 3 21h10" />
      </>
    ),
    light: (
      <>
        <path d="M9 18h6M10 22h4" />
        <path d="M8 14a6 6 0 1 1 8 0c-1 .8-1 1.5-1 2H9c0-.5 0-1.2-1-2Z" />
      </>
    ),
    shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    mic: (
      <>
        <rect x="9" y="3" width="6" height="12" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
      </>
    ),
    send: (
      <>
        <path d="m22 2-7 20-4-9-9-4 20-7Z" />
        <path d="M22 2 11 13" />
      </>
    ),
    stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
    check: <path d="m5 12 4 4L19 6" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

export function PageIntro({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className={styles.pageIntro}>
      <p className={styles.eyebrow}>{eyebrow}</p>
      <h1 className={styles.pageTitle}>{title}</h1>
      {subtitle && <p className={styles.pageSubtitle}>{subtitle}</p>}
    </div>
  );
}

export function EmptyCapability({
  icon,
  title,
  copy,
}: {
  icon: IconName;
  title: string;
  copy: string;
}) {
  return (
    <section className={styles.emptyCapability}>
      <span className={styles.emptyIcon}>
        <Icon name={icon} size={24} />
      </span>
      <strong>{title}</strong>
      <p>{copy}</p>
      <span className={styles.pendingLabel}>等待后端能力</span>
    </section>
  );
}
