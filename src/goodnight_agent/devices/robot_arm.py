"""Panthera 机械臂场景服务的 HTTP 网关。

把后端工具能力映射到 ASUS 上的场景 HTTP 服务（见《机械臂 Agent HTTP 调用契约》）：

- 一次性场景：POST /api/application/<scene>/run 立即返回 202，
  动作在 ASUS 后台运行；网关轮询 /api/status，直到 running 变为 false。
- 持续场景（讲故事）：POST /api/application/plant2/start 开始持续摆动，
  直到调用 POST /api/application/plant2/stop 平滑停止。

约束：
- 同一时间只允许一个动作运行；409 表示机械臂被占用。
- 404 表示轨迹未部署；5xx 表示服务异常。
- 客户端不传关节角度、夹爪参数或 sleep 姿态，回落由 ASUS 侧完成。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

from goodnight_agent.domain.models import (
    DeviceCommand,
    DeviceCommandStatus,
    DeviceStatus,
)

# 一次性动作：能力名 -> (场景名, 触发路径)。
# blanket01/insert02 有契约约定的应用层路由；take_phone02/shake_toy02 在 ASUS 上
# 没有 application 路由（404），走通用回放接口 /api/scenes/{scene}/replay。
ONE_SHOT_SCENES: dict[str, str] = {
    "arm_take_phone": "take_phone02",
    "arm_shake_toy": "shake_toy02",
    "arm_pull_blanket": "blanket01",
    "arm_insert_item": "insert02",
}

ONE_SHOT_TRIGGER_PATHS: dict[str, str] = {
    "arm_take_phone": "/api/scenes/take_phone02/replay",
    "arm_shake_toy": "/api/scenes/shake_toy02/replay",
    "arm_pull_blanket": "/api/application/blanket01/run",
    "arm_insert_item": "/api/application/insert02/run",
}

# 持续动作（讲故事）：start 后持续运行，必须显式 stop
CONTINUOUS_SCENES: dict[str, str] = {
    "arm_storytelling": "plant2",
}

ARM_CAPABILITIES: tuple[str, ...] = tuple(ONE_SHOT_SCENES) + tuple(CONTINUOUS_SCENES)

DEFAULT_BASE_URL = "http://100.67.212.112:8000"

# 轮询状态时允许连续失败的次数，避免一次网络抖动直接判失败
MAX_STATUS_ERRORS = 3


@dataclass
class RobotArmHttpGateway:
    """实现 DeviceGateway 协议，把设备命令转发给机械臂场景 HTTP 服务。"""

    base_url: str = DEFAULT_BASE_URL
    device_id: str = "panthera-arm"
    poll_interval: float = 1.0
    request_timeout: float = 5.0
    # 触发（run/start/stop）单独放宽：实测 ASUS 在启动场景时可能超过 5 秒才回 202
    trigger_timeout: float = 30.0
    client: httpx.AsyncClient | None = None
    statuses: dict[str, DeviceStatus] = field(default_factory=dict)
    _stop_events: dict[str, asyncio.Event] = field(default_factory=dict)

    # ---- DeviceGateway 协议 ----

    async def execute(self, command: DeviceCommand) -> AsyncIterator[DeviceStatus]:
        existing = self.statuses.get(command.command_id)
        if existing is not None and existing.status.terminal:
            yield existing
            return

        stop_event = self._stop_events.setdefault(command.command_id, asyncio.Event())
        yield await self._emit(
            DeviceStatus(
                command_id=command.command_id,
                device_id=command.device_id,
                status=DeviceCommandStatus.ACCEPTED,
                progress=0,
            )
        )

        if command.capability in CONTINUOUS_SCENES:
            inner = self._execute_continuous(command, stop_event)
            try:
                async for status in inner:
                    yield status
            finally:
                # 外层生成器被关闭（超时/取消）时，确定性关闭内层生成器，
                # 让内层 finally 里的 plant2/stop 立即执行。
                await inner.aclose()
            return

        scene = ONE_SHOT_SCENES.get(command.capability)
        if scene is None:
            yield await self._emit(
                self._failure(
                    command, "UNSUPPORTED_CAPABILITY", f"未知机械臂能力 {command.capability}"
                )
            )
            return

        error_code, message = await self._trigger_with_confirm(
            ONE_SHOT_TRIGGER_PATHS[command.capability],
            scene=scene,
            continuous=False,
        )
        if error_code is not None:
            yield await self._emit(self._failure(command, error_code, message or ""))
            return

        yield await self._emit(
            DeviceStatus(
                command_id=command.command_id,
                device_id=command.device_id,
                status=DeviceCommandStatus.EXECUTING,
                progress=0.1,
            )
        )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + command.timeout_ms / 1000
        consecutive_errors = 0
        while True:
            if stop_event.is_set():
                await self._request_arm_stop()
                yield await self._emit(
                    DeviceStatus(
                        command_id=command.command_id,
                        device_id=command.device_id,
                        status=DeviceCommandStatus.STOPPED,
                        message="动作已停止，机械臂按场景配置自动回落",
                    )
                )
                return
            if loop.time() >= deadline:
                await self._request_arm_stop()
                yield await self._emit(
                    self._failure(command, "ARM_TIMEOUT", "等待机械臂动作完成超时")
                )
                return
            await asyncio.sleep(self.poll_interval)
            try:
                payload = await self._arm_status()
                consecutive_errors = 0
            except (httpx.HTTPError, ValueError):
                consecutive_errors += 1
                if consecutive_errors >= MAX_STATUS_ERRORS:
                    yield await self._emit(
                        self._failure(command, "ARM_STATUS_UNKNOWN", "无法读取机械臂运行状态")
                    )
                    return
                continue
            if payload.get("running"):
                continue
            state = str(payload.get("state", ""))
            if state == "failed":
                yield await self._emit(
                    self._failure(command, "ARM_SCENE_FAILED", f"场景 {scene} 回放失败")
                )
                return
            yield await self._emit(
                DeviceStatus(
                    command_id=command.command_id,
                    device_id=command.device_id,
                    status=DeviceCommandStatus.SUCCEEDED,
                    progress=1,
                    result={"facts": {"arm_scene": scene, "arm_state": state}},
                )
            )
            return

    async def get_status(self, command_id: str) -> DeviceStatus | None:
        return self.statuses.get(command_id)

    async def stop(self, command_id: str) -> None:
        self._stop_events.setdefault(command_id, asyncio.Event()).set()

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    # ---- 持续场景（讲故事） ----

    async def _execute_continuous(
        self,
        command: DeviceCommand,
        stop_event: asyncio.Event,
    ) -> AsyncIterator[DeviceStatus]:
        scene = CONTINUOUS_SCENES[command.capability]
        started = False
        try:
            error_code, message = await self._trigger_with_confirm(
                f"/api/application/{scene}/start",
                scene=scene,
                continuous=True,
            )
            if error_code is not None:
                yield await self._emit(self._failure(command, error_code, message or ""))
                return
            started = True
            yield await self._emit(
                DeviceStatus(
                    command_id=command.command_id,
                    device_id=command.device_id,
                    status=DeviceCommandStatus.EXECUTING,
                    progress=None,
                )
            )
            consecutive_errors = 0
            while True:
                if stop_event.is_set():
                    await self._stop_continuous(scene)
                    yield await self._emit(
                        DeviceStatus(
                            command_id=command.command_id,
                            device_id=command.device_id,
                            status=DeviceCommandStatus.STOPPED,
                            message="讲故事已手动停止，机械臂平滑回落",
                        )
                    )
                    return
                await asyncio.sleep(self.poll_interval)
                try:
                    response = await self._http().get(f"/api/application/{scene}/status")
                    response.raise_for_status()
                    payload = response.json()
                    consecutive_errors = 0
                except (httpx.HTTPError, ValueError):
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_STATUS_ERRORS:
                        yield await self._emit(
                            self._failure(command, "ARM_STATUS_UNKNOWN", "无法读取机械臂运行状态")
                        )
                        return
                    continue
                if isinstance(payload, dict) and not payload.get("running", True):
                    yield await self._emit(
                        DeviceStatus(
                            command_id=command.command_id,
                            device_id=command.device_id,
                            status=DeviceCommandStatus.SUCCEEDED,
                            progress=1,
                            result={"facts": {"arm_scene": scene}},
                        )
                    )
                    return
        finally:
            # workflow 超时或 run 被取消时生成器会被关闭；
            # 即使如此也必须通知 ASUS 平滑停止持续场景。
            if started:
                await self._stop_continuous(scene)

    async def _stop_continuous(self, scene: str) -> None:
        try:
            await self._http().post(f"/api/application/{scene}/stop")
        except httpx.HTTPError:
            pass

    # ---- HTTP 辅助 ----

    def _http(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.request_timeout,
            )
        return self.client

    async def _trigger(self, path: str) -> tuple[str | None, str | None]:
        """POST 场景触发接口。返回 (error_code, message)，全 None 表示已接受。"""
        try:
            response = await self._http().post(path, timeout=self.trigger_timeout)
        except httpx.HTTPError as exc:
            detail = str(exc) or type(exc).__name__
            return "ARM_UNREACHABLE", f"机械臂服务连接失败：{detail}"
        if response.status_code == 202:
            return None, None
        if response.status_code == 404:
            return "SCENE_NOT_DEPLOYED", "场景轨迹未在 ASUS 上部署"
        if response.status_code == 409:
            return "ARM_BUSY", "机械臂已被其他动作或持续场景占用"
        if response.status_code >= 500:
            return "ARM_SERVICE_ERROR", f"机械臂服务异常，HTTP {response.status_code}"
        return "ARM_UNEXPECTED_RESPONSE", f"机械臂服务返回 HTTP {response.status_code}"

    async def _trigger_with_confirm(
        self,
        path: str,
        *,
        scene: str,
        continuous: bool,
    ) -> tuple[str | None, str | None]:
        """触发场景；POST 超时/失败时回查状态，避免"实际已启动却报失败"。"""
        error_code, message = await self._trigger(path)
        if error_code != "ARM_UNREACHABLE":
            return error_code, message
        await asyncio.sleep(1)
        try:
            if continuous:
                response = await self._http().get(f"/api/application/{scene}/status")
                response.raise_for_status()
                payload = response.json()
                running = isinstance(payload, dict) and bool(payload.get("running"))
            else:
                payload = await self._arm_status()
                running = bool(payload.get("running")) and payload.get("scene") in {
                    scene,
                    None,
                }
        except (httpx.HTTPError, ValueError):
            return error_code, message
        if running:
            return None, None
        return error_code, message

    async def _arm_status(self) -> dict[str, object]:
        response = await self._http().get("/api/status")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "running" not in payload:
            raise ValueError(f"机械臂状态响应格式不正确: {payload!r}")
        return payload

    async def _request_arm_stop(self) -> None:
        try:
            await self._http().post("/api/arm/stop")
        except httpx.HTTPError:
            pass

    async def _emit(self, status: DeviceStatus) -> DeviceStatus:
        self.statuses[status.command_id] = status
        return status

    def _failure(self, command: DeviceCommand, error_code: str, message: str) -> DeviceStatus:
        return DeviceStatus(
            command_id=command.command_id,
            device_id=command.device_id,
            status=DeviceCommandStatus.FAILED,
            error_code=error_code,
            message=message,
        )
