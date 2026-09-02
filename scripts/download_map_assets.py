"""
AgriSentinel - Unified Offline Map Asset Downloader
Downloads:
1. Vector PMTiles archive via Protomaps (crisp roads, paths, labels, water, boundaries)
2. Satellite raster imagery tiles via Esri World Imagery

Supports automatic cross-platform binary setup (Windows x64, Linux ARM64 for Pi, Linux x64).

Usage:
    python scripts/download_map_assets.py --lat 6.681023 --lon 124.689331 --radius 30
"""

import os
import sys
import math
import time
import json
import ssl
import platform
import zipfile
import tarfile
import io
import argparse
import subprocess
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}

ESRI_SATELLITE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def get_bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.32
    lon_delta = radius_km / (111.32 * math.cos(math.radians(lat)))
    return (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)


def ensure_pmtiles_binary() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bin_dir = os.path.join(base_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        exe_path = os.path.join(bin_dir, "pmtiles.exe")
        asset_name = "go-pmtiles_1.31.2_Windows_x86_64.zip"
        is_zip = True
    elif system == "linux":
        exe_path = os.path.join(bin_dir, "pmtiles")
        if "aarch64" in machine or "arm64" in machine or "armv8" in machine:
            asset_name = "go-pmtiles_1.31.2_Linux_arm64.tar.gz"
        else:
            asset_name = "go-pmtiles_1.31.2_Linux_x86_64.tar.gz"
        is_zip = False
    elif system == "darwin":
        exe_path = os.path.join(bin_dir, "pmtiles")
        asset_name = "go-pmtiles-1.31.2_Darwin_arm64.zip" if "arm" in machine else "go-pmtiles-1.31.2_Darwin_x86_64.zip"
        is_zip = True
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")

    if os.path.exists(exe_path) and os.path.getsize(exe_path) > 1000:
        return exe_path

    print(f"[*] Downloading pmtiles CLI binary ({asset_name})...")
    url = f"https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/{asset_name}"
    req = urllib.request.Request(url, headers=HEADERS)

    with urllib.request.urlopen(req, context=ssl_ctx) as resp:
        content = resp.read()

    if is_zip:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            z.extractall(bin_dir)
    else:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            tar.extractall(bin_dir)

    if not system == "windows":
        os.chmod(exe_path, 0o755)

    print(f"[OK] pmtiles installed to: {exe_path}")
    return exe_path


def get_latest_protomaps_build_url() -> str:
    try:
        req = urllib.request.Request("https://build-metadata.protomaps.dev/builds.json", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as r:
            data = json.loads(r.read())
            latest_key = data[-1]["key"]
            return f"https://build.protomaps.com/{latest_key}"
    except Exception as e:
        print(f"[!] Warning: Could not query latest build ({e}), falling back to standard URL.")
        return "https://build.protomaps.com/20260902.pmtiles"


def extract_vector_pmtiles(pmtiles_bin: str, min_lon: float, min_lat: float, max_lon: float, max_lat: float, max_zoom: int, output_path: str):
    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[OK] Vector PMTiles extract already exists at {output_path} ({size_mb:.2f} MB). Skipping extract.")
        return

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    remote_build = get_latest_protomaps_build_url()
    bbox_str = f"{min_lon:.6f},{min_lat:.6f},{max_lon:.6f},{max_lat:.6f}"

    print(f"\n[*] Extracting Vector PMTiles from: {remote_build}")
    print(f"    Bounding Box: {bbox_str} (Max Zoom: {max_zoom})")

    cmd = [
        pmtiles_bin,
        "extract",
        remote_build,
        output_path,
        f"--bbox={bbox_str}",
        f"--maxzoom={max_zoom}",
        "--download-threads=8",
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[!] PMTiles extraction failed with exit code {result.returncode}")
    else:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[OK] Vector PMTiles extract saved to {output_path} ({size_mb:.2f} MB)")


def download_single_satellite_tile(item: tuple[int, int, int, str]) -> bool:
    zoom, x, y, output_dir = item
    tile_dir = os.path.join(output_dir, str(zoom), str(x))
    os.makedirs(tile_dir, exist_ok=True)
    tile_path = os.path.join(tile_dir, f"{y}.jpg")

    if os.path.exists(tile_path) and os.path.getsize(tile_path) > 500:
        return True

    url = ESRI_SATELLITE_URL.format(z=zoom, x=x, y=y)
    req = urllib.request.Request(url, headers=HEADERS)

    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as response:
                content = response.read()
                if len(content) > 300:
                    with open(tile_path, "wb") as f:
                        f.write(content)
                    return True
        except Exception:
            time.sleep(0.05)

    return False


def download_satellite_tiles(min_lat: float, max_lat: float, min_lon: float, max_lon: float, min_zoom: int, max_zoom: int, threads: int, output_dir: str):
    print(f"\n[*] Preparing Satellite Imagery Tiles ({min_zoom} to {max_zoom})...")
    tasks = []
    for z in range(min_zoom, max_zoom + 1):
        x_min, y_max = deg2num(min_lat, min_lon, z)
        x_max, y_min = deg2num(max_lat, max_lon, z)

        x_start, x_end = min(x_min, x_max), max(x_min, x_max)
        y_start, y_end = min(y_min, y_max), max(y_min, y_max)

        for x in range(x_start, x_end + 1):
            for y in range(y_start, y_end + 1):
                tasks.append((z, x, y, output_dir))

    total = len(tasks)
    print(f"[*] Downloading {total} satellite tiles across {threads} threads...")

    downloaded = 0
    failed = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(download_single_satellite_tile, t): t for t in tasks}
        for future in as_completed(futures):
            ok = future.result()
            if ok:
                downloaded += 1
            else:
                failed += 1

            done = downloaded + failed
            if done % 25 == 0 or done == total:
                progress = done / total * 100
                rate = done / max(0.1, time.time() - start_time)
                sys.stdout.write(f"\r    Progress: {progress:5.1f}% ({done}/{total} | {rate:.1f} tiles/s | {failed} failed)")
                sys.stdout.flush()

    elapsed = time.time() - start_time
    print(f"\n[OK] Satellite download finished in {elapsed:.1f}s ({downloaded} tiles saved to {output_dir})")


def main():
    parser = argparse.ArgumentParser(description="AgriSentinel Offline Map Asset Downloader (PMTiles + Satellite)")
    parser.add_argument("--lat", type=float, default=6.681023, help="Center latitude")
    parser.add_argument("--lon", type=float, default=124.689331, help="Center longitude")
    parser.add_argument("--radius", type=float, default=30.0, help="Radius in kilometers (default: 30 km)")
    parser.add_argument("--min-zoom", type=int, default=11, help="Minimum satellite zoom level (default: 11)")
    parser.add_argument("--max-zoom", type=int, default=15, help="Maximum zoom level (default: 15)")
    parser.add_argument("--threads", type=int, default=20, help="Concurrent download threads (default: 20)")
    parser.add_argument("--pmtiles-out", type=str, default="web/static/basemap.pmtiles", help="Output PMTiles file")
    parser.add_argument("--satellite-out", type=str, default="web/static/tiles/satellite", help="Output satellite tiles dir")

    args = parser.parse_args()

    min_lat, max_lat, min_lon, max_lon = get_bounding_box(args.lat, args.lon, args.radius)

    print("========================================================")
    print("      AgriSentinel Offline Map Asset Downloader")
    print("========================================================")
    print(f"  Center:         {args.lat:.6f}, {args.lon:.6f}")
    print(f"  Radius:         {args.radius:.1f} km")
    print(f"  Lat Range:      [{min_lat:.6f}, {max_lat:.6f}]")
    print(f"  Lon Range:      [{min_lon:.6f}, {max_lon:.6f}]")
    print(f"  PMTiles Output: {os.path.abspath(args.pmtiles_out)}")
    print(f"  Satellite Dir:  {os.path.abspath(args.satellite_out)}")
    print("========================================================")

    pmtiles_bin = ensure_pmtiles_binary()
    extract_vector_pmtiles(pmtiles_bin, min_lon, min_lat, max_lon, max_lat, args.max_zoom, args.pmtiles_out)
    download_satellite_tiles(min_lat, max_lat, min_lon, max_lon, args.min_zoom, args.max_zoom, args.threads, args.satellite_out)
    print("\n[SUCCESS] All offline vector & satellite map assets are ready!")


if __name__ == "__main__":
    main()
