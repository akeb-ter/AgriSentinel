"""
AgriSentinel Pest Imagery Service

Provides entomological visual assets for the Pesticide & Agronomic Advisor:
1. Bundled offline SVG taxonomic specimen cards with order-specific anatomical silhouettes.
2. Auto-cached online entomological photography (Wikimedia Commons / Wikipedia API) with offline local disk caching.
3. Field detection retrieval: queries SQLite for the latest real farm snapshot of this pest.
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional

from edge.database import BASE_DIR, get_db_connection

logger = logging.getLogger("AgriSentinel-PestImagery")

PEST_IMAGES_DIR = os.path.join(BASE_DIR, "web", "static", "images", "pests")
os.makedirs(PEST_IMAGES_DIR, exist_ok=True)

# Taxonomic order classification keywords
TAXONOMIC_ORDERS = {
    "lepidoptera": ["borer", "armyworm", "army_worm", "cutworm", "leafroller", "leaf_roller", "moth", "caterpillar", "caterpiller", "bollworm", "looper"],
    "hemiptera": ["planthopper", "plant_hopper", "leafhopper", "leaf_hopper", "aphid", "scale", "whitefly", "bug", "psyllid", "mealybug"],
    "coleoptera": ["beetle", "weevil", "grub", "chafer", "wireworm"],
    "diptera": ["midge", "fly", "maggot", "leafminer", "leaf_miner"],
    "acari": ["mite", "spider_mite", "rust_mite", "broad_mite"],
    "thysanoptera": ["thrips"],
    "orthoptera": ["locust", "grasshopper", "cricket"]
}

# Stylized entomological SVG vector paths (viewBox 0 0 100 100)
SVG_ORDER_ICONS = {
    "lepidoptera": (
        '<path d="M50 20 C48 10 32 6 22 18 C12 30 18 52 32 60 C40 65 48 58 50 50 '
        'C52 58 60 65 68 60 C82 52 88 30 78 18 C68 6 52 10 50 20 Z" fill="#4ade80" fill-opacity="0.25" stroke="#4ade80" stroke-width="2.5"/>'
        '<path d="M50 50 C44 56 32 68 36 82 C40 92 48 88 50 75 C52 88 60 92 64 82 C68 68 56 56 50 50 Z" fill="#22c55e" fill-opacity="0.3" stroke="#22c55e" stroke-width="2"/>'
        '<ellipse cx="50" cy="46" rx="3.5" ry="24" fill="#86efac"/>'
        '<path d="M48 24 Q40 10 32 8 M52 24 Q60 10 68 8" stroke="#86efac" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
    ),
    "hemiptera": (
        '<path d="M50 16 L68 34 L62 76 L50 90 L38 76 L32 34 Z" fill="#38bdf8" fill-opacity="0.25" stroke="#38bdf8" stroke-width="2.5"/>'
        '<line x1="50" y1="34" x2="50" y2="86" stroke="#38bdf8" stroke-width="1.8"/>'
        '<path d="M38 42 L62 42 M35 56 L65 56" stroke="#7dd3fc" stroke-width="1.5" stroke-dasharray="2,2"/>'
        '<circle cx="50" cy="22" r="6" fill="#0284c7"/>'
        '<path d="M47 18 L40 8 M53 18 L60 8" stroke="#7dd3fc" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    "coleoptera": (
        '<path d="M50 22 C34 22 26 38 26 62 C26 78 36 90 50 92 C64 90 74 78 74 62 C74 38 66 22 50 22 Z" fill="#fbbf24" fill-opacity="0.25" stroke="#fbbf24" stroke-width="2.5"/>'
        '<line x1="50" y1="36" x2="50" y2="91" stroke="#f59e0b" stroke-width="2"/>'
        '<path d="M38 22 C38 14 62 14 62 22 Z" fill="#d97706" stroke="#fbbf24" stroke-width="1.8"/>'
        '<circle cx="45" cy="18" r="2" fill="#fff"/>'
        '<circle cx="55" cy="18" r="2" fill="#fff"/>'
    ),
    "diptera": (
        '<ellipse cx="50" cy="54" rx="8" ry="22" fill="#a78bfa" fill-opacity="0.4" stroke="#c4b5fd" stroke-width="2"/>'
        '<path d="M46 44 C28 22 10 32 18 56 C24 70 44 54 46 50 Z" fill="#818cf8" fill-opacity="0.25" stroke="#818cf8" stroke-width="2"/>'
        '<path d="M54 44 C72 22 90 32 82 56 C76 70 56 54 54 50 Z" fill="#818cf8" fill-opacity="0.25" stroke="#818cf8" stroke-width="2"/>'
        '<circle cx="50" cy="26" r="7" fill="#6d28d9"/>'
    ),
    "acari": (
        '<ellipse cx="50" cy="54" rx="20" ry="24" fill="#f87171" fill-opacity="0.25" stroke="#f87171" stroke-width="2.5"/>'
        '<ellipse cx="50" cy="28" rx="10" ry="8" fill="#ef4444" stroke="#f87171" stroke-width="1.8"/>'
        '<path d="M32 40 L16 32 M30 50 L12 50 M32 62 L14 70 M36 72 L20 86" stroke="#fca5a5" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M68 40 L84 32 M70 50 L88 50 M68 62 L86 70 M64 72 L80 86" stroke="#fca5a5" stroke-width="2" stroke-linecap="round"/>'
    ),
    "default": (
        '<ellipse cx="50" cy="52" rx="12" ry="24" fill="#34d399" fill-opacity="0.3" stroke="#34d399" stroke-width="2.5"/>'
        '<circle cx="50" cy="24" r="8" fill="#059669" stroke="#34d399" stroke-width="2"/>'
        '<path d="M46 18 L36 8 M54 18 L64 8" stroke="#6ee7b7" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M40 44 L20 38 M60 44 L80 38 M38 56 L18 58 M62 56 L82 58 M40 68 L22 76 M60 68 L78 76" stroke="#6ee7b7" stroke-width="1.8" stroke-linecap="round"/>'
    )
}


def classify_pest_order(pest_name: str, taxonomy: str = "") -> str:
    """Identifies the entomological order based on name keywords and taxonomic string."""
    combined = f"{pest_name} {taxonomy}".lower()
    for order, keywords in TAXONOMIC_ORDERS.items():
        if order in combined:
            return order
        for kw in keywords:
            if kw in combined:
                return order
    return "default"


def generate_pest_svg_specimen(pest_key: str, pest_info: Dict[str, Any]) -> str:
    """
    Generates a crisp, high-detail SVG entomological specimen card.
    Guaranteed offline visual rendering with scientific name and classification badges.
    """
    clean_name = pest_info.get("detected_pest") or pest_key.replace("_", " ").title()
    taxonomy = pest_info.get("taxonomy") or ""
    order = classify_pest_order(pest_key, taxonomy)
    order_label = order.capitalize()
    is_beneficial = bool(pest_info.get("is_beneficial") or "beneficial" in pest_key.lower())

    icon_svg = SVG_ORDER_ICONS.get(order, SVG_ORDER_ICONS["default"])
    badge_color = "#22c55e" if is_beneficial else "#ef4444"
    badge_text = "Beneficial Organism" if is_beneficial else f"Order: {order_label}"

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 260" width="100%" height="100%">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a" />
      <stop offset="100%" stop-color="#090d16" />
    </linearGradient>
    <linearGradient id="borderGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#334155" />
      <stop offset="100%" stop-color="#1e293b" />
    </linearGradient>
    <radialGradient id="glowGrad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{badge_color}" stop-opacity="0.18" />
      <stop offset="100%" stop-color="{badge_color}" stop-opacity="0" />
    </radialGradient>
  </defs>

  <!-- Card Background -->
  <rect x="2" y="2" width="416" height="256" rx="14" fill="url(#bgGrad)" stroke="url(#borderGrad)" stroke-width="2" />
  <circle cx="210" cy="118" r="85" fill="url(#glowGrad)" />

  <!-- Grid / Scientific Specimen Graph Backdrop -->
  <g stroke="#1e293b" stroke-width="0.8" opacity="0.6">
    <line x1="20" y1="50" x2="400" y2="50" />
    <line x1="20" y1="90" x2="400" y2="90" />
    <line x1="20" y1="130" x2="400" y2="130" />
    <line x1="20" y1="170" x2="400" y2="170" />
    <line x1="20" y1="210" x2="400" y2="210" />
    <line x1="70" y1="20" x2="70" y2="240" />
    <line x1="140" y1="20" x2="140" y2="240" />
    <line x1="210" y1="20" x2="210" y2="240" />
    <line x1="280" y1="20" x2="280" y2="240" />
    <line x1="350" y1="20" x2="350" y2="240" />
  </g>

  <!-- Specimen Icon Centerpiece -->
  <g transform="translate(160, 52) scale(1.0)">
    {icon_svg}
  </g>

  <!-- Header Badge -->
  <rect x="20" y="16" width="130" height="22" rx="11" fill="{badge_color}" fill-opacity="0.18" stroke="{badge_color}" stroke-width="1" />
  <text x="85" y="31" fill="{badge_color}" font-family="system-ui, -apple-system, sans-serif" font-size="11" font-weight="700" text-anchor="middle" letter-spacing="0.5">
    {badge_text.upper()}
  </text>

  <!-- Card Title -->
  <text x="20" y="200" fill="#f8fafc" font-family="system-ui, -apple-system, sans-serif" font-size="16" font-weight="700">
    {clean_name}
  </text>

  <!-- Subtitle / Taxonomy -->
  <text x="20" y="222" fill="#94a3b8" font-family="system-ui, -apple-system, sans-serif" font-size="11" font-style="italic">
    AgriSentinel Taxonomic Specimen Library • {pest_key}
  </text>

  <!-- Corner Specimen Index -->
  <text x="395" y="31" fill="#64748b" font-family="monospace" font-size="10" text-anchor="end">
    SPECIMEN #{abs(hash(pest_key)) % 9000 + 1000}
  </text>
</svg>"""

    svg_filename = f"{pest_key}.svg"
    svg_path = os.path.join(PEST_IMAGES_DIR, svg_filename)
    try:
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
    except Exception as e:
        logger.warning(f"Failed writing SVG specimen for {pest_key}: {e}")

    return f"/static/images/pests/{svg_filename}"


def fetch_online_pest_photo(pest_key: str, common_name: str) -> Optional[str]:
    """
    Fetches real entomological photograph thumbnail from Wikipedia / Wikimedia Commons API
    with a fast timeout (2.5s) and caches locally on disk so future requests are instantaneous and offline.
    """
    jpg_filename = f"{pest_key}.jpg"
    disk_path = os.path.join(PEST_IMAGES_DIR, jpg_filename)
    if os.path.exists(disk_path) and os.path.getsize(disk_path) > 1000:
        return f"/static/images/pests/{jpg_filename}"

    queries = [common_name, pest_key.replace("_", " ")]
    for q in queries:
        try:
            encoded_query = urllib.parse.quote(q.strip())
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_query}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AgriSentinel-Edge-Bot/1.0 (agrisentinel-research@deped.gov.ph)"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    thumb_url = data.get("thumbnail", {}).get("source")
                    if thumb_url:
                        # Download thumbnail
                        img_req = urllib.request.Request(
                            thumb_url,
                            headers={"User-Agent": "AgriSentinel-Edge-Bot/1.0"}
                        )
                        with urllib.request.urlopen(img_req, timeout=3.0) as img_resp:
                            img_bytes = img_resp.read()
                            if len(img_bytes) > 1000:
                                with open(disk_path, "wb") as f:
                                    f.write(img_bytes)
                                logger.info(f"[PestImagery] Successfully cached online photo for {pest_key}")
                                return f"/static/images/pests/{jpg_filename}"
        except Exception as e:
            logger.debug(f"[PestImagery] Online query for '{q}' skipped: {e}")
            continue

    return None


def get_latest_field_capture(pest_key: str) -> Optional[Dict[str, str]]:
    """Retrieves the most recent real camera detection snapshot for this pest from SQLite."""
    try:
        conn = get_db_connection()
        term = f"%{pest_key.replace('_', ' ')}%"
        row = conn.execute("""
            SELECT image_path, crop_image_path, timestamp, crop_type, detected_pest
            FROM detections
            WHERE LOWER(detected_pest) LIKE LOWER(?)
               OR LOWER(detected_pest) LIKE LOWER(?)
            ORDER BY id DESC LIMIT 1
        """, (term, f"%{pest_key}%")).fetchone()
        conn.close()

        if row:
            crop_path = row["crop_image_path"] if ("crop_image_path" in row.keys() and row["crop_image_path"]) else row["image_path"]
            return {
                "url": crop_path,
                "timestamp": row["timestamp"],
                "crop_type": row["crop_type"],
                "detected_pest": row["detected_pest"]
            }
    except Exception as e:
        logger.debug(f"[PestImagery] Field capture lookup error: {e}")

    return None


def get_or_create_pest_reference_image(pest_key: str, pest_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns visual assets for the Pesticide Advisor:
    - reference_url: real photo if cached/downloadable, else SVG card
    - svg_fallback_url: permanent offline vector card
    - latest_field_capture: recent farm snapshot if detected on farm
    """
    clean_key = pest_key.lower().replace(" ", "_").strip()
    common_name = pest_info.get("detected_pest") or clean_key.replace("_", " ").title()

    # 1. Guarantee offline SVG specimen card exists
    svg_url = generate_pest_svg_specimen(clean_key, pest_info)

    # 2. Check for locally cached photo or attempt fast online query
    photo_url = fetch_online_pest_photo(clean_key, common_name)

    # 3. Lookup real field capture from farm database
    field_capture = get_latest_field_capture(clean_key)

    primary_url = photo_url if photo_url else svg_url
    source = "online_cached" if photo_url else "svg_specimen"

    return {
        "reference_url": primary_url,
        "svg_fallback_url": svg_url,
        "has_photo": bool(photo_url),
        "source": source,
        "latest_field_capture": field_capture
    }
