const agentBackendUrl = (
  process.env.AGENT_BACKEND_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request) {
  const upstream = await fetch(`${agentBackendUrl}/api/events`, {
    cache: "no-store",
    headers: { Accept: "text/event-stream" },
    signal: request.signal,
  });

  if (!upstream.ok || !upstream.body) {
    return Response.json(
      { detail: "Agent 事件流不可用" },
      { status: upstream.status || 502 },
    );
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "Content-Type": "text/event-stream",
      "X-Accel-Buffering": "no",
    },
  });
}
