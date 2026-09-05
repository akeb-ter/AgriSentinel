import os
import sys
import subprocess
import datetime
from fastapi import APIRouter, Request, Form, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Response
import shutil
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import asyncio
import time
from typing import List, Optional, Dict, Any

from .database import get_db_connection
from .drivers.motors import MotorController
from .drivers.servo import ServoController
from .drivers.gps import GPSReader

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

motors = MotorController()
servo = ServoController()
gps_reader = GPSReader()
gps_task: Optional[asyncio.Task] = None




# Simple active websocket connections for alerts
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# --- Auth Dependency ---
def get_current_user(request: Request):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users_tbl WHERE ID = ?", (user_id,)).fetchone()
    conn.close()
    return user

# --- Web Routes ---

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "message": None, "registration_success": False})

import hashlib

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    return salt.hex() + ":" + hashlib.sha256(salt + password.encode('utf-8')).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    if ":" not in hashed:
        return password == hashed
    salt_hex, hash_val = hashed.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    return hashlib.sha256(salt + password.encode('utf-8')).hexdigest() == hash_val

@router.post("/login", response_class=HTMLResponse)
async def do_login(request: Request, account: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users_tbl WHERE ACCOUNT = ?", (account,)).fetchone()
    conn.close()

    if user and verify_password(password, user['PASSWORD']):
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(key="user_id", value=str(user['ID']))
        return response
    
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "message": "Invalid credentials", "registration_success": False})

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
    # Check if account already exists
    existing = conn.execute("SELECT ID FROM users_tbl WHERE ACCOUNT = ?", (account,)).fetchone()
    
    if existing:
        conn.close()
        return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "message": "Account username already exists. Please choose another.", "registration_success": False})

    hashed_pw = hash_password(password)
    conn.execute("""
        INSERT INTO users_tbl (LASTNAME, FIRSTNAME, MIDDLENAME, USER_TYPE, AFFILIATION, ACCOUNT, PASSWORD)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (lastname, firstname, middlename, user_type, affiliation, account, hashed_pw))
    conn.commit()
    conn.close()

    # Return success flag to frontend
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "message": None, "registration_success": True})

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
    
    conn = get_db_connection()
    pests = conn.execute("SELECT * FROM pest").fetchall()
    logs = conn.execute("SELECT * FROM detection_logs ORDER BY ID DESC LIMIT 100").fetchall()
    conn.close()

    # Pass the threshold as a global setting to the template
    from edge.camera_test import get_log_confidence_threshold
    threshold = get_log_confidence_threshold()

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "request": request,
        "user": user,
        "db_pests": [dict(p) for p in pests],
        "logs": [dict(l) for l in logs],
        "log_confidence_threshold": threshold
    })

# --- APIs ---

@router.post("/api/detection_logs/delete")
async def delete_detection_log(request: Request, log_id: Optional[int] = Form(None)):
    if log_id is None:
        try:
            body = await request.json()
            log_id = body.get("log_id")
        except Exception:
            pass
            
    if not log_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "log_id is required"})
        
    conn = get_db_connection()
    try:
        log_entry = conn.execute("SELECT IMAGE_PATH FROM detection_logs WHERE ID = ?", (log_id,)).fetchone()
        if log_entry and log_entry['IMAGE_PATH']:
            img_path = os.path.join("web", "static", log_entry['IMAGE_PATH'])
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except Exception as e:
                    print(f"Error removing log image {img_path}: {e}")
                    
        conn.execute("DELETE FROM detection_logs WHERE ID = ?", (log_id,))
        conn.commit()
    finally:
        conn.close()

    # Check if request was made via fetch/AJAX
    accept = request.headers.get("accept", "")
    content_type = request.headers.get("content-type", "")
    if "application/json" in accept or "application/json" in content_type:
        return JSONResponse(content={"status": "success", "deleted_id": log_id})

    return RedirectResponse(url="/dashboard?tab=panelLogs", status_code=303)

@router.post("/api/detection_logs/delete_all")
async def delete_all_detection_logs(request: Request):
    conn = get_db_connection()
    try:
        logs = conn.execute("SELECT IMAGE_PATH FROM detection_logs").fetchall()
        for log_entry in logs:
            if log_entry and log_entry['IMAGE_PATH']:
                img_path = os.path.join("web", "static", log_entry['IMAGE_PATH'])
                if os.path.exists(img_path):
                    try:
                        os.remove(img_path)
                    except Exception as e:
                        print(f"Error removing log image {img_path}: {e}")
        conn.execute("DELETE FROM detection_logs")
        conn.commit()
    finally:
        conn.close()

    accept = request.headers.get("accept", "")
    content_type = request.headers.get("content-type", "")
    if "application/json" in accept or "application/json" in content_type:
        return JSONResponse(content={"status": "success", "message": "All detection logs deleted"})

    return RedirectResponse(url="/dashboard?tab=panelLogs", status_code=303)

class LogSettingsRequest(BaseModel):
    threshold: float

@router.post("/api/logs/settings")
async def update_log_settings(req: LogSettingsRequest):
    from edge.camera_test import set_log_confidence_threshold
    try:
        set_log_confidence_threshold(req.threshold)
        return {"status": "success", "threshold": req.threshold}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.post("/api/logs")
async def save_log(pest: str = Form(...), result: str = Form(...)):
    conn = get_db_connection()
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    conn.execute("INSERT INTO logs (PEST, RESULT, DATE, TIME) VALUES (?, ?, ?, ?)", 
                 (pest, result, date_str, time_str))
    conn.commit()
    conn.close()
    return {"status": "success"}

@router.post("/api/pests")
async def save_pest(
    request: Request,
    pest_name: str = Form(...),
    description: str = Form(...),
    suggested_action: str = Form(...),
    signal_range: str = Form(...),
    pest_id: str = Form(None),
    existing_image: str = Form(None),
    image_file: UploadFile = File(None)
):
    image_path = existing_image if existing_image else "default_pest.jpg"
    
    if image_file and image_file.filename:
        os.makedirs("web/static/images", exist_ok=True)
        filename = f"{int(datetime.datetime.now().timestamp())}_{image_file.filename}"
        target_path = os.path.join("web/static/images", filename)
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)
        image_path = f"images/{filename}"

    conn = get_db_connection()
    if pest_id and pest_id.strip():
        conn.execute("""
            UPDATE pest SET PEST = ?, DESCRIPTION = ?, SUGGESTED_ACTION = ?, SIGNAL_RANGE = ?, IMAGE = ?
            WHERE ID = ?
        """, (pest_name, description, suggested_action, signal_range, image_path, int(pest_id)))
    else:
        conn.execute("""
            INSERT INTO pest (PEST, DESCRIPTION, SUGGESTED_ACTION, SIGNAL_RANGE, IMAGE)
            VALUES (?, ?, ?, ?, ?)
        """, (pest_name, description, suggested_action, signal_range, image_path))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)

@router.post("/api/pests/delete")
async def delete_pest(pest_id: int = Form(...)):
    conn = get_db_connection()
    conn.execute("DELETE FROM pest WHERE ID = ?", (pest_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)

# Periodic GPS broadcast loop
async def ensure_gps_telemetry_loop():
    global gps_task
    if gps_task is None or gps_task.done():
        gps_task = asyncio.create_task(gps_telemetry_loop())

async def gps_telemetry_loop():
    while True:
        try:
            if manager.active_connections:
                raw_data = gps_reader.read_gps_data()
                is_synthetic = gps_reader.is_synthetic
                has_fix = bool(raw_data.get("gps_fix"))
                
                is_live = False
                data_status = "Unknown"
                last_fix = getattr(gps_reader, "last_valid_fix_time", 0.0)
                
                if is_synthetic:
                    data_status = "Synthetic"
                elif has_fix and time.time() - last_fix < 5.0:
                    is_live = True
                    data_status = "Live"
                elif last_fix > 0:
                    data_status = "Cached"
                else:
                    data_status = "No Fix"

                # Use real hardware coordinates if fix acquired, or demo coordinates in synthetic mode
                lat = raw_data.get("latitude") if has_fix else (6.681023 if is_synthetic else 0.0)
                lon = raw_data.get("longitude") if has_fix else (124.689331 if is_synthetic else 0.0)
                alt = raw_data.get("altitude") or (24.5 if is_synthetic else 0.0)
                sats = raw_data.get("satellites") if has_fix else (8 if is_synthetic else 0)

                if data_status == "Cached":
                    lat = gps_reader.latitude
                    lon = gps_reader.longitude
                    alt = gps_reader.altitude
                    sats = gps_reader.satellites

                await manager.broadcast({
                    "type": "GPS_TELEMETRY",
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "altitude": round(alt, 1),
                    "satellites": sats,
                    "gps_fix": has_fix,
                    "is_synthetic": is_synthetic,
                    "is_live": is_live,
                    "data_status": data_status,
                    "last_fix_time": last_fix
                })
        except Exception as e:
            print(f"Error in telemetry loop: {e}")
        await asyncio.sleep(1.0)

# --- WebSocket ---
@router.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await ensure_gps_telemetry_loop()
    try:
        while True:
            # We don't really expect the client to send us data, but we need to keep connection open
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Helper function to trigger alert from elsewhere in python code
async def trigger_pest_alert(pest_name: str, confidence: float, action: str, signal: str):
    await manager.broadcast({
        "type": "PEST_DETECTED",
        "name": pest_name,
        "confidence": confidence,
        "action": action,
        "signal": signal
    })

@router.get("/api/simulate_alert")
async def simulate_alert():
    await trigger_pest_alert("Armyworm", 0.92, "Apply Bt pesticide", "High")
    return {"status": "simulated"}

@router.get("/api/gps")
async def get_gps():
    raw_data = gps_reader.read_gps_data()
    is_synthetic = gps_reader.is_synthetic
    has_fix = bool(raw_data.get("gps_fix"))
    
    # Calculate if the fix is recent (live) or cached
    is_live = False
    data_status = "Unknown"
    last_fix = getattr(gps_reader, "last_valid_fix_time", 0.0)
    
    if is_synthetic:
        data_status = "Synthetic"
    elif has_fix and time.time() - last_fix < 5.0:
        is_live = True
        data_status = "Live"
    elif last_fix > 0:
        data_status = "Cached"
    else:
        data_status = "No Fix"

    # Fallbacks for UI demonstration if hardware is mocking or no fix yet
    lat = raw_data.get("latitude") if has_fix else (6.681023 if is_synthetic else 0.0)
    lon = raw_data.get("longitude") if has_fix else (124.689331 if is_synthetic else 0.0)
    alt = raw_data.get("altitude") or (24.5 if is_synthetic else 0.0)
    sats = raw_data.get("satellites") if has_fix else (8 if is_synthetic else 0)

    # Use old lat/lon if cached
    if data_status == "Cached":
        lat = gps_reader.latitude
        lon = gps_reader.longitude
        alt = gps_reader.altitude
        sats = gps_reader.satellites

    return {
        "status": "success",
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "altitude": round(alt, 1),
        "satellites": sats,
        "gps_fix": has_fix,
        "is_synthetic": is_synthetic,
        "is_live": is_live,
        "data_status": data_status,
        "last_fix_time": last_fix
    }

@router.get("/api/dev/gps/raw")
async def dev_get_gps_raw():
    """Returns the buffered raw NMEA stream for debugging."""
    raw_sentences = getattr(gps_reader, "get_raw_nmea", lambda: [])()
    return {
        "status": "success",
        "raw_stream": raw_sentences,
        "is_synthetic": gps_reader.is_synthetic,
        "baudrate": gps_reader.baudrate,
        "port": gps_reader.port
    }

@router.post("/api/dev/gps/restart")
async def dev_restart_gps():
    """Restarts the serial connection for the GPS module."""
    try:
        success = getattr(gps_reader, "reconnect", lambda: False)()
        return {
            "status": "success" if success else "warning",
            "message": "GPS Serial connection restarted." if success else "Fallback mode enabled after restart."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.websocket("/ws/control")
async def control_endpoint(websocket: WebSocket):
    await websocket.accept()
    last_command_time = time.time()
    
    async def deadman_switch():
        nonlocal last_command_time
        while True:
            if time.time() - last_command_time > 0.5:
                if motors.get_state() != "STOPPED":
                    motors.stop()
                # To prevent servo jitter, detach if idle
                servo.detach()
            await asyncio.sleep(0.1)
    
    deadman_task = asyncio.create_task(deadman_switch())
    
    try:
        while True:
            data = await websocket.receive_json()
            last_command_time = time.time()
            action = data.get("action")
            device = data.get("device")
            
            if device == "motor":
                if action == "forward":
                    motors.forward()
                elif action == "backward":
                    motors.backward()
                elif action == "left":
                    motors.left()
                elif action == "right":
                    motors.right()
                elif action == "stop":
                    if motors.get_state() != "STOPPED":
                        motors.stop()
            elif device == "servo":
                if action == "left":
                    servo.set_angle(servo.get_angle() + 5)
                elif action == "right":
                    servo.set_angle(servo.get_angle() - 5)
                elif action == "center":
                    servo.center()
            elif action == "heartbeat":
                pass # last_command_time is already updated
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Control WebSocket error: {e}")
    finally:
        deadman_task.cancel()
        motors.stop()
        servo.detach()


# ═══════════════════════════════════════════════════════════════════════
# Developer Settings Endpoints
# ═══════════════════════════════════════════════════════════════════════

class WifiConnectRequest(BaseModel):
    ssid: str
    password: Optional[str] = None


@router.get("/dev_settings", response_class=HTMLResponse)
async def dev_settings_page(request: Request):
    """Serves the Developer Settings dashboard."""
    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="dev_settings.html",
        context={"request": request, "user": user}
    )


@router.get("/api/dev/status")
async def dev_get_status():
    """Returns network mode, IP, camera diagnostics, and system info."""
    ip_addr = "Unknown"
    active_connection = "Unknown"

    try:
        if shutil.which("nmcli"):
            res_conn = subprocess.run(
                ["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", "wlan0"],
                capture_output=True, text=True, timeout=3
            )
            if res_conn.returncode == 0:
                conn_line = res_conn.stdout.strip().split("\n")[0]
                active_connection = conn_line.split(":")[-1]

        if shutil.which("ip"):
            res_ip = subprocess.run(
                ["ip", "-4", "addr", "show", "wlan0"],
                capture_output=True, text=True, timeout=3
            )
            if res_ip.returncode == 0:
                for line in res_ip.stdout.splitlines():
                    if "inet " in line:
                        ip_addr = line.strip().split()[1].split("/")[0]
                        break
        elif sys.platform.startswith("win"):
            import socket
            hostname = socket.gethostname()
            ip_addr = socket.gethostbyname(hostname)
            active_connection = "Windows Dev Network"
    except Exception as e:
        active_connection = f"Error: {e}"

    camera_info = {}
    try:
        from edge.camera_test import camera_manager
        camera_info = camera_manager.get_status()
    except Exception:
        camera_info = {"is_running": False, "backend": "Unavailable (simulation/standalone)"}

    return {
        "status": "success",
        "network": {
            "connection": active_connection,
            "ip_address": ip_addr,
            "local_domain": "http://agrisentinel.local:8000",
        },
        "camera": camera_info,
        "platform": sys.platform,
        "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


@router.post("/api/dev/wifi/connect")
async def dev_wifi_connect(req: WifiConnectRequest):
    """Executes set_wifi.sh to configure the target Wi-Fi network."""
    ssid = req.ssid.strip()
    if not ssid:
        raise HTTPException(status_code=400, detail="SSID cannot be empty.")

    script_path = os.path.abspath("scripts/set_wifi.sh")
    if not os.path.exists(script_path):
        return JSONResponse(status_code=500, content={"status": "error", "message": "scripts/set_wifi.sh not found."})

    try:
        cmd = ["bash", script_path, f"--ssid={ssid}"]
        if req.password:
            cmd.append(f"--pass={req.password}")
            
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30
        )
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.post("/api/dev/camera/restart")
async def dev_restart_camera():
    """Stops and reinitializes the active camera backend without full restart."""
    try:
        from edge.camera_test import camera_manager
        camera_manager.stop()
        await asyncio.sleep(0.6)
        camera_manager.start()
        return {
            "status": "success",
            "message": "Camera subsystem restarted successfully.",
            "camera_status": camera_manager.get_status()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.get("/api/dev/logs")
async def dev_get_logs(lines: int = 60):
    """Fetches recent system logs via journalctl."""
    lines = min(max(lines, 10), 200)
    output = ""
    try:
        if shutil.which("journalctl"):
            proc = subprocess.run(
                ["journalctl", "-u", "agrisentinel", "-n", str(lines), "--no-pager"],
                capture_output=True, text=True, timeout=5
            )
            output = proc.stdout if proc.stdout.strip() else proc.stderr
            if not output.strip():
                # Fallback to last system entries
                proc2 = subprocess.run(
                    ["journalctl", "-n", str(lines), "--no-pager"],
                    capture_output=True, text=True, timeout=5
                )
                output = proc2.stdout
        else:
            output = (
                f"[INFO] journalctl is not present on this host ({sys.platform}).\n"
                f"[INFO] Real systemd logs will appear here when running on Raspberry Pi.\n"
                f"[TIMESTAMP] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"[STATUS] AgriSentinel Edge Application is alive."
            )
    except Exception as e:
        output = f"Error reading logs: {e}"

    return {"status": "success", "logs": output}


@router.post("/api/dev/system/reboot")
async def dev_system_reboot():
    """Gracefully reboots the Raspberry Pi."""
    def _do_reboot():
        time.sleep(1.0)
        subprocess.run(["sudo", "reboot"])

    asyncio.get_event_loop().run_in_executor(None, _do_reboot)
    return {
        "status": "success",
        "message": "Reboot initiated. The system will restart in a few seconds."
    }


@router.post("/api/dev/system/shutdown")
async def dev_system_shutdown():
    """Safely shuts down the Raspberry Pi."""
    def _do_shutdown():
        time.sleep(1.0)
        subprocess.run(["sudo", "shutdown", "-h", "now"])

    asyncio.get_event_loop().run_in_executor(None, _do_shutdown)
    return {
        "status": "success",
        "message": "Shutdown initiated. Safely wait for the activity LED to turn off before cutting power."
    }


