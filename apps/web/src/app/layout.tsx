import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Goodnight Agent · 场景 1 联调",
  description: "好梦鸟前端与 Agent 后端的最小联调页面",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
