from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt

from goodnight_agent.domain.models import (
    DeviceCommand,
    DeviceCommandStatus,
    DeviceStatus,
)


@dataclass
class MockDevice:
    host: str
    port: int
    device_id: str
    base_topic: str
    step_delay: float
    client: mqtt.Client = field(init=False)
    terminal_cache: dict[str, DeviceStatus] = field(default_factory=dict, init=False)
    active_stops: dict[str, threading.Event] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"goodnight-mock-{self.device_id}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.will_set(
            self._topic("availability"),
            json.dumps({"status": "offline"}),
            qos=1,
            retain=True,
        )

    def _topic(self, suffix: str) -> str:
        return f"{self.base_topic}/{self.device_id}/{suffix}"

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code != 0:
            print(f"连接失败: {reason_code}")
            return
        client.subscribe(self._topic("command"), qos=1)
        client.publish(
            self._topic("availability"),
            json.dumps({"status": "online"}),
            qos=1,
            retain=True,
        )
        client.publish(
            self._topic("capabilities"),
            json.dumps(
                {
                    "capabilities": [
                        "move_phone_to_dock",
                        "turn_off_light",
                        "stop_all_motion",
                    ]
                }
            ),
            qos=1,
            retain=True,
        )
        print(f"模拟设备已上线: {self.device_id}")

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            command = DeviceCommand.model_validate_json(message.payload)
        except ValueError as exc:
            print(f"忽略非法指令: {exc}")
            return

        cached = self.terminal_cache.get(command.command_id)
        if cached is not None:
            self._publish(cached)
            return

        if command.capability == "stop_all_motion":
            target = command.parameters.get("target_command_id")
            if isinstance(target, str):
                self.active_stops.setdefault(target, threading.Event()).set()
            stopped = DeviceStatus(
                command_id=command.command_id,
                device_id=self.device_id,
                status=DeviceCommandStatus.SUCCEEDED,
                result={"target_command_id": target},
            )
            self.terminal_cache[command.command_id] = stopped
            self._publish(stopped)
            return

        threading.Thread(target=self._execute, args=(command,), daemon=True).start()

    def _execute(self, command: DeviceCommand) -> None:
        stop_event = self.active_stops.setdefault(command.command_id, threading.Event())
        self._publish_status(command, DeviceCommandStatus.ACCEPTED, progress=0)
        time.sleep(self.step_delay)
        if self._publish_stopped_if_needed(command, stop_event):
            return

        self._publish_status(command, DeviceCommandStatus.EXECUTING, progress=0.5)
        if command.parameters.get("simulate_timeout") is True:
            return

        time.sleep(self.step_delay)
        if self._publish_stopped_if_needed(command, stop_event):
            return

        if command.parameters.get("simulate_failure") is True:
            self._publish_status(
                command,
                DeviceCommandStatus.FAILED,
                error_code="SIMULATED_FAILURE",
                message="模拟设备执行失败",
            )
            return

        facts: dict[str, object] = {}
        if command.capability == "move_phone_to_dock":
            facts["phone_location"] = "dock"
        elif command.capability == "turn_off_light":
            facts["light_on"] = False
        self._publish_status(
            command,
            DeviceCommandStatus.SUCCEEDED,
            progress=1,
            result={"facts": facts},
        )

    def _publish_stopped_if_needed(
        self,
        command: DeviceCommand,
        stop_event: threading.Event,
    ) -> bool:
        if not stop_event.is_set():
            return False
        self._publish_status(
            command,
            DeviceCommandStatus.STOPPED,
            message="收到停止动作指令",
        )
        return True

    def _publish_status(
        self,
        command: DeviceCommand,
        status: DeviceCommandStatus,
        **updates: object,
    ) -> None:
        self._publish(
            DeviceStatus(
                command_id=command.command_id,
                device_id=self.device_id,
                status=status,
                **updates,
            )
        )

    def _publish(self, status: DeviceStatus) -> None:
        if status.status.terminal:
            self.terminal_cache[status.command_id] = status
        self.client.publish(
            self._topic("command/status"),
            status.model_dump_json(),
            qos=1,
            retain=False,
        )
        print(f"{status.command_id}: {status.status}")

    def run(self) -> None:
        self.client.connect(self.host, self.port)
        self.client.loop_forever()

    def shutdown(self) -> None:
        self.client.publish(
            self._topic("availability"),
            json.dumps({"status": "offline"}),
            qos=1,
            retain=True,
        )
        self.client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="好梦鸟 MQTT 模拟设备")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="mock-arm")
    parser.add_argument("--base-topic", default="goodnight")
    parser.add_argument("--step-delay", type=float, default=0.5)
    args = parser.parse_args()

    device = MockDevice(
        host=args.host,
        port=args.port,
        device_id=args.device_id,
        base_topic=args.base_topic,
        step_delay=args.step_delay,
    )
    signal.signal(signal.SIGTERM, lambda *_: device.shutdown())
    try:
        device.run()
    except KeyboardInterrupt:
        device.shutdown()


if __name__ == "__main__":
    main()
