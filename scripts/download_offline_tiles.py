"""
AgriSentinel - Offline Map Tile Downloader Utility
Fast multi-threaded downloader for offline map tiles.

Supports multiple reliable high-speed tile providers:
- 'carto' (Default: Clean high-contrast street map)
- 'satellite' (Real high-resolution aerial / field satellite imagery)
- 'osm-hot' (Humanitarian OpenStreetMap mirror)
- 'osm' (Standard OpenStreetMap)

Usage:
    # 30km radius covering regional (zoom 11) to street level (zoom 16)
    python scripts/download_offline_tiles.py --lat 6.681023 --lon 124.689331 --radius 30 --min-zoom 11 --max-zoom 15
"""

import os
import sys
import math
import time
import ssl
import argparse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# Modern browser headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "https://www.openstreetmap.org/",
}

# Tile Provider URL Templates
PROVIDERS = {
    "carto": "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    "satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "osm-hot": "https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
    "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}

# Create permissive SSL context
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    """Converts Latitude & Longitude in degrees to Slippy Map tile X and Y coordinates."""
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def get_bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Calculates min_lat, max_lat, min_lon, max_lon for a given center coordinate and radius."""
    lat_delta = radius_km / 111.32
    lon_delta = radius_km / (111.32 * math.cos(math.radians(lat)))
    return (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)


def download_single_tile(item: tuple[int, int, int, str, str]) -> bool:
    """Worker function to download a single tile."""
    zoom, x, y, output_dir, source = item
    tile_dir = os.path.join(output_dir, str(zoom), str(x))
    os.makedirs(tile_dir, exist_ok=True)
    tile_path = os.path.join(tile_dir, f"{y}.png")

    if os.path.exists(tile_path) and os.path.getsize(tile_path) > 500:
        return True  # Already cached

    url_template = PROVIDERS.get(source, PROVIDERS["carto"])
    url = url_template.format(z=zoom, x=x, y=y)
    req = urllib.request.Request(url, headers=HEADERS)

    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
                content = response.read()
                if len(content) > 200:
                    with open(tile_path, "wb") as f:
                        f.write(content)
                    return True
        except Exception:
            time.sleep(0.05)

    return False


def main():
    parser = argparse.ArgumentParser(description="AgriSentinel Fast Offline Map Tile Downloader")
    parser.add_argument("--lat", type=float, default=6.681023, help="Center latitude")
    parser.add_argument("--lon", type=float, default=124.689331, help="Center longitude")
    parser.add_argument("--radius", type=float, default=30.0, help="Radius in kilometers (default: 30 km)")
    parser.add_argument("--min-zoom", type=int, default=11, help="Minimum zoom level (default: 11)")
    parser.add_argument("--max-zoom", type=int, default=15, help="Maximum zoom level (default: 15)")
    parser.add_argument("--source", type=str, default="carto", choices=["carto", "satellite", "osm-hot", "osm"],
                        help="Tile provider source: 'carto' (default), 'satellite', 'osm-hot', 'osm'")
    parser.add_argument("--threads", type=int, default=16, help="Concurrent download threads (default: 16)")
    parser.add_argument("--output", type=str, default="web/static/tiles", help="Output directory")

    args = parser.parse_args()

    min_lat, max_lat, min_lon, max_lon = get_bounding_box(args.lat, args.lon, args.radius)

    print("\n========================================================")
    print("      AgriSentinel High-Speed Map Tile Downloader")
    print("========================================================")
    print(f"  Center:       {args.lat:.6f}, {args.lon:.6f}")
    print(f"  Radius:       {args.radius:.1f} km")
    print(f"  Source:       {args.source.upper()} ({PROVIDERS[args.source]})")
    print(f"  Lat Range:    [{min_lat:.6f}, {max_lat:.6f}]")
    print(f"  Lon Range:    [{min_lon:.6f}, {max_lon:.6f}]")
    print(f"  Zoom Levels:  {args.min_zoom} to {args.max_zoom}")
    print(f"  Threads:      {args.threads}")
    print(f"  Output Dir:   {os.path.abspath(args.output)}")
    print("--------------------------------------------------------")

    tasks = []
    for z in range(args.min_zoom, args.max_zoom + 1):
        x_min, y_max = deg2num(min_lat, min_lon, z)
        x_max, y_min = deg2num(max_lat, max_lon, z)

        x_start, x_end = min(x_min, x_max), max(x_min, x_max)
        y_start, y_end = min(y_min, y_max), max(y_min, y_max)

        count = (x_end - x_start + 1) * (y_end - y_start + 1)
        print(f"  Zoom {z:02d}: {count:5d} tiles (X: {x_start}..{x_end}, Y: {y_start}..{y_end})")

        for x in range(x_start, x_end + 1):
            for y in range(y_start, y_end + 1):
                tasks.append((z, x, y, args.output, args.source))

    total_tiles = len(tasks)
    print("--------------------------------------------------------")
    print(f"  Total Tiles to Download: {total_tiles}")
    print("========================================================\n")

    start_time = time.time()
    downloaded = 0
    failed = 0

    print(f"[*] Downloading {total_tiles} tiles across {args.threads} threads...")

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(download_single_tile, item): item for item in tasks}
        for future in as_completed(futures):
            ok = future.result()
            if ok:
                downloaded += 1
            else:
                failed += 1

            done = downloaded + failed
            if done % 20 == 0 or done == total_tiles:
                progress = done / total_tiles * 100
                rate = done / max(0.1, time.time() - start_time)
                sys.stdout.write(f"\r    Progress: {progress:5.1f}% ({done}/{total_tiles} | {rate:.1f} tiles/s | {failed} failed)")
                sys.stdout.flush()

    elapsed = time.time() - start_time
    print(f"\n\n[OK] Completed in {elapsed:.1f}s ({downloaded / max(0.1, elapsed):.1f} tiles/sec).")
    print(f"    Saved {downloaded} tiles to `{args.output}` for 100% offline usage!\n")


if __name__ == "__main__":
    main()
