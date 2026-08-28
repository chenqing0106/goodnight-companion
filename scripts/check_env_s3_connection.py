from __future__ import annotations

import argparse
import asyncio
import json
import os

from goodnight_agent.devices.env_s3 import EnvS3MqttGateway
from goodnight_agent.domain.models import DeviceCommand


async def check_connection(args: argparse.Namespace) -> None:
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
        print(json.dumps(device.model_dump(mode="json"), ensure_ascii=False))
        print(json.dumps([item.model_dump(mode="json") for item in readings], ensure_ascii=False))

        commands = []
        if args.rgb_mode is not None:
            commands.append(("set_rgb_indicator", args.rgb_mode))
        if args.led_mode is not None:
            commands.append(("set_led_mode", args.led_mode))
        for capability, mode in commands:
            command = DeviceCommand(
                action_id="manual_env_s3_check",
                device_id=args.device_id,
                capability=capability,
                parameters={"mode": mode},
                timeout_ms=int(args.wait * 1000),
            )
            statuses = [status async for status in gateway.execute(command)]
            print(
                json.dumps(
                    [status.model_dump(mode="json") for status in statuses],
                    ensure_ascii=False,
                )
            )
    finally:
        await gateway.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="检查 ENV-S3 MQTT 状态、传感器和执行器")
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
    parser.add_argument("--wait", type=float, default=3)
    parser.add_argument("--rgb-mode", type=int, choices=range(4))
    parser.add_argument("--led-mode", type=int, choices=range(8))
    asyncio.run(check_connection(parser.parse_args()))


if __name__ == "__main__":
    main()
