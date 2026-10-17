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
import uuid
import datetime
import logging
from typing import List, Optional, Dict, Any
import cv2
import numpy as np

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
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from edge.database import (
    get_db_connection,
    insert_detection,
    get_recent_detections,
    get_detection_by_id,
    delete_detection,
    get_detection_stats,
    DETECTIONS_DIR
)
from edge.knowledge_base import knowledge_base
from edge.probe_controller import probe
from edge.vision.detector import annotate_frame

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


@router.get("/sw.js", include_in_schema=False)
async def serve_service_worker():
    """Serves root-scoped service worker for PWA offline lifecycle."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sw_path = os.path.join(base_dir, "web", "static", "sw.js")
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request, next: Optional[str] = None):
    user = get_current_user(request)
    if user:
        target = next if next and next.startswith("/") else "/dashboard"
        return RedirectResponse(url=target, status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "message": None, "registration_success": False, "next": next}
    )


@router.post("/login", response_class=HTMLResponse)
async def do_login(
    request: Request,
    account: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None)
):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users_tbl WHERE ACCOUNT = ?", (account,)).fetchone()
    conn.close()

    if user and verify_password(password, user["PASSWORD"]):
        target = next if next and next.startswith("/") else "/dashboard"
        response = RedirectResponse(url=target, status_code=302)
        response.set_cookie(key="user_id", value=str(user["ID"]))
        return response

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "message": "Invalid credentials", "registration_success": False, "next": next}
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
        pest_count=telemetry["latest_pest_count"]
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


@router.get("/mobile", response_class=HTMLResponse)
async def mobile_page(request: Request):
    """Serves the Progressive Web App (PWA) mobile field inspection interface."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/?next=/mobile", status_code=302)

    crops = knowledge_base.get_supported_crops()
    telemetry = probe.get_telemetry()

    return templates.TemplateResponse(
        request=request,
        name="mobile.html",
        context={
            "request": request,
            "user": user,
            "telemetry": telemetry,
            "crops": crops,
            "active_crop": probe.active_crop
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

@router.get("/api/ping")
async def ping():
    """Heartbeat endpoint for connection health monitoring."""
    return {
        "status": "ok",
        "device": "agrisentinel_probe",
        "active_crop": probe.active_crop,
        "timestamp": time.time()
    }


@router.get("/api/status")
async def get_status():
    """Returns current probe telemetry (crop, pest status, health, model)."""
    return {
        "status": "success",
        "telemetry": probe.get_telemetry()
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


@router.post("/api/detect/upload")
async def detect_from_phone(
    file: UploadFile = File(...),
    crop_type: Optional[str] = Form(None),
    conf_threshold: Optional[float] = Form(None)
):
    """
    Receives an image snapshot uploaded from the smartphone camera,
    runs TFLite YOLO inference, generates plant health & pesticide recommendations,
    saves the annotated image, logs the detection to SQLite with [Phone Camera] tag,
    and broadcasts alert over WebSocket.
    """
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image file format")

    # Determine crop
    target_crop = (crop_type or probe.active_crop).lower().strip()
    supported_keys = [c["key"] for c in knowledge_base.get_supported_crops()]
    if target_crop not in supported_keys:
        target_crop = probe.active_crop

    # Run inference with optional custom confidence threshold
    parsed_conf = float(conf_threshold) if conf_threshold is not None else None
    detections = probe.detector.detect(frame, target_crop, conf_threshold=parsed_conf)

    # Prepare metadata & recommendations
    crop_data = knowledge_base.get_crop(target_crop)
    crop_name = crop_data.get("name", target_crop.capitalize()) if crop_data else target_crop.capitalize()

    primary_pest = detections[0] if detections else None
    pest_name = primary_pest.pest_key if primary_pest else "none"
    pest_count = len(detections)
    confidence = primary_pest.confidence if primary_pest else 1.0

    infestation = knowledge_base.calculate_infestation_level(target_crop, pest_name, pest_count)
    plant_health = knowledge_base.evaluate_plant_health(pest_count, infestation)

    rec = knowledge_base.get_recommendation(
        crop_key=target_crop,
        pest_name=pest_name,
        confidence=confidence if detections else 1.0,
        pest_count=pest_count
    )

    # Ensure detected pests receive informative IPM recommendations even if borderline
    if detections and rec.get("status") == "IGNORED_LOW_CONFIDENCE":
        pest_meta = knowledge_base.get_pest(target_crop, pest_name) or {}
        recs_meta = pest_meta.get("recommendations", {})
        chem_meta = recs_meta.get("chemical", {})
        org_meta = recs_meta.get("organic_biocontrol", {})
        rec["detected_pest"] = primary_pest.label
        rec["pest_count"] = pest_count
        rec["infestation_level"] = "Low"
        rec["plant_health_status"] = "Mild Pest Stress"
        rec["recommended_pesticide"] = f"[VERIFY FIRST] Candidate match ({confidence*100:.0f}%): " + chem_meta.get("product_name", "Broad-spectrum contact insecticide")
        rec["organic_alternative"] = org_meta.get("product_name", "Cold-pressed Neem Oil spray")
        rec["safety_precautions"] = "Visual confirmation recommended before chemical application."

    # Annotate snapshot
    model_status = "Online" if getattr(probe.detector, "is_model_loaded", False) else "Offline (Missing)"
    annotated = annotate_frame(
        frame,
        detections,
        crop_name=crop_name,
        health_status=rec["plant_health_status"],
        model_status=model_status
    )

    # Save snapshot
    ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"det_{ts_str}_{target_crop}_phone_{uuid.uuid4().hex[:6]}.jpg"
    full_path = os.path.join(DETECTIONS_DIR, filename)
    cv2.imwrite(full_path, annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
    rel_path = f"/static/detections/{filename}"

    # Insert to database with [Phone Camera] tag in farm_area
    farm_tag = f"{probe.farm_area} [Phone Camera]"
    db_payload = {
        "timestamp": datetime.datetime.now().isoformat(),
        "crop_type": target_crop,
        "farm_area": farm_tag,
        "detected_pest": rec["detected_pest"],
        "pest_count": pest_count,
        "infestation_level": rec["infestation_level"],
        "soil_moisture_percent": 0.0,
        "soil_status": "N/A",
        "plant_health_status": rec["plant_health_status"],
        "confidence": confidence if detections else 1.0,
        "recommended_pesticide": rec.get("recommended_pesticide", ""),
        "organic_alternative": rec.get("organic_alternative", ""),
        "dosage_instruction": rec.get("dosage_instruction", ""),
        "safety_precautions": rec.get("safety_precautions", ""),
        "image_path": rel_path,
        "status": rec["status"]
    }
    rec_id = insert_detection(db_payload)
    db_payload["id"] = rec_id

    # Broadcast WebSocket alert
    alert_event = {
        "type": "PEST_DETECTION_ALERT",
        "trigger": "PHONE_CAMERA",
        "record": db_payload,
        "summary": f"{rec['detected_pest']} ({pest_count} detected via Phone Camera) in {crop_name}"
    }
    probe._broadcast_alert(alert_event)

    findings = [
        {
            "name": d.label,
            "pest_key": d.pest_key,
            "confidence": round(d.confidence, 3),
            "box": {"x": d.x, "y": d.y, "width": d.width, "height": d.height}
        }
        for d in detections
    ]

    return {
        "status": "success",
        "source": "PHONE_CAMERA",
        "crop_type": target_crop,
        "crop_name": crop_name,
        "pest_count": pest_count,
        "findings": findings,
        "recommendation": rec,
        "plant_health": rec["plant_health_status"],
        "record": db_payload,
        "image_url": rel_path
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
    soil_status: Optional[str] = None
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
    """Returns system status, network IP, camera diagnostics, and model status."""
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
    mode = getattr(detector, "class_filter_mode", "full_102")

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
        "conf_threshold": getattr(detector, "conf_threshold", 0.25),
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
            "class_filter_mode": getattr(detector, "class_filter_mode", "full_102"),
            "conf_threshold": getattr(detector, "conf_threshold", 0.25),
            "iou_threshold": getattr(detector, "iou_threshold", 0.45),
            "model_loaded": getattr(detector, "is_model_loaded", False)
        }
    }


