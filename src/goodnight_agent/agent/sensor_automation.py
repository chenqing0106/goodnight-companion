from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

from goodnight_agent.agent.workflow import SimpleWorkflow
from goodnight_agent.devices.base import SensorEventSource
from goodnight_agent.domain.models import (
    ActionStatus,
    DomainEvent,
    Observation,
    SensorReading,
    new_id,
    utc_now,
)
from goodnight_agent.infrastructure.events import EventPublisher


@dataclass
class VitalsSignalAutomation:
    source: SensorEventSource
    workflow: SimpleWorkflow
    publisher: EventPublisher
    device_id: str
    required_samples: int = 3
    freshness_seconds: float = 5
    pair_window_ms: int = 2_000
    cooldown_seconds: float = 10
    reconnect_delay_seconds: float = 2
    _latest: dict[str, SensorReading] = field(default_factory=dict, init=False)
    _consumed_ts: dict[str, int] = field(default_factory=dict, init=False)
    _outcome: str = field(default="unknown", init=False)
    _streak: int = field(default=0, init=False)
    _last_target_mode: int | None = field(default=None, init=False)
    _last_attempt_at: float | None = field(default=None, init=False)

    async def run(self) -> None:
        await self.publisher.publish(
            DomainEvent(
                event_type="automation.started",
                payload={
                    "rule": "vitals_signal_indicator",
                    "device_id": self.device_id,
                    "required_samples": self.required_samples,
                },
            )
        )
        while True:
            try:
                async for reading in self.source.subscribe_sensor_readings(self.device_id):
                    await self.handle(reading)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - transport adapters vary
                await self.publisher.publish(
                    DomainEvent(
                        event_type="automation.connection_failed",
                        payload={
                            "rule": "vitals_signal_indicator",
                            "device_id": self.device_id,
                            "error": str(exc),
                        },
                    )
                )
                await asyncio.sleep(self.reconnect_delay_seconds)

    async def handle(self, reading: SensorReading) -> None:
        if reading.device_id != self.device_id or reading.sensor not in {
            "heart_rate",
            "spo2",
        }:
            return
        previous_ts = self._consumed_ts.get(reading.sensor)
        if previous_ts is not None and reading.ts_ms < previous_ts:
            self._consumed_ts.clear()
        self._latest[reading.sensor] = reading

        heart_rate = self._latest.get("heart_rate")
        spo2 = self._latest.get("spo2")
        if heart_rate is None or spo2 is None:
            return
        if heart_rate.ts_ms <= self._consumed_ts.get("heart_rate", -1):
            return
        if spo2.ts_ms <= self._consumed_ts.get("spo2", -1):
            return
        if abs(heart_rate.ts_ms - spo2.ts_ms) > self.pair_window_ms:
            return

        self._consumed_ts = {
            "heart_rate": heart_rate.ts_ms,
            "spo2": spo2.ts_ms,
        }
        outcome, reason = self._classify_pair(heart_rate, spo2)
        if outcome == self._outcome:
            self._streak += 1
        else:
            self._outcome = outcome
            self._streak = 1

        if self._streak <= self.required_samples:
            await self.publisher.publish(
                DomainEvent(
                    event_type="condition.evaluated",
                    payload={
                        "rule": "vitals_signal_indicator",
                        "device_id": self.device_id,
                        "outcome": outcome,
                        "reason": reason,
                        "consecutive_samples": self._streak,
                        "required_samples": self.required_samples,
                    },
                )
            )

        target_mode = {"stable": 2, "finger_not_detected": 0}.get(outcome)
        if target_mode is None or self._streak < self.required_samples:
            return
        if target_mode == self._last_target_mode or self._cooldown_active():
            return

        self._last_attempt_at = asyncio.get_running_loop().time()
        run_id = new_id("run")
        await self.publisher.publish(
            DomainEvent(
                event_type="condition.satisfied",
                run_id=run_id,
                payload={
                    "rule": "vitals_signal_indicator",
                    "device_id": self.device_id,
                    "outcome": outcome,
                    "reason": reason,
                    "consecutive_samples": self._streak,
                    "target": {
                        "capability": "set_rgb_indicator",
                        "parameters": {"mode": target_mode},
                    },
                },
            )
        )
        result = await self.workflow.process_observation(
            Observation(
                source="env_s3_sensor_automation",
                facts={
                    "vitals_signal_state": outcome,
                    "vitals_valid_streak": self._streak,
                    "vitals_reason": reason,
                },
            ),
            run_id=run_id,
        )
        action_succeeded = any(
            action.status is ActionStatus.SUCCEEDED for action in result.actions
        )
        already_applied = result.decision is not None and not result.decision.should_intervene
        if action_succeeded or already_applied:
            self._last_target_mode = target_mode

    def _classify_pair(
        self,
        heart_rate: SensorReading,
        spo2: SensorReading,
    ) -> tuple[str, str]:
        freshness = timedelta(seconds=self.freshness_seconds)
        now = utc_now()
        if now - heart_rate.received_at > freshness or now - spo2.received_at > freshness:
            return "collecting", "stale_reading"
        if heart_rate.valid and spo2.valid:
            return "stable", "heart_rate_and_spo2_valid"
        if (
            not heart_rate.valid
            and not spo2.valid
            and heart_rate.error == "finger_not_detected"
            and spo2.error == "finger_not_detected"
        ):
            return "finger_not_detected", "finger_not_detected"
        return "collecting", heart_rate.error or spo2.error or "signal_unstable"

    def _cooldown_active(self) -> bool:
        if self._last_attempt_at is None:
            return False
        elapsed = asyncio.get_running_loop().time() - self._last_attempt_at
        return elapsed < self.cooldown_seconds
