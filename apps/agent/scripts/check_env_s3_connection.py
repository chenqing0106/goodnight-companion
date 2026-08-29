from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

from goodnight_agent.devices.env_s3 import EnvS3MqttGateway
from goodnight_agent.domain.models import (
    DeviceAvailability,
    DeviceCommand,
    DeviceRecord,
    DeviceStatus,
    SensorReading,
)

_SENSOR_ORDER = ["temp", "humidity", "light", "heart_rate", "spo2"]
_SENSOR_LABELS = {
    "temp": "温度",
    "humidity": "湿度",
    "light": "光敏",
    "heart_rate": "心率",
    "spo2": "血氧",
}


async def check_connection(args: argparse.Namespace) -> int:
    gateway = EnvS3MqttGateway(
        host=args.host,
        port=args.port,
        device_id=args.device_id,
        username=os.getenv("GOODNIGHT_MQTT_USERNAME"),
        password=os.getenv("GOODNIGHT_MQTT_PASSWORD"),
        registry_wait_timeout=args.wait,
    )
    try:
        device = await gateway.get_device(args.device_id)
        readings = await gateway.list_sensor_readings(args.device_id)
        if readings and args.collect_seconds > 0:
            await asyncio.sleep(args.collect_seconds)
            readings = await gateway.list_sensor_readings(args.device_id)

        statuses: list[DeviceStatus] = []
        commands: list[tuple[str, int]] = []
        if args.rgb_mode is not None:
            commands.append(("set_rgb_indicator", args.rgb_mode))
        if args.led_mode is not None:
            commands.append(("set_led_mode", args.led_mode))
        if commands and device is not None and device.availability is DeviceAvailability.ONLINE:
            for capability, mode in commands:
                command = DeviceCommand(
                    action_id="manual_env_s3_check",
                    device_id=args.device_id,
                    capability=capability,
                    parameters={"mode": mode},
                    timeout_ms=int(args.wait * 1000),
                )
                statuses.extend([status async for status in gateway.execute(command)])

        missing = sorted(set(_SENSOR_ORDER) - {reading.sensor for reading in readings})
        if args.json:
            _print_json_report(device, readings, missing, statuses)
        else:
            _print_human_report(device, readings, missing, statuses, commands)
        unhealthy = (
            device is None
            or device.availability is not DeviceAvailability.ONLINE
            or bool(missing)
        )
        return int(args.strict and unhealthy)
    finally:
        await gateway.close()


def _print_human_report(
    device: DeviceRecord | None,
    readings: list[SensorReading],
    missing: list[str],
    statuses: list[DeviceStatus],
    commands: list[tuple[str, int]],
) -> None:
    availability = device.availability if device is not None else DeviceAvailability.UNKNOWN
    print(f"设备 {device.device_id if device else 'unknown'}: {availability}")
    reading_by_sensor = {reading.sensor: reading for reading in readings}
    for sensor in _SENSOR_ORDER:
        label = _SENSOR_LABELS[sensor]
        reading = reading_by_sensor.get(sensor)
        if reading is None:
            print(f"- {label}: 未收到")
        elif reading.valid:
            print(
                f"- {label}: {reading.value:g} {reading.unit}，有效，"
                f"接收于 {reading.received_at.isoformat(timespec='seconds')}"
            )
        else:
            print(f"- {label}: 无效，原因 {reading.error or 'unknown'}")
    if missing:
        print("缺失 Topic: " + ", ".join(f"sensor/{sensor}" for sensor in missing))
    if commands and availability is not DeviceAvailability.ONLINE:
        print("设备不在线，已跳过执行器命令。")
    for status in statuses:
        print(
            f"执行器回执: {status.status} "
            f"{json.dumps(status.result, ensure_ascii=False)}"
        )


def _print_json_report(
    device: DeviceRecord | None,
    readings: list[SensorReading],
    missing: list[str],
    statuses: list[DeviceStatus],
) -> None:
    report: dict[str, Any] = {
        "device": device.model_dump(mode="json") if device is not None else None,
        "readings": [reading.model_dump(mode="json") for reading in readings],
        "missing_sensors": missing,
        "command_statuses": [status.model_dump(mode="json") for status in statuses],
    }
    print(json.dumps(report, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="检查 ENV-S3 MQTT 在线状态和传感器")
    parser.add_argument("--host", default=os.getenv("GOODNIGHT_MQTT_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("GOODNIGHT_MQTT_PORT", "1883")),
    )
    parser.add_argument(
        "--device-id",
        default=os.getenv("GOODNIGHT_MQTT_DEVICE_ID", "env-s3-01"),
    )
    parser.add_argument("--wait", type=float, default=5, help="等待状态或首条数据的秒数")
    parser.add_argument(
        "--collect-seconds",
        type=float,
        default=3,
        help="收到首条数据后继续收集完整传感器快照的秒数",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--strict", action="store_true", help="离线或传感器缺失时返回非零状态")
    parser.add_argument("--rgb-mode", type=int, choices=range(4))
    parser.add_argument("--led-mode", type=int, choices=(0, 7, 8, 9))
    try:
        exit_code = asyncio.run(check_connection(parser.parse_args()))
    except TimeoutError:
        print("连接 MQTT Broker 超时，请检查网络、地址和认证配置。")
        raise SystemExit(2) from None
    except OSError as exc:
        print(f"连接 MQTT Broker 失败: {exc}")
        raise SystemExit(2) from None
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
