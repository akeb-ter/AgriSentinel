"""
AgriSentinel - Offline Map Tile Downloader Utility
Downloads OpenStreetMap tiles for a specified geographic area (GPS coordinate + radius)
and saves them into `web/static/tiles/{z}/{x}/{y}.png` for 100% offline map viewing.

Usage:
    python scripts/download_offline_tiles.py --lat 14.5995 --lon 120.9842 --radius 2 --min-zoom 13 --max-zoom 17

Options:
    --lat        Target latitude (decimal degrees, e.g. 14.599512)
    --lon        Target longitude (decimal degrees, e.g. 120.984222)
    --radius     Coverage radius in kilometers (default: 2.0 km)
    --min-zoom   Minimum zoom level (default: 13 - town level)
    --max-zoom   Maximum zoom level (default: 17 - building/field level)
    --output     Target directory (default: web/static/tiles)
"""

import os
import sys
import math
import time
import ssl
import argparse
import urllib.request
import urllib.error

# User-Agent header (Required by OpenStreetMap tile usage policy)
USER_AGENT = "AgriSentinel-Offline-Map-Downloader/1.0 (agrisentinel-project; agricultural-robot)"

# Create permissive SSL context to handle systems without bundled CA certs
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


def download_tile(zoom: int, x: int, y: int, output_dir: str) -> bool:
    """Downloads a single OSM tile and stores it into output_dir/{z}/{x}/{y}.png."""
    tile_dir = os.path.join(output_dir, str(zoom), str(x))
    os.makedirs(tile_dir, exist_ok=True)
    tile_path = os.path.join(tile_dir, f"{y}.png")

    if os.path.exists(tile_path) and os.path.getsize(tile_path) > 500:
        return True  # Already cached

    url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            content = response.read()
            if len(content) > 100:
                with open(tile_path, "wb") as f:
                    f.write(content)
                return True
    except urllib.error.HTTPError as e:
        print(f"\n [!] HTTP Error downloading tile {zoom}/{x}/{y}: {e.code}")
    except Exception as e:
        print(f"\n [!] Error downloading tile {zoom}/{x}/{y}: {e}")

    return False


def main():
    parser = argparse.ArgumentParser(description="AgriSentinel Offline Map Tile Downloader")
    parser.add_argument("--lat", type=float, default=14.5995, help="Center latitude (e.g. 14.5995)")
    parser.add_argument("--lon", type=float, default=120.9842, help="Center longitude (e.g. 120.9842)")
    parser.add_argument("--radius", type=float, default=2.0, help="Radius in kilometers (default: 2.0 km)")
    parser.add_argument("--min-zoom", type=int, default=13, help="Minimum zoom level (default: 13)")
    parser.add_argument("--max-zoom", type=int, default=17, help="Maximum zoom level (default: 17)")
    parser.add_argument("--output", type=str, default="web/static/tiles", help="Output directory")

    args = parser.parse_args()

    min_lat, max_lat, min_lon, max_lon = get_bounding_box(args.lat, args.lon, args.radius)

    print("\n========================================================")
    print("      AgriSentinel Offline Map Tile Downloader")
    print("========================================================")
    print(f"  Center:       {args.lat:.6f}, {args.lon:.6f}")
    print(f"  Radius:       {args.radius:.1f} km")
    print(f"  Lat Range:    [{min_lat:.6f}, {max_lat:.6f}]")
    print(f"  Lon Range:    [{min_lon:.6f}, {max_lon:.6f}]")
    print(f"  Zoom Levels:  {args.min_zoom} to {args.max_zoom}")
    print(f"  Output Dir:   {os.path.abspath(args.output)}")
    print("--------------------------------------------------------")

    total_tiles = 0
    plan = []
    for z in range(args.min_zoom, args.max_zoom + 1):
        x_min, y_max = deg2num(min_lat, min_lon, z)
        x_max, y_min = deg2num(max_lat, max_lon, z)

        # Handle coordinate ordering
        x_start, x_end = min(x_min, x_max), max(x_min, x_max)
        y_start, y_end = min(y_min, y_max), max(y_min, y_max)

        count = (x_end - x_start + 1) * (y_end - y_start + 1)
        total_tiles += count
        plan.append((z, x_start, x_end, y_start, y_end, count))
        print(f"  Zoom {z:02d}: {count:4d} tiles (X: {x_start}..{x_end}, Y: {y_start}..{y_end})")

    print("--------------------------------------------------------")
    print(f"  Total Tiles to Download: {total_tiles}")
    print("========================================================\n")

    if total_tiles > 5000:
        print(" [!] WARNING: More than 5,000 tiles requested. Consider lowering radius or max zoom.")
        confirm = input(" Proceed with download? (y/N): ").strip().lower()
        if confirm != "y":
            print(" Download aborted.")
            return

    downloaded = 0
    failed = 0
    start_time = time.time()

    for z, x_start, x_end, y_start, y_end, count in plan:
        print(f"[*] Downloading Zoom level {z} ({count} tiles)...")
        for x in range(x_start, x_end + 1):
            for y in range(y_start, y_end + 1):
                ok = download_tile(z, x, y, args.output)
                if ok:
                    downloaded += 1
                else:
                    failed += 1

                progress = (downloaded + failed) / total_tiles * 100
                sys.stdout.write(f"\r    Progress: {progress:5.1f}% ({downloaded}/{total_tiles} downloaded, {failed} failed)")
                sys.stdout.flush()
                # Polite rate limiting (80ms per tile to respect OSM server capacity)
                time.sleep(0.08)
        print()

    elapsed = time.time() - start_time
    print(f"\n[OK] Finished in {elapsed:.1f}s. Successfully saved {downloaded} tiles to `{args.output}`.")
    print("    These tiles are now ready for 100% offline usage on the AgriSentinel dashboard!\n")


if __name__ == "__main__":
    main()

