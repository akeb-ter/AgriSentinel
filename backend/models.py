"""
AgriSentinel Backend - Pydantic Schemas & Telemetry Models
Defines data structures for system telemetry, pest detections, and remote control commands.
"""

from typing import Optional
from pydantic import BaseModel, Field


class SystemTelemetry(BaseModel):
    """Real-time robot status and telemetry model."""
    mode: str = Field(..., description="Operating mode: AUTO or MANUAL")
    motor_state: str = Field(..., description="Motor state: STOPPED, FORWARD, REVERSE, LEFT, RIGHT")
    front_obstacle_cm: float = Field(..., description="Primary Front ultrasonic sensor distance in cm")
    rear_obstacle_cm: float = Field(..., description="Secondary Rear ultrasonic sensor distance in cm")
    obstacle_distance_cm: float = Field(..., description="Legacy front obstacle distance metric in cm")
    camera_pan_angle: float = Field(..., description="Pan-tilt servo angle in degrees (-60 to +60)")
    latitude: float = Field(default=0.0, description="GPS latitude field coordinate")
    longitude: float = Field(default=0.0, description="GPS longitude field coordinate")
    altitude: Optional[float] = Field(default=0.0, description="GPS altitude in meters")
    gps_fix: bool = Field(default=False, description="GPS satellite fix indicator")
    satellites: Optional[int] = Field(default=0, description="Number of connected GPS satellites")
    active_frequency_hz: Optional[float] = Field(default=0.0, description="Active dynamic repellent signal in Hz")
    timestamp: float = Field(..., description="Epoch timestamp of telemetry snapshot")


class PestDetectionEvent(BaseModel):
    """Pest detection event payload."""
    pest_class: str = Field(..., description="Detected pest species class")
    confidence: float = Field(..., description="FOMO model detection confidence (0.0 - 1.0)")
    latitude: float = Field(default=0.0, description="Field latitude coordinate of detection")
    longitude: float = Field(default=0.0, description="Field longitude coordinate of detection")
    active_frequency_hz: float = Field(..., description="Repellent frequency emitted")
    timestamp: float = Field(..., description="Epoch timestamp of detection")


class MotorControlCommand(BaseModel):
    """Remote control direction command."""
    command: str = Field(..., description="Command string: FORWARD, REVERSE, LEFT, RIGHT, STOP")
    speed_pwm: Optional[int] = Field(default=255, ge=0, le=255, description="PWM motor duty cycle")

