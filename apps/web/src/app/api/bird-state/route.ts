import { NextResponse } from "next/server";

import {
  isBirdControlMode,
  type BirdControlMode,
} from "@/features/agent/model/bird-state";

interface BirdControlStore {
  mode: BirdControlMode;
  updatedAt: string;
}

const globalStore = globalThis as unknown as {
  __haomengBirdControl?: BirdControlStore;
};

function readStore(): BirdControlStore {
  if (!globalStore.__haomengBirdControl) {
    globalStore.__haomengBirdControl = {
      mode: "auto",
      updatedAt: new Date().toISOString(),
    };
  }
  return globalStore.__haomengBirdControl;
}

export async function GET() {
  const store = readStore();
  return NextResponse.json(
    { mode: store.mode, updated_at: store.updatedAt },
    { headers: { "Cache-Control": "no-store" } },
  );
}

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json(
      { detail: "请求体不是合法的 JSON" },
      { status: 400 },
    );
  }

  const mode = (payload as Record<string, unknown> | null)?.mode;
  if (!isBirdControlMode(mode)) {
    return NextResponse.json(
      { detail: "mode 必须是 auto 或 f1 ~ f5 之一" },
      { status: 400 },
    );
  }

  const store = readStore();
  store.mode = mode;
  store.updatedAt = new Date().toISOString();

  return NextResponse.json({ mode: store.mode, updated_at: store.updatedAt });
}
