"""
AgriSentinel Backend - Pydantic Schemas & Telemetry Models

Defines modern schemas for probe telemetry, soil moisture readings,
pest detections, plant health evaluations, and agricultural pesticide recommendations.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SoilMoistureReading(BaseModel):
    """Real-time Soil Moisture sensor telemetry."""
    moisture_percent: float = Field(..., ge=0.0, le=100.0, description="Volumetric soil moisture percentage (0-100%)")
    raw_adc: Optional[int] = Field(default=None, description="Raw ADC count from ADS1115/MCP3008 if available")
    voltage: Optional[float] = Field(default=None, description="Measured analog voltage in Volts")
    status: str = Field(..., description="Moisture classification: Dry, Optimal, or Waterlogged")
    timestamp: float = Field(..., description="Epoch timestamp of sensor reading")


class ProbeTelemetry(BaseModel):
    """Real-time status and operational telemetry for the AgriSentinel probe stick."""
    probe_id: str = Field(default="PROBE-01", description="Unique identifier for the probe hardware")
    active_crop: str = Field(default="corn", description="Currently selected crop (mungbean, squash, eggplant, corn)")
    farm_area: str = Field(default="Plot 1 - North Field", description="Assigned farm plot or monitoring zone")
    camera_active: bool = Field(default=True, description="Indicates if the imaging camera subsystem is active")
    soil_moisture_percent: float = Field(default=50.0, description="Latest soil moisture percentage")
    soil_status: str = Field(default="Optimal", description="Soil status: Dry, Optimal, Waterlogged")
    latest_pest: Optional[str] = Field(default=None, description="Most recently detected pest species")
    latest_pest_count: int = Field(default=0, description="Pest count detected in latest scan")
    infestation_level: str = Field(default="None", description="Infestation rating: None, Low, Moderate, Severe")
    plant_health_status: str = Field(default="Healthy", description="Integrated plant health assessment")
    timestamp: float = Field(..., description="Epoch timestamp of telemetry snapshot")


class PesticideRecommendation(BaseModel):
    """Pest-specific pesticide and agricultural management recommendation."""
    pest_name: str = Field(..., description="Target pest common name")
    scientific_name: Optional[str] = Field(default="", description="Scientific pest taxonomy")
    crop_type: str = Field(..., description="Target host crop")
    chemical_product: str = Field(..., description="Recommended chemical insecticide brand/active ingredient")
    chemical_dosage: str = Field(..., description="Recommended application dosage and mixing instructions")
    phi_days: int = Field(default=0, description="Pre-Harvest Interval (PHI) in days")
    organic_alternative: str = Field(..., description="Biological control or organic alternative")
    organic_dosage: str = Field(..., description="Organic dosage and application guidance")
    safety_precautions: str = Field(..., description="PPE requirements and environmental safety precautions")
    confidence: float = Field(..., ge=0.0, le=1.0, description="AI detection confidence (0.0 to 1.0)")
    is_uncertain: bool = Field(default=False, description="True if confidence is borderline (40-69%) requiring caution")


class DetectionRecord(BaseModel):
    """Complete pest detection and plant inspection record for DBMS storage."""
    id: Optional[int] = Field(default=None, description="Database record primary key")
    timestamp: str = Field(..., description="ISO 8601 formatted timestamp string")
    crop_type: str = Field(..., description="Selected crop: mungbean, squash, eggplant, corn")
    farm_area: str = Field(default="Plot 1", description="Assigned farm plot or greenhouse zone")
    detected_pest: str = Field(..., description="Identified pest common name or 'Pest-Free'")
    pest_count: int = Field(default=0, ge=0, description="Estimated count of detected pests in image")
    infestation_level: str = Field(default="None", description="None, Low, Moderate, Severe")
    soil_moisture_percent: float = Field(default=0.0, description="Soil moisture % at time of detection")
    soil_status: str = Field(default="Optimal", description="Soil moisture status: Dry, Optimal, Waterlogged")
    plant_health_status: str = Field(default="Healthy", description="Holistic plant health condition")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="AI model confidence score")
    recommended_pesticide: Optional[str] = Field(default=None, description="Chemical pesticide recommendation")
    organic_alternative: Optional[str] = Field(default=None, description="Organic bio-pesticide alternative")
    dosage_instruction: Optional[str] = Field(default=None, description="Application rate and timing")
    safety_precautions: Optional[str] = Field(default=None, description="Safety notes and PPE guidelines")
    image_path: Optional[str] = Field(default=None, description="Relative path to annotated snapshot image")
    status: str = Field(default="CONFIRMED", description="Record status: CONFIRMED, UNCERTAIN, or PEST_FREE")


class AnalyzeRequest(BaseModel):
    """Request payload to trigger an immediate manual inspection snapshot."""
    crop_type: Optional[str] = Field(default=None, description="Override active crop for this analysis")
    farm_area: Optional[str] = Field(default=None, description="Override farm plot for this analysis")


class CropInfo(BaseModel):
    """Crop catalog metadata."""
    key: str
    name: str
    scientific_name: Optional[str] = ""
    pests: List[str] = []
