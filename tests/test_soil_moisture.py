"""
Tests for Soil Moisture Sensor driver and status classification.
"""

from edge.drivers.soil_moisture import SoilMoistureSensor


def test_soil_sensor_mock_reading():
    """Verify mock soil sensor produces valid volumetric percentage and status."""
    sensor = SoilMoistureSensor(adc_type="mock")
    data = sensor.read_moisture()

    assert "moisture_percent" in data
    assert "status" in data
    assert "timestamp" in data
    assert 0.0 <= data["moisture_percent"] <= 100.0
    assert data["status"] in ("Dry", "Optimal", "Waterlogged")


def test_soil_sensor_classification_thresholds():
    """Verify correct status classification based on moisture levels."""
    sensor = SoilMoistureSensor(adc_type="mock")

    # Dry: < 25%
    sensor.set_mock_moisture(15.0)
    res_dry = sensor.read_moisture()
    assert res_dry["status"] == "Dry"

    # Optimal: 25% - 75%
    sensor.set_mock_moisture(55.0)
    res_opt = sensor.read_moisture()
    assert res_opt["status"] == "Optimal"

    # Waterlogged: > 75%
    sensor.set_mock_moisture(88.0)
    res_wet = sensor.read_moisture()
    assert res_wet["status"] == "Waterlogged"

