"""
AgriSentinel - Main Autonomous Control Loop

Coordinates motor navigation, dual ultrasonic obstacle avoidance (Front & Rear),
GY-NEO6MV2 GPS telemetry streaming, camera servo panning, and telemetry reporting.
"""

import os
import sys
import time
import logging
from typing import Dict, Any

from edge.drivers.servo import ServoController
from edge.drivers.ultrasonic import FrontSensor, RearSensor, DualUltrasonicSensors
from edge.drivers.gps import GPSReader
from edge.drivers.motors import MotorController

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgriSentinel-Robot")

OBSTACLE_CLEARANCE_THRESHOLD_CM = float(os.getenv("OBSTACLE_CLEARANCE_CM", "30.0"))
LOOP_INTERVAL_SEC = float(os.getenv("LOOP_INTERVAL_SEC", "0.2"))


class RobotController:
    """Main Robot Autonomous Controller Coordinating Subsystems with Bidirectional Failsafe."""

    def __init__(self):
        self.mode = "AUTO"  # "AUTO" or "MANUAL"
        self.front_obstacle_cm = 100.0
        self.rear_obstacle_cm = 100.0
        self.pan_angle = 0.0

        # Hardware Drivers
        self.motors = MotorController()
        self.servo = ServoController()
        self.ultrasonics = DualUltrasonicSensors()
        self.gps = GPSReader()

        logger.info("[RobotController] Initialized robot control loop with motors, dual ultrasonic, and GPS drivers.")

    def update_sensors(self):
        """Reads sensor telemetry (Dual Ultrasonic distance, GPS, & Camera pan sweep)."""
        # Advance camera pan sweep angle during autonomous scan
        self.pan_angle = self.servo.sweep_step()

        # Read Front & Rear Distance Sensors
        clearance = self.ultrasonics.read_clearance()
        self.front_obstacle_cm = clearance["front_obstacle_cm"]
        self.rear_obstacle_cm = clearance["rear_obstacle_cm"]

    def process_autonomous_navigation(self):
        """Executes bidirectional collision avoidance and motor navigation logic."""
        if self.mode != "AUTO":
            return

        current_state = self.motors.get_state()

        # Bidirectional Failsafe Rules (30.0 cm threshold)
        if current_state == "FORWARD" and self.front_obstacle_cm < OBSTACLE_CLEARANCE_THRESHOLD_CM:
            logger.warning(
                f"[RobotController] Front obstacle detected ({self.front_obstacle_cm:.1f} cm)! Stopping motors."
            )
            self.motors.stop()
        elif current_state == "REVERSE" and self.rear_obstacle_cm < OBSTACLE_CLEARANCE_THRESHOLD_CM:
            logger.warning(
                f"[RobotController] Rear obstacle detected ({self.rear_obstacle_cm:.1f} cm)! Stopping motors."
            )
            self.motors.stop()
        elif current_state == "STOPPED":
            if self.front_obstacle_cm >= OBSTACLE_CLEARANCE_THRESHOLD_CM:
                logger.info("[RobotController] Front path clear. Moving forward.")
                self.motors.forward()
            elif self.rear_obstacle_cm >= OBSTACLE_CLEARANCE_THRESHOLD_CM:
                logger.info("[RobotController] Front blocked. Performing reverse correction maneuver.")
                self.motors.backward()

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns unified system telemetry payload including dual clearance & GPS tags."""
        gps_data = self.gps.read_gps_data()
        return {
            "mode": self.mode,
            "motor_state": self.motors.get_state(),
            "front_obstacle_cm": self.front_obstacle_cm,
            "rear_obstacle_cm": self.rear_obstacle_cm,
            "obstacle_distance_cm": self.front_obstacle_cm,  # Legacy field compatibility
            "camera_pan_angle": self.pan_angle,
            "latitude": gps_data["latitude"],
            "longitude": gps_data["longitude"],
            "altitude": gps_data["altitude"],
            "gps_fix": gps_data["gps_fix"],
            "satellites": gps_data["satellites"],
            "timestamp": time.time(),
        }

    def run_step(self):
        """Executes one iteration of the control loop."""
        self.update_sensors()
        self.process_autonomous_navigation()

    def shutdown(self):
        """Cleans up hardware driver resources."""
        logger.info("[RobotController] Shutting down robot subsystems.")
        self.motors.cleanup()
        self.servo.center()
        self.servo.close()
        self.ultrasonics.cleanup()
        self.gps.close()


def main():
    """CLI Entry point for running main robot loop."""
    logger.info("Starting AgriSentinel Main Control Loop...")
    robot = RobotController()

    try:
        for step in range(20):
            robot.run_step()
            telemetry = robot.get_telemetry()
            logger.info(f"Step {step+1:02d} | Telemetry: {telemetry}")
            time.sleep(LOOP_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Control loop interrupted by user.")
    finally:
        robot.shutdown()


if __name__ == "__main__":
    main()
