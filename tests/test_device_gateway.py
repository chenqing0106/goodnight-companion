import pytest

from goodnight_agent.devices.memory import InMemoryDeviceGateway
from goodnight_agent.domain.models import DeviceCommand, DeviceCommandStatus


@pytest.mark.asyncio
async def test_duplicate_command_is_not_executed_twice() -> None:
    gateway = InMemoryDeviceGateway(step_delay=0)
    command = DeviceCommand(
        command_id="cmd_stable",
        action_id="act_test",
        device_id="mock-arm",
        capability="turn_off_light",
    )

    first = [status async for status in gateway.execute(command)]
    second = [status async for status in gateway.execute(command)]

    assert first[-1].status is DeviceCommandStatus.SUCCEEDED
    assert [status.status for status in second] == [DeviceCommandStatus.SUCCEEDED]
    assert gateway.execution_count[command.command_id] == 1
