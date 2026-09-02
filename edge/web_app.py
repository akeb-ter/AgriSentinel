import os
import datetime
from fastapi import APIRouter, Request, Form, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import asyncio
from typing import List

from .database import get_db_connection

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

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

@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "message": None})

@router.post("/login", response_class=HTMLResponse)
async def do_login(request: Request, account: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users_tbl WHERE ACCOUNT = ?", (account,)).fetchone()
    conn.close()

    if user and user['PASSWORD'] == password: # In real app, use password_verify
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(key="user_id", value=str(user['ID']))
        return response
    
    return templates.TemplateResponse("login.html", {"request": request, "message": "Invalid credentials"})

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
    logs = conn.execute("SELECT * FROM logs ORDER BY ID DESC LIMIT 50").fetchall()
    conn.close()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "db_pests": [dict(p) for p in pests],
        "logs": [dict(l) for l in logs]
    })

# --- APIs ---

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

# --- WebSocket ---
@router.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
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

