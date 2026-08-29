from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt

_RGB_STATES = {0: "off", 1: "red", 2: "green", 3: "blue"}
_LED_STATES = {
    0: "off",
    7: "mode_7",
    8: "mode_8",
    9: "mode_9",
}


@dataclass
class MockEnvS3Device:
    host: str
    port: int
    device_id: str
    username: str | None = None
    password: str | None = None
    client: mqtt.Client = field(init=False)
    stopped: threading.Event = field(default_factory=threading.Event, init=False)
    started_at: float = field(default_factory=time.monotonic, init=False)

    def __post_init__(self) -> None:
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"mock-{self.device_id}",
        )
        if self.username:
            self.client.username_pw_set(self.username, self.password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.will_set(
            self._topic("status"),
            json.dumps({"state": "offline"}),
            qos=1,
            retain=True,
        )

    def _topic(self, suffix: str) -> str:
        return f"{self.device_id}/{suffix}"

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
        client.subscribe(self._topic("actuator/rgb/set"), qos=1)
        client.subscribe(self._topic("actuator/led/set"), qos=1)
        client.publish(
            self._topic("status"),
            json.dumps({"state": "online"}),
            qos=1,
            retain=True,
        )
        print(f"ENV-S3 模拟设备已上线: {self.device_id}")

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        if message.topic == self._topic("actuator/rgb/set"):
            self._handle_actuator("rgb", message.payload, _RGB_STATES)
        elif message.topic == self._topic("actuator/led/set"):
            self._handle_actuator("led", message.payload, _LED_STATES)

    def _handle_actuator(
        self,
        actuator: str,
        raw_payload: bytes,
        states: dict[int, str],
    ) -> None:
        try:
            payload = raw_payload.decode("utf-8")
        except UnicodeDecodeError:
            payload = ""
        if len(payload) != 1 or not payload.isascii() or not payload.isdigit():
            self._publish_rejection(actuator, f"payload_must_be_0_to_{max(states)}")
            return
        command = int(payload)
        if command not in states:
            self._publish_rejection(actuator, f"payload_must_be_0_to_{max(states)}")
            return
        self.client.publish(
            self._topic(f"actuator/{actuator}/state"),
            json.dumps(
                {"accepted": True, "command": command, "state": states[command]},
                separators=(",", ":"),
            ),
            qos=1,
            retain=False,
        )
        print(f"{actuator} -> {states[command]}")

    def _publish_rejection(self, actuator: str, reason: str) -> None:
        self.client.publish(
            self._topic(f"actuator/{actuator}/state"),
            json.dumps({"accepted": False, "reason": reason}, separators=(",", ":")),
            qos=1,
            retain=False,
        )

    def _publish_sensors(self) -> None:
        values = {
            "temp": (25.0, "C"),
            "humidity": (52.0, "%RH"),
            "light": (900, "adc_count"),
            "heart_rate": (72, "bpm"),
            "spo2": (98, "%"),
        }
        while not self.stopped.wait(1):
            ts_ms = int((time.monotonic() - self.started_at) * 1000)
            for sensor, (value, unit) in values.items():
                self.client.publish(
                    self._topic(f"sensor/{sensor}"),
                    json.dumps(
                        {"value": value, "unit": unit, "valid": True, "ts_ms": ts_ms},
                        separators=(",", ":"),
                    ),
                    qos=0,
                    retain=False,
                )

    def run(self) -> None:
        self.client.connect(self.host, self.port)
        threading.Thread(target=self._publish_sensors, daemon=True).start()
        self.client.loop_forever()

    def shutdown(self) -> None:
        if self.stopped.is_set():
            return
        self.stopped.set()
        self.client.publish(
            self._topic("status"),
            json.dumps({"state": "offline"}),
            qos=1,
            retain=True,
        )
        self.client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="ENV-SENSING-S3 MQTT 模拟设备")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="env-s3-01")
    parser.add_argument("--username")
    parser.add_argument("--password")
    args = parser.parse_args()

    device = MockEnvS3Device(
        host=args.host,
        port=args.port,
        device_id=args.device_id,
        username=args.username,
        password=args.password,
    )
    signal.signal(signal.SIGTERM, lambda *_: device.shutdown())
    try:
        device.run()
    except KeyboardInterrupt:
        device.shutdown()


if __name__ == "__main__":
    main()
