"""
AgriSentinel Web Application & REST/WebSocket API

Serves the mobile-first monitoring dashboard, telemetry endpoints,
and real-time alerts for the AgriSentinel Smart Crop Probe Stick.
"""

import os
import sys
import time
import json
import asyncio
import hashlib
import logging
from typing import List, Optional, Dict, Any

from fastapi import (
    APIRouter,
    Request,
    Form,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    Response
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from edge.database import (
    get_db_connection,
    insert_detection,
    get_recent_detections,
    get_detection_by_id,
    delete_detection,
    get_detection_stats
)
from edge.knowledge_base import knowledge_base
from edge.probe_controller import probe

logger = logging.getLogger("AgriSentinel-WebApp")

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


# --- WebSocket Connection Manager for Real-Time Alerts ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WebSocket] Client connected. Active clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"[WebSocket] Client disconnected. Active clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


# Register probe alert callback with event loop
def on_probe_alert(payload: Dict[str, Any]):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)
        else:
            asyncio.run(manager.broadcast(payload))
    except Exception as e:
        logger.debug(f"[WebSocket] Alert broadcast scheduled: {e}")


probe.register_alert_callback(on_probe_alert)


# --- Authentication Utilities ---
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    return salt.hex() + ":" + hashlib.sha256(salt + password.encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    if ":" not in hashed:
        return password == hashed
    salt_hex, hash_val = hashed.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    return hashlib.sha256(salt + password.encode("utf-8")).hexdigest() == hash_val


def get_current_user(request: Request):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users_tbl WHERE ID = ?", (user_id,)).fetchone()
    conn.close()
    return user


# --- Web Page Routes ---

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "message": None, "registration_success": False}
    )


@router.post("/login", response_class=HTMLResponse)
async def do_login(request: Request, account: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users_tbl WHERE ACCOUNT = ?", (account,)).fetchone()
    conn.close()

    if user and verify_password(password, user["PASSWORD"]):
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(key="user_id", value=str(user["ID"]))
        return response

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "message": "Invalid credentials", "registration_success": False}
    )


@router.post("/register", response_class=HTMLResponse)
async def do_register(
    request: Request,
    lastname: str = Form(...),
    firstname: str = Form(...),
    middlename: str = Form(""),
    user_type: str = Form(...),
    affiliation: str = Form(...),
    account: str = Form(...),
    password: str = Form(...)
):
    conn = get_db_connection()
    existing = conn.execute("SELECT ID FROM users_tbl WHERE ACCOUNT = ?", (account,)).fetchone()
    if existing:
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "message": "Account username already exists. Please choose another.", "registration_success": False}
        )

    hashed_pw = hash_password(password)
    conn.execute("""
        INSERT INTO users_tbl (LASTNAME, FIRSTNAME, MIDDLENAME, USER_TYPE, AFFILIATION, ACCOUNT, PASSWORD)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (lastname, firstname, middlename, user_type, affiliation, account, hashed_pw))
    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "message": None, "registration_success": True}
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("user_id")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    crops = knowledge_base.get_supported_crops()
    telemetry = probe.get_telemetry()
    detections = get_recent_detections(limit=30)
    stats = get_detection_stats()

    # Pre-fetch recommendation for current active pest
    active_crop = telemetry["active_crop"]
    latest_pest = telemetry["latest_pest"]
    rec = knowledge_base.get_recommendation(
        crop_key=active_crop,
        pest_name=latest_pest,
        confidence=0.88,
        pest_count=telemetry["latest_pest_count"],
        soil_status=telemetry["soil_status"]
    )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "user": user,
            "telemetry": telemetry,
            "crops": crops,
            "detections": detections,
            "stats": stats,
            "latest_recommendation": rec
        }
    )


# --- Live Video Streaming Route ---

def gen_probe_stream():
    """Generates continuous multipart MJPEG stream from the probe controller."""
    while True:
        frame_bytes = probe.get_jpeg_frame()
        if frame_bytes:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame_bytes)).encode() + b"\r\n\r\n" +
                frame_bytes +
                b"\r\n"
            )
        time.sleep(0.04)


@router.get("/video_feed")
def video_feed():
    """MJPEG Video stream endpoint for real-time web/mobile inspection preview."""
    return StreamingResponse(
        gen_probe_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


@router.get("/api/camera/snapshot")
def get_snapshot():
    """Returns a single JPEG image snapshot from the live camera stream."""
    frame_bytes = probe.get_jpeg_frame()
    if not frame_bytes:
        return Response(status_code=500, content="Failed to capture snapshot")
    return Response(content=frame_bytes, media_type="image/jpeg")


# --- REST API Endpoints ---

@router.get("/api/status")
async def get_status():
    """Returns current probe telemetry (crop, soil moisture, pest status, health)."""
    return {
        "status": "success",
        "telemetry": probe.get_telemetry()
    }


@router.get("/api/soil-moisture")
async def get_soil_moisture():
    """Returns latest soil moisture reading and status classification."""
    reading = probe.soil_sensor.read_moisture()
    return {
        "status": "success",
        "soil_moisture": reading
    }


@router.get("/api/crops")
async def get_crops():
    """Returns list of supported crops and their cataloged pests."""
    return {
        "status": "success",
        "crops": knowledge_base.get_supported_crops(),
        "active_crop": probe.active_crop
    }


class SelectCropRequest(BaseModel):
    crop: str


@router.post("/api/crop/select")
async def select_crop(req: SelectCropRequest):
    """Sets the active host crop being inspected by the probe."""
    probe.set_active_crop(req.crop)
    return {
        "status": "success",
        "active_crop": probe.active_crop,
        "crop_details": knowledge_base.get_crop(probe.active_crop)
    }


class UpdatePlotRequest(BaseModel):
    farm_area: str


@router.post("/api/plot/update")
async def update_plot(req: UpdatePlotRequest):
    """Sets the farm zone or field plot identifier."""
    probe.set_farm_area(req.farm_area)
    return {
        "status": "success",
        "farm_area": probe.farm_area
    }


class AnalyzeRequest(BaseModel):
    crop_type: Optional[str] = None
    farm_area: Optional[str] = None


@router.post("/api/analyze")
async def analyze_snapshot(req: Optional[AnalyzeRequest] = None):
    """Triggers immediate camera capture, pest detection, and pesticide recommendation."""
    crop = req.crop_type if req else None
    plot = req.farm_area if req else None
    record = probe.analyze_now(crop_type=crop, farm_area=plot)
    return {
        "status": "success",
        "record": record
    }


@router.get("/api/detections")
async def get_detections_api(
    limit: int = 50,
    crop_type: Optional[str] = None,
    infestation_level: Optional[str] = None
):
    """Retrieves paginated historical detection logs with optional filtering."""
    records = get_recent_detections(limit=limit, crop_type=crop_type, infestation_level=infestation_level)
    return {
        "status": "success",
        "count": len(records),
        "detections": records
    }


@router.get("/api/detections/{detection_id}")
async def get_single_detection(detection_id: int):
    """Retrieves single detection record details by ID."""
    rec = get_detection_by_id(detection_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Detection record not found")
    return {
        "status": "success",
        "detection": rec
    }


@router.delete("/api/detections/{detection_id}")
async def delete_detection_api(detection_id: int):
    """Deletes detection record and associated snapshot image."""
    success = delete_detection(detection_id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"status": "success", "message": f"Detection {detection_id} deleted."}


@router.get("/api/recommendations/{crop}/{pest}")
async def query_recommendation(
    crop: str,
    pest: str,
    confidence: float = 0.85,
    count: int = 1,
    soil_status: str = "Optimal"
):
    """Queries agricultural knowledge base directly for a crop and pest combination."""
    rec = knowledge_base.get_recommendation(
        crop_key=crop,
        pest_name=pest,
        confidence=confidence,
        pest_count=count,
        soil_status=soil_status
    )
    return {
        "status": "success",
        "recommendation": rec
    }


@router.get("/api/stats")
async def get_stats_api():
    """Returns summary statistics across all inspections."""
    return {
        "status": "success",
        "stats": get_detection_stats()
    }


# --- WebSocket Alert Streaming ---

@router.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    """WebSocket stream providing real-time pest detection alerts and telemetry heartbeats."""
    await manager.connect(websocket)
    try:
        # Send initial connection handshake with latest telemetry
        await websocket.send_json({
            "type": "HANDSHAKE",
            "telemetry": probe.get_telemetry(),
            "timestamp": time.time()
        })

        while True:
            # Keep connection alive and accept client pings/messages
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
                if data.get("action") == "PING":
                    await websocket.send_json({
                        "type": "PONG",
                        "telemetry": probe.get_telemetry()
                    })
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"[WebSocket] Disconnected: {e}")
        manager.disconnect(websocket)


# --- Developer Settings View & Diagnostic Endpoints ---

@router.get("/dev_settings", response_class=HTMLResponse)
async def dev_settings_page(request: Request):
    """Serves Developer Settings page."""
    user = get_current_user(request)
    crops = knowledge_base.get_supported_crops()
    return templates.TemplateResponse(
        request=request,
        name="dev_settings.html",
        context={
            "request": request,
            "user": user,
            "telemetry": probe.get_telemetry(),
            "crops": crops
        }
    )


@router.get("/api/dev/status")
async def dev_get_status():
    """Returns system status, network IP, camera diagnostics, and soil sensor status."""
    ip_addr = "127.0.0.1"
    net_mode = "Wi-Fi"

    try:
        if sys.platform.startswith("linux"):
            import subprocess
            res = subprocess.run(["hostname", "-I"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                ip_addr = res.stdout.strip().split()[0]
    except Exception:
        pass

    soil_data = probe.soil_sensor.read_moisture()

    return {
        "status": "success",
        "ip_address": ip_addr,
        "network_mode": net_mode,
        "active_connection": "wlan0",
        "camera": {
            "backend": "OpenCV / Probe Vision",
            "resolution": "640x480",
            "target_fps": 30,
            "is_active": True,
            "is_synthetic": probe.cap is None
        },
        "model": {
            "loaded": getattr(probe.detector, "is_model_loaded", False),
            "path": getattr(probe.detector, "model_path", ""),
            "runtime": getattr(probe.detector, "runtime_name", "None"),
            "error": getattr(probe.detector, "model_error", None)
        },
        "soil": {
            "moisture_percent": soil_data["moisture_percent"],
            "status": soil_data["status"],
            "voltage": soil_data["voltage"],
            "raw_adc": soil_data["raw_adc"],
            "hardware_type": probe.soil_sensor.adc_type
        },
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": sys.platform
    }


class WifiConnectRequest(BaseModel):
    ssid: str
    password: Optional[str] = None


@router.post("/api/dev/wifi/connect")
async def dev_connect_wifi(req: WifiConnectRequest):
    """Saves Wi-Fi configuration using NetworkManager nmcli if available."""
    if not sys.platform.startswith("linux"):
        return {"status": "success", "message": f"[Simulated] Saved profile for '{req.ssid}'."}

    import subprocess
    cmd = ["nmcli", "device", "wifi", "connect", req.ssid]
    if req.password:
        cmd.extend(["password", req.password])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            return {"status": "success", "message": f"Connected to Wi-Fi '{req.ssid}' successfully."}
        return {"status": "error", "message": proc.stderr or proc.stdout}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/dev/camera/restart")
async def dev_restart_camera():
    """Reinitializes probe camera capture interface."""
    try:
        probe._init_camera()
        return {"status": "success", "message": "Camera subsystem reinitialized."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class PowerActionRequest(BaseModel):
    action: str


@router.post("/api/dev/system/power")
async def dev_system_power(req: PowerActionRequest):
    """Executes safe reboot or shutdown on Linux SBC."""
    action = req.action.lower().strip()
    if not sys.platform.startswith("linux"):
        return {"status": "success", "message": f"[Simulated] System {action} received."}

    import subprocess
    if action == "reboot":
        subprocess.Popen(["sudo", "reboot"])
        return {"status": "success", "message": "Reboot sequence initiated."}
    elif action == "shutdown":
        subprocess.Popen(["sudo", "shutdown", "-h", "now"])
        return {"status": "success", "message": "Shutdown sequence initiated."}
    return {"status": "error", "message": "Invalid power action specified."}


@router.get("/api/dev/system/logs")
async def dev_get_system_logs(lines: int = 80):
    """Returns recent application logs."""
    if sys.platform.startswith("linux"):
        import subprocess
        try:
            res = subprocess.run(
                ["journalctl", "-u", "agrisentinel", "-n", str(lines), "--no-pager"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode == 0:
                return {"status": "success", "logs": res.stdout}
        except Exception:
            pass

    # Fallback simulated logs for dev
    sim_logs = (
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] AgriSentinel Smart Crop Probe online\n"
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Active crop: {probe.active_crop}\n"
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Soil moisture: {probe.latest_soil['moisture_percent']}%\n"
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Camera capture stream active (640x480)\n"
    )
    return {"status": "success", "logs": sim_logs}


# --- AI Vision & Inference Settings Endpoints ---

class VisionSettingsRequest(BaseModel):
    class_filter_mode: Optional[str] = None
    conf_threshold: Optional[float] = None
    iou_threshold: Optional[float] = None


@router.get("/api/dev/vision_settings")
async def dev_get_vision_settings():
    """Returns AI vision engine parameters, model status, and active taxonomy mode."""
    detector = probe.detector
    labels = getattr(detector, "labels", [])
    mode = getattr(detector, "class_filter_mode", "strict_12")

    from edge.vision.detector import ALLOWED_STRICT_12
    if mode == "strict_12":
        active_list = [{"id": k, "name": v} for k, v in sorted(ALLOWED_STRICT_12.items())]
    else:
        active_list = [{"id": idx, "name": name} for idx, name in enumerate(labels)]

    return {
        "status": "success",
        "model_loaded": getattr(detector, "is_model_loaded", False),
        "model_path": getattr(detector, "model_path", ""),
        "model_error": getattr(detector, "model_error", None),
        "runtime_name": getattr(detector, "runtime_name", "None"),
        "class_filter_mode": mode,
        "conf_threshold": getattr(detector, "conf_threshold", 0.60),
        "iou_threshold": getattr(detector, "iou_threshold", 0.45),
        "total_classes": len(labels),
        "active_classes_count": len(active_list),
        "active_classes": active_list
    }


@router.post("/api/dev/vision_settings")
async def dev_update_vision_settings(req: VisionSettingsRequest):
    """Updates AI vision engine parameters and class filtering mode live."""
    detector = probe.detector
    if hasattr(detector, "set_parameters"):
        detector.set_parameters(
            conf_threshold=req.conf_threshold,
            iou_threshold=req.iou_threshold,
            class_filter_mode=req.class_filter_mode
        )
    return {
        "status": "success",
        "message": "Vision parameters updated successfully.",
        "settings": {
            "class_filter_mode": getattr(detector, "class_filter_mode", "strict_12"),
            "conf_threshold": getattr(detector, "conf_threshold", 0.60),
            "iou_threshold": getattr(detector, "iou_threshold", 0.45),
            "model_loaded": getattr(detector, "is_model_loaded", False)
        }
    }


