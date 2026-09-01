"""
AgriSentinel - Main Autonomous Control Loop

Coordinates motor navigation, ultrasonic obstacle avoidance, camera servo panning,
and telemetry reporting for autonomous crop protection operations.
"""

import os
import sys
import time
import logging
from typing import Dict, Any

from edge.drivers.servo import ServoController

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgriSentinel-Robot")

OBSTACLE_CLEARANCE_THRESHOLD_CM = float(os.getenv("OBSTACLE_CLEARANCE_CM", "30.0"))
LOOP_INTERVAL_SEC = float(os.getenv("LOOP_INTERVAL_SEC", "0.2"))


class RobotController:
    """Main Robot Autonomous Controller Coordinating Subsystems."""

    def __init__(self):
        self.mode = "AUTO"  # "AUTO" or "MANUAL"
        self.motor_state = "STOPPED"
        self.obstacle_distance_cm = 100.0
        self.pan_angle = 0.0

        # Drivers
        self.servo = ServoController()
        logger.info("[RobotController] Initialized robot control loop.")

    def update_sensors(self):
        """Simulates/reads sensor telemetry (Ultrasonic distance & Camera pan sweep)."""
        # Advance camera pan sweep angle during autonomous scan
        self.pan_angle = self.servo.sweep_step()

    def process_autonomous_navigation(self):
        """Executes collision avoidance and motor navigation logic."""
        if self.mode != "AUTO":
            return

        if self.obstacle_distance_cm < OBSTACLE_CLEARANCE_THRESHOLD_CM:
            if self.motor_state != "STOPPED":
                logger.warning(
                    f"[RobotController] Obstacle detected ({self.obstacle_distance_cm:.1f} cm)! Stopping motors."
                )
                self.motor_state = "STOPPED"
        else:
            if self.motor_state != "FORWARD":
                logger.info("[RobotController] Path clear. Moving forward.")
                self.motor_state = "FORWARD"

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns unified system telemetry payload."""
        return {
            "mode": self.mode,
            "motor_state": self.motor_state,
            "obstacle_distance_cm": self.obstacle_distance_cm,
            "camera_pan_angle": self.pan_angle,
            "timestamp": time.time(),
        }

    def run_step(self):
        """Executes one iteration of the control loop."""
        self.update_sensors()
        self.process_autonomous_navigation()

    def shutdown(self):
        """Cleans up hardware driver resources."""
        logger.info("[RobotController] Shutting down robot subsystems.")
        self.servo.center()
        self.servo.close()


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

