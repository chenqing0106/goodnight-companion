import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "好梦鸟｜睡眠 Agent",
  description: "在你入睡后完成安全、可停止的睡前收尾。",
};

export const viewport: Viewport = {
  themeColor: "#e9e5dd",
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
