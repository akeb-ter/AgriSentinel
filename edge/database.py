"""
AgriSentinel Database Management Module

Manages SQLite storage for:
- detections: rich inspection logs (pest count, plant health, pesticide advice, snapshot image)
- users_tbl: administrative credentials and authentication
"""

import os
import sqlite3
import datetime
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("AgriSentinel-Database")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "agrisentinel.db")
DETECTIONS_DIR = os.path.join(BASE_DIR, "web", "static", "detections")


def init_db():
    """Initializes and migrates the SQLite database schema."""
    os.makedirs(DETECTIONS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create modernized detections table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS detections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        crop_type TEXT NOT NULL,
        farm_area TEXT NOT NULL,
        detected_pest TEXT NOT NULL,
        pest_count INTEGER NOT NULL,
        infestation_level TEXT NOT NULL,
        soil_moisture_percent REAL NOT NULL,
        soil_status TEXT NOT NULL,
        plant_health_status TEXT NOT NULL,
        confidence REAL NOT NULL,
        recommended_pesticide TEXT,
        organic_alternative TEXT,
        dosage_instruction TEXT,
        safety_precautions TEXT,
        image_path TEXT,
        status TEXT NOT NULL
    )
    """)

    # Create users_tbl if not exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users_tbl (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        LASTNAME TEXT NOT NULL,
        FIRSTNAME TEXT NOT NULL,
        MIDDLENAME TEXT NOT NULL,
        USER_TYPE TEXT NOT NULL,
        AFFILIATION TEXT NOT NULL,
        ACCOUNT TEXT NOT NULL,
        PASSWORD TEXT NOT NULL
    )
    """)

    # Check if default admin user exists
    cursor.execute("SELECT COUNT(*) FROM users_tbl WHERE ACCOUNT = ?", ("vicente.labadia@deped.gov.ph",))
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO users_tbl (LASTNAME, FIRSTNAME, MIDDLENAME, USER_TYPE, AFFILIATION, ACCOUNT, PASSWORD) VALUES
        ('Labadia', 'Vicente', 'Beri', 'Administrator', 'Tacurong National High School', 'vicente.labadia@deped.gov.ph', '123')
        """)
        conn.commit()

    conn.commit()
    conn.close()
    logger.info(f"[Database] SQLite schema verified at {DB_PATH}")


def get_db_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with Row factory enabled."""
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def insert_detection(data: Dict[str, Any]) -> int:
    """Inserts a new detection record into the DBMS."""
    conn = get_db_connection()
    cursor = conn.cursor()

    ts = data.get("timestamp") or datetime.datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO detections (
        timestamp, crop_type, farm_area, detected_pest, pest_count,
        infestation_level, soil_moisture_percent, soil_status,
        plant_health_status, confidence, recommended_pesticide,
        organic_alternative, dosage_instruction, safety_precautions,
        image_path, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ts,
        data.get("crop_type", "corn"),
        data.get("farm_area", "Plot 1"),
        data.get("detected_pest", "Pest-Free"),
        int(data.get("pest_count", 0)),
        data.get("infestation_level", "None"),
        float(data.get("soil_moisture_percent", 0.0) or 0.0),
        str(data.get("soil_status", "N/A") or "N/A"),
        data.get("plant_health_status", "Healthy / Pest-Free"),
        float(data.get("confidence", 1.0)),
        data.get("recommended_pesticide", ""),
        data.get("organic_alternative", ""),
        data.get("dosage_instruction", ""),
        data.get("safety_precautions", ""),
        data.get("image_path", ""),
        data.get("status", "CONFIRMED")
    ))

    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def query_detections(
    crop_type: Optional[str] = None,
    infestation_level: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_confidence: Optional[float] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 25,
    offset: int = 0
) -> Dict[str, Any]:
    """Queries detections with rich multi-tier filters and pagination."""
    conn = get_db_connection()
    where_clauses = ["1=1"]
    params = []

    if crop_type and crop_type.lower() != "all":
        where_clauses.append("LOWER(crop_type) = ?")
        params.append(crop_type.lower().strip())

    if infestation_level and infestation_level.lower() != "all":
        where_clauses.append("LOWER(infestation_level) = ?")
        params.append(infestation_level.lower().strip())

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        where_clauses.append("(LOWER(detected_pest) LIKE ? OR LOWER(farm_area) LIKE ? OR LOWER(plant_health_status) LIKE ? OR LOWER(recommended_pesticide) LIKE ?)")
        params.extend([term, term, term, term])

    if start_date and start_date.strip():
        where_clauses.append("timestamp >= ?")
        params.append(start_date.strip())

    if end_date and end_date.strip():
        ed = end_date.strip()
        if len(ed) == 10:
            ed += "T23:59:59"
        where_clauses.append("timestamp <= ?")
        params.append(ed)

    if min_confidence is not None and float(min_confidence) > 0:
        where_clauses.append("confidence >= ?")
        params.append(float(min_confidence))

    if status and status.lower() != "all":
        where_clauses.append("LOWER(status) = ?")
        params.append(status.lower().strip())

    if source and source.lower() != "all":
        src = source.lower().strip()
        if "phone" in src:
            where_clauses.append("farm_area LIKE '%[Phone Camera]%'")
        elif "robot" in src or "probe" in src:
            where_clauses.append("farm_area NOT LIKE '%[Phone Camera]%'")

    where_sql = " AND ".join(where_clauses)

    count_sql = f"SELECT COUNT(*) FROM detections WHERE {where_sql}"
    total_count = conn.execute(count_sql, params).fetchone()[0]

    data_sql = f"SELECT * FROM detections WHERE {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
    data_params = list(params) + [max(1, int(limit)), max(0, int(offset))]
    rows = conn.execute(data_sql, data_params).fetchall()
    conn.close()

    return {
        "records": [dict(r) for r in rows],
        "total": total_count
    }


def get_recent_detections(
    limit: int = 50,
    crop_type: Optional[str] = None,
    infestation_level: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieves recent detections with optional basic filters."""
    res = query_detections(
        crop_type=crop_type,
        infestation_level=infestation_level,
        limit=limit,
        offset=0
    )
    return res["records"]


def get_detection_by_id(detection_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves single detection record by ID."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM detections WHERE id = ?", (detection_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_detection(detection_id: int) -> bool:
    """Deletes detection record and associated image file."""
    return delete_detections_batch([detection_id]) > 0


def delete_detections_batch(ids: List[int]) -> int:
    """Deletes multiple detection records and their snapshot image files."""
    if not ids:
        return 0

    valid_ids = [int(i) for i in ids if str(i).isdigit()]
    if not valid_ids:
        return 0

    placeholders = ",".join(["?"] * len(valid_ids))
    conn = get_db_connection()

    rows = conn.execute(
        f"SELECT image_path FROM detections WHERE id IN ({placeholders})",
        valid_ids
    ).fetchall()

    for r in rows:
        img_path = r["image_path"]
        if img_path:
            img_full = os.path.join(BASE_DIR, "web", img_path.lstrip("/"))
            if os.path.exists(img_full):
                try:
                    os.remove(img_full)
                except Exception as e:
                    logger.warning(f"Failed removing batch image {img_full}: {e}")

    cursor = conn.execute(
        f"DELETE FROM detections WHERE id IN ({placeholders})",
        valid_ids
    )
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count


def clear_detections(filters: Optional[Dict[str, Any]] = None, clear_all: bool = False) -> int:
    """
    Clears all detection records or only records matching active filters,
    removing their associated image files from disk.
    """
    conn = get_db_connection()

    if clear_all or not filters:
        rows = conn.execute("SELECT image_path FROM detections").fetchall()
        for r in rows:
            img_path = r["image_path"]
            if img_path:
                img_full = os.path.join(BASE_DIR, "web", img_path.lstrip("/"))
                if os.path.exists(img_full):
                    try:
                        os.remove(img_full)
                    except Exception as e:
                        logger.warning(f"Failed removing image {img_full}: {e}")

        cursor = conn.execute("DELETE FROM detections")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

    where_clauses = ["1=1"]
    params = []

    crop_type = filters.get("crop_type")
    if crop_type and crop_type.lower() != "all":
        where_clauses.append("LOWER(crop_type) = ?")
        params.append(crop_type.lower().strip())

    infestation_level = filters.get("infestation_level")
    if infestation_level and infestation_level.lower() != "all":
        where_clauses.append("LOWER(infestation_level) = ?")
        params.append(infestation_level.lower().strip())

    search = filters.get("search")
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        where_clauses.append("(LOWER(detected_pest) LIKE ? OR LOWER(farm_area) LIKE ? OR LOWER(plant_health_status) LIKE ? OR LOWER(recommended_pesticide) LIKE ?)")
        params.extend([term, term, term, term])

    start_date = filters.get("start_date")
    if start_date and start_date.strip():
        where_clauses.append("timestamp >= ?")
        params.append(start_date.strip())

    end_date = filters.get("end_date")
    if end_date and end_date.strip():
        ed = end_date.strip()
        if len(ed) == 10:
            ed += "T23:59:59"
        where_clauses.append("timestamp <= ?")
        params.append(ed)

    min_confidence = filters.get("min_confidence")
    if min_confidence is not None and float(min_confidence) > 0:
        where_clauses.append("confidence >= ?")
        params.append(float(min_confidence))

    status = filters.get("status")
    if status and status.lower() != "all":
        where_clauses.append("LOWER(status) = ?")
        params.append(status.lower().strip())

    source = filters.get("source")
    if source and source.lower() != "all":
        src = source.lower().strip()
        if "phone" in src:
            where_clauses.append("farm_area LIKE '%[Phone Camera]%'")
        elif "robot" in src or "probe" in src:
            where_clauses.append("farm_area NOT LIKE '%[Phone Camera]%'")

    where_sql = " AND ".join(where_clauses)

    rows = conn.execute(f"SELECT image_path FROM detections WHERE {where_sql}", params).fetchall()
    for r in rows:
        img_path = r["image_path"]
        if img_path:
            img_full = os.path.join(BASE_DIR, "web", img_path.lstrip("/"))
            if os.path.exists(img_full):
                try:
                    os.remove(img_full)
                except Exception as e:
                    logger.warning(f"Failed removing filtered image {img_full}: {e}")

    cursor = conn.execute(f"DELETE FROM detections WHERE {where_sql}", params)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def get_detection_stats() -> Dict[str, Any]:
    """Computes summary statistics across all detections."""
    conn = get_db_connection()
    total = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]

    severe_count = conn.execute(
        "SELECT COUNT(*) FROM detections WHERE infestation_level = 'Severe'"
    ).fetchone()[0]

    pest_summary = conn.execute("""
        SELECT detected_pest, COUNT(*) as count
        FROM detections
        WHERE detected_pest != 'Pest-Free'
        GROUP BY detected_pest
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()

    crop_summary = conn.execute("""
        SELECT crop_type, COUNT(*) as count
        FROM detections
        GROUP BY crop_type
        ORDER BY count DESC
    """).fetchall()

    avg_conf = conn.execute(
        "SELECT AVG(confidence) FROM detections WHERE confidence > 0"
    ).fetchone()[0]

    conn.close()

    return {
        "total_inspections": total,
        "severe_alerts": severe_count,
        "top_pests": [dict(r) for r in pest_summary],
        "crop_distribution": [dict(r) for r in crop_summary],
        "avg_confidence": round((avg_conf or 0.0) * 100, 1),
        "avg_soil_moisture": 0.0,
    }


if __name__ == "__main__":
    init_db()
    print("Database initialized and ready.")
