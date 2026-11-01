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
    query_detections,
    delete_detections_batch,
    clear_detections,
    get_detection_stats,
    DETECTIONS_DIR
)
from edge.knowledge_base import knowledge_base
from edge.probe_controller import probe, generate_cropped_pest_snapshot
from edge.vision.detector import annotate_frame
from edge.pest_imagery import get_or_create_pest_reference_image

logger = logging.getLogger("AgriSentinel-WebApp")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_video_logo_assets():
    """Extracts official logo emblem and full video poster from VIdeoAboutAgriSentinel.mp4 if missing."""
    icon_path = os.path.join(BASE_DIR, "web", "static", "images", "logo_icon.png")
    full_path = os.path.join(BASE_DIR, "web", "static", "images", "logo_full.png")
    if os.path.exists(icon_path) and os.path.exists(full_path):
        return

    video_path = os.path.join(BASE_DIR, "VIdeoAboutAgriSentinel.mp4")
    if not os.path.exists(video_path):
        return

    try:
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return

        os.makedirs(os.path.join(BASE_DIR, "web", "static", "images"), exist_ok=True)
        # 1. Full poster
        poster = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)
        cv2.imwrite(full_path, poster)

        # 2. Clean circular emblem
        emblem = frame.copy()
        emblem[0:850, 1242:] = [255, 255, 255]
        emblem[850:1210, 1152:] = [255, 255, 255]
        emblem[1210:, 1305:] = [255, 255, 255]

        cx, cy, size = 705, 1070, 1350
        x1, y1 = cx - size // 2, cy - size // 2
        crop = emblem[y1 : y1 + size, x1 : x1 + size]
        icon = cv2.resize(crop, (512, 512), interpolation=cv2.INTER_AREA)
        cv2.imwrite(icon_path, icon)
        logger.info("[WebApp] Successfully generated logo_icon.png and logo_full.png from VIdeoAboutAgriSentinel.mp4")
    except Exception as e:
        logger.warning(f"[WebApp] Could not auto-extract video logo assets: {e}")


# Run extraction check once on module load
_ensure_video_logo_assets()

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


@router.get("/logo.png", include_in_schema=False)
async def logo_fallback():
    logo_path = os.path.join(BASE_DIR, "web", "static", "images", "logo_icon.png")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/png")
    return Response(status_code=404)


@router.get("/api/video/intro")
async def get_intro_video():
    """Serves promotional & introductory video with HTTP byte-range streaming support."""
    video_path = os.path.join(BASE_DIR, "VIdeoAboutAgriSentinel.mp4")
    if not os.path.exists(video_path):
        alt_path = os.path.join(os.path.dirname(BASE_DIR), "VIdeoAboutAgriSentinel.mp4")
        if os.path.exists(alt_path):
            video_path = alt_path
        else:
            raise HTTPException(status_code=404, detail="Intro video file not found on probe.")
    return FileResponse(video_path, media_type="video/mp4")


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
    images = get_or_create_pest_reference_image(latest_pest, rec)

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
            "latest_recommendation": rec,
            "rec_images": images
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
        time.sleep(0.033)


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
        "live_ai_enabled": probe.live_ai_enabled,
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
    record = await asyncio.to_thread(probe.analyze_now, crop_type=crop, farm_area=plot)
    return {
        "status": "success",
        "record": record
    }


@router.post("/api/detect/upload")
async def detect_from_phone(
    file: UploadFile = File(...),
    crop_type: Optional[str] = Form(None),
    conf_threshold: Optional[float] = Form(None),
    model_profile: Optional[str] = Form(None),
    source: Optional[str] = Form("phone_camera")
):
    """
    Receives an image snapshot uploaded from the smartphone camera or desktop dashboard,
    runs AI inference with active or selectable model profile,
    generates plant health, beneficial predator protection, & pesticide recommendations,
    saves the annotated image, logs the detection to SQLite with [Phone Camera] or [Dashboard Upload] tag,
    and broadcasts alert over WebSocket.
    """
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image file format")

    is_dashboard = (source or "").lower().strip() == "dashboard_upload"
    tag_label = "Dashboard Upload" if is_dashboard else "Phone Camera"
    src_slug = "dash" if is_dashboard else "phone"

    # Determine crop
    target_crop = (crop_type or probe.active_crop).lower().strip()
    supported_keys = [c["key"] for c in knowledge_base.get_supported_crops()]
    if target_crop not in supported_keys and target_crop not in ("auto", "auto_detect", "autodetect"):
        target_crop = probe.active_crop

    # Run inference with optional custom confidence threshold & profile asynchronously
    parsed_conf = float(conf_threshold) if conf_threshold is not None else None
    clean_profile = model_profile.strip() if model_profile and model_profile.strip() else None
    detections = await asyncio.to_thread(
        probe.detector.detect, frame, target_crop, conf_threshold=parsed_conf, model_profile=clean_profile
    )

    primary_pest = detections[0] if detections else None
    pest_name = primary_pest.pest_key if primary_pest else "none"
    pest_count = len(detections)
    confidence = primary_pest.confidence if primary_pest else 1.0
    is_beneficial = primary_pest.is_beneficial if primary_pest else False
    taxonomy = primary_pest.taxonomy if primary_pest else None

    # Auto-resolve target crop from detected pest
    if pest_name and pest_name != "none":
        resolved_crop = knowledge_base.infer_crop_from_pest(pest_name, fallback_crop=target_crop)
        if resolved_crop:
            target_crop = resolved_crop

    if target_crop in ("auto", "auto_detect", "autodetect"):
        target_crop = "rice"

    infestation = knowledge_base.calculate_infestation_level(target_crop, pest_name, pest_count)
    plant_health = knowledge_base.evaluate_plant_health(pest_count, infestation, pest_name=pest_name)

    rec = knowledge_base.get_recommendation(
        crop_key=target_crop,
        pest_name=pest_name,
        confidence=confidence if detections else 1.0,
        pest_count=pest_count,
        is_beneficial=is_beneficial,
        taxonomy=taxonomy
    )

    crop_data = knowledge_base.get_crop(target_crop)
    crop_name = crop_data.get("name", target_crop.capitalize()) if crop_data else target_crop.capitalize()

    # Ensure detected pests receive informative IPM recommendations even if borderline (unless beneficial predator)
    if detections and not is_beneficial and rec.get("status") == "IGNORED_LOW_CONFIDENCE":
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

    # 1. Annotate uncropped full snapshot
    model_status = "Online" if getattr(probe.detector, "is_model_loaded", False) else "Offline (Missing)"
    annotated_full = annotate_frame(
        frame,
        detections,
        crop_name=crop_name,
        health_status=rec["plant_health_status"],
        model_status=model_status
    )

    # 2. Generate cropped pest close-up ROI macro
    cropped_macro = generate_cropped_pest_snapshot(frame, detections)

    # Save dual snapshots
    ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:6]
    full_filename = f"det_{ts_str}_{target_crop}_{src_slug}_{uid}_full.jpg"
    crop_filename = f"det_{ts_str}_{target_crop}_{src_slug}_{uid}_crop.jpg"

    full_disk_path = os.path.join(DETECTIONS_DIR, full_filename)
    crop_disk_path = os.path.join(DETECTIONS_DIR, crop_filename)

    cv2.imwrite(full_disk_path, annotated_full, [cv2.IMWRITE_JPEG_QUALITY, 85])
    cv2.imwrite(crop_disk_path, cropped_macro, [cv2.IMWRITE_JPEG_QUALITY, 90])

    rel_full_path = f"/static/detections/{full_filename}"
    rel_crop_path = f"/static/detections/{crop_filename}"

    # Build multi-pest recommendations
    multi_recs = probe._build_multi_pest_recommendations(detections, target_crop)

    # Format composite pest name if multiple species detected
    if not detections:
        detected_pest_name = "Pest-Free"
    elif len(multi_recs) == 1:
        detected_pest_name = rec["detected_pest"]
    else:
        detected_pest_name = ", ".join([
            f"{r.get('detected_pest', 'Pest')} ({r.get('pest_count_for_species', 1)})"
            for r in multi_recs
        ])

    # Insert to database with [Phone Camera] or [Dashboard Upload] tag in farm_area
    farm_tag = f"{probe.farm_area} [{tag_label}]"
    db_payload = {
        "timestamp": datetime.datetime.now().isoformat(),
        "crop_type": target_crop,
        "farm_area": farm_tag,
        "detected_pest": detected_pest_name,
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
        "image_path": rel_full_path,
        "crop_image_path": rel_crop_path,
        "status": rec["status"],
        "recommendations": multi_recs
    }
    rec_id = insert_detection(db_payload)
    db_payload["id"] = rec_id

    # Broadcast WebSocket alert
    trigger_type = "DASHBOARD_UPLOAD" if is_dashboard else "PHONE_CAMERA"
    alert_event = {
        "type": "PEST_DETECTION_ALERT",
        "trigger": trigger_type,
        "record": db_payload,
        "summary": f"{detected_pest_name} ({pest_count} detected via {tag_label}) in {crop_name}",
        "recommendations": multi_recs
    }
    probe._broadcast_alert(alert_event)

    findings = [
        {
            "name": d.label,
            "pest_key": d.pest_key,
            "confidence": round(d.confidence, 3),
            "is_beneficial": d.is_beneficial,
            "taxonomy": d.taxonomy,
            "box": {"x": d.x, "y": d.y, "width": d.width, "height": d.height}
        }
        for d in detections
    ]

    return {
        "status": "success",
        "source": "dashboard_upload" if is_dashboard else "PHONE_CAMERA",
        "crop_type": target_crop,
        "crop_name": crop_name,
        "pest_count": pest_count,
        "findings": findings,
        "recommendation": rec,
        "recommendations": multi_recs,
        "plant_health": rec["plant_health_status"],
        "record": db_payload,
        "image_url": rel_full_path,
        "crop_image_url": rel_crop_path
    }


class BatchDeleteRequest(BaseModel):
    ids: List[int]


class ClearDetectionsRequest(BaseModel):
    clear_all: bool = False
    filters: Optional[Dict[str, Any]] = None
    password: str = ""


@router.get("/api/detections")
async def get_detections_api(
    page: int = 1,
    page_size: int = 25,
    limit: Optional[int] = None,
    crop_type: Optional[str] = None,
    infestation_level: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_confidence: Optional[float] = None,
    status: Optional[str] = None,
    source: Optional[str] = None
):
    """Retrieves paginated historical detection logs with rich multi-tier filtering."""
    eff_limit = limit if limit is not None else page_size
    eff_limit = max(1, min(200, eff_limit))
    eff_page = max(1, page)
    offset = (eff_page - 1) * eff_limit

    data = query_detections(
        crop_type=crop_type,
        infestation_level=infestation_level,
        search=search,
        start_date=start_date,
        end_date=end_date,
        min_confidence=min_confidence,
        status=status,
        source=source,
        limit=eff_limit,
        offset=offset
    )

    total = data["total"]
    total_pages = max(1, (total + eff_limit - 1) // eff_limit)

    return {
        "status": "success",
        "count": len(data["records"]),
        "detections": data["records"],
        "pagination": {
            "page": eff_page,
            "page_size": eff_limit,
            "total": total,
            "total_pages": total_pages
        }
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


@router.post("/api/detections/batch-delete")
async def batch_delete_detections_api(req: BatchDeleteRequest):
    """Deletes multiple detection records and associated snapshot images."""
    deleted_count = delete_detections_batch(req.ids)
    return {
        "status": "success",
        "message": f"Successfully deleted {deleted_count} record(s).",
        "deleted_count": deleted_count
    }


@router.post("/api/detections/clear")
async def clear_detections_api(req: ClearDetectionsRequest, request: Request):
    """
    Clears all detection records or filtered records matching criteria.
    Requires user password verification before execution to prevent accidental data loss.
    """
    user = get_current_user(request)
    if not user:
        # Fallback to default administrator if called by API without active cookie
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users_tbl WHERE ACCOUNT = ?", ("vicente.labadia@deped.gov.ph",)).fetchone()
        conn.close()

    if not user:
        raise HTTPException(status_code=403, detail="No authorized user account found.")

    if not req.password or not verify_password(req.password, user["PASSWORD"]):
        raise HTTPException(status_code=403, detail="Incorrect account password. Clear History was cancelled.")

    deleted_count = clear_detections(filters=req.filters, clear_all=req.clear_all)
    return {
        "status": "success",
        "message": f"Successfully deleted {deleted_count} record(s).",
        "deleted_count": deleted_count
    }


@router.get("/api/recommendations/{crop}/{pest}")
async def query_recommendation(
    crop: str,
    pest: str,
    confidence: float = 0.85,
    count: int = 1,
    soil_status: Optional[str] = None
):
    """Queries agricultural knowledge base directly for a crop and pest combination and returns reference imagery."""
    rec = knowledge_base.get_recommendation(
        crop_key=crop,
        pest_name=pest,
        confidence=confidence,
        pest_count=count,
        soil_status=soil_status
    )
    images = get_or_create_pest_reference_image(pest, rec)
    return {
        "status": "success",
        "recommendation": rec,
        "images": images
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
        "network": {
            "connection": "wlan0",
            "ip_address": ip_addr,
            "mode": net_mode
        },
        "camera": {
            "model": probe.ptz.model_name,
            "connection_mode": probe.ptz.connection_mode,
            "backend": f"{probe.ptz.model_name} ({probe.ptz.connection_mode.upper()})",
            "resolution": f"{probe.ptz.profile['capture_size'][0]}x{probe.ptz.profile['capture_size'][1]}",
            "profile": probe.ptz.profile_key,
            "profile_name": probe.ptz.profile["name"],
            "target_fps": 30,
            "is_active": True,
            "is_synthetic": probe.cap is None,
            "ptz": probe.ptz.get_status()
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
    model_profile: Optional[str] = None
    box_thickness: Optional[int] = None


@router.get("/api/dev/vision_settings")
async def dev_get_vision_settings():
    """Returns AI vision engine parameters, model status, active taxonomy mode, and available model profiles."""
    detector = probe.detector
    labels = getattr(detector, "labels", [])
    mode = getattr(detector, "class_filter_mode", "full_102")
    active_profile = getattr(detector, "active_profile", "comprehensive_102")

    from edge.vision.detector import ALLOWED_STRICT_12, MODEL_PROFILES
    if mode == "strict_12" and active_profile == "comprehensive_102":
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
        "box_thickness": getattr(detector, "box_thickness", 2),
        "active_model_profile": active_profile,
        "available_profiles": [
            {
                "id": k,
                "name": v["name"],
                "type": v["type"],
                "total_classes": v["total_classes"],
                "description": v["description"]
            }
            for k, v in MODEL_PROFILES.items()
        ],
        "total_classes": len(labels),
        "active_classes_count": len(active_list),
        "active_classes": active_list
    }


@router.post("/api/dev/vision_settings")
async def dev_update_vision_settings(req: VisionSettingsRequest):
    """Updates AI vision engine parameters, class filtering mode, box thickness, and active model profile live."""
    detector = probe.detector
    if hasattr(detector, "set_parameters"):
        detector.set_parameters(
            conf_threshold=req.conf_threshold,
            iou_threshold=req.iou_threshold,
            class_filter_mode=req.class_filter_mode,
            model_profile=req.model_profile,
            box_thickness=req.box_thickness
        )
    return {
        "status": "success",
        "message": "Vision parameters updated successfully.",
        "settings": {
            "active_model_profile": getattr(detector, "active_profile", "comprehensive_102"),
            "class_filter_mode": getattr(detector, "class_filter_mode", "full_102"),
            "conf_threshold": getattr(detector, "conf_threshold", 0.25),
            "iou_threshold": getattr(detector, "iou_threshold", 0.45),
            "box_thickness": getattr(detector, "box_thickness", 2),
            "model_loaded": getattr(detector, "is_model_loaded", False)
        }
    }


class LiveAIToggleRequest(BaseModel):
    enabled: bool


@router.post("/api/vision/live_toggle")
async def api_vision_live_toggle(req: LiveAIToggleRequest):
    """Enables or disables continuous background AI pest detection to optimize stream frame rate."""
    probe.set_live_ai_enabled(req.enabled)
    return {
        "status": "success",
        "live_ai_enabled": probe.live_ai_enabled,
        "message": f"Live AI Detection {'enabled' if probe.live_ai_enabled else 'disabled'}"
    }


# --- FEELWORLD 4K10X PTZ & Camera Configuration Endpoints ---

class PTZMoveRequest(BaseModel):
    action: str  # pan_left, pan_right, tilt_up, tilt_down, zoom_in, zoom_out, home, set
    step: Optional[float] = 5.0
    zoom_step: Optional[float] = 0.5
    pan: Optional[float] = None
    tilt: Optional[float] = None
    zoom: Optional[float] = None


class PTZPresetRequest(BaseModel):
    action: str  # recall, save
    preset_id: int
    name: Optional[str] = None


class PTZPatrolRequest(BaseModel):
    patrol_mode: str  # off, preset_sweep, continuous_sweep
    interval_sec: Optional[float] = None
    auto_zoom_on_detect: Optional[bool] = None


class CameraConfigRequest(BaseModel):
    connection_mode: Optional[str] = None
    camera_index: Optional[int] = None
    rtsp_url: Optional[str] = None
    visca_ip: Optional[str] = None
    visca_port: Optional[int] = None
    resolution_profile: Optional[str] = None


@router.get("/api/ptz/status")
async def api_ptz_status():
    """Returns FEELWORLD 4K10X PTZ current pan, tilt, zoom, presets, patrol and limits."""
    return {"status": "success", "ptz": probe.ptz.get_status()}


@router.post("/api/ptz/move")
async def api_ptz_move(req: PTZMoveRequest):
    """Executes relative or absolute PTZ step."""
    if req.action == "set":
        status = probe.ptz.set_position(pan=req.pan, tilt=req.tilt, zoom=req.zoom)
    else:
        status = probe.ptz.move_step(action=req.action, step=req.step or 5.0, zoom_step=req.zoom_step or 0.5)
    return {"status": "success", "ptz": status}


@router.post("/api/ptz/preset")
async def api_ptz_preset(req: PTZPresetRequest):
    """Recalls or saves a canopy preset slot."""
    if req.action == "recall":
        status = probe.ptz.recall_preset(preset_id=req.preset_id)
    elif req.action == "save":
        status = probe.ptz.save_preset(preset_id=req.preset_id, name=req.name)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown preset action: {req.action}")
    return {"status": "success", "ptz": status}


@router.post("/api/ptz/patrol")
async def api_ptz_patrol(req: PTZPatrolRequest):
    """Configures automated field sweep patrol and smart auto-zoom."""
    status = probe.ptz.set_patrol_mode(
        mode=req.patrol_mode,
        interval_sec=req.interval_sec,
        auto_zoom=req.auto_zoom_on_detect
    )
    return {"status": "success", "ptz": status}


@router.post("/api/dev/camera/config")
async def api_dev_camera_config(req: CameraConfigRequest):
    """Dynamically applies FEELWORLD 4K10X connection mode and resolution profile."""
    telemetry = probe.restart_camera(
        connection_mode=req.connection_mode,
        camera_index=req.camera_index,
        rtsp_url=req.rtsp_url,
        visca_ip=req.visca_ip,
        visca_port=req.visca_port,
        resolution_profile=req.resolution_profile
    )
    return {
        "status": "success",
        "message": "Camera configuration updated and restarted.",
        "telemetry": telemetry,
        "ptz": probe.ptz.get_status()
    }



