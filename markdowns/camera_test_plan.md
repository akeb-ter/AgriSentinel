# Camera Test Implementation Plan (v1.1)

## Objective
Create a locally hosted camera test server to verify hardware vision capture on the Raspberry Pi 4 using the native `rpicam-vid` / `libcamera-vid` streaming pipeline with OpenCV and synthetic fallbacks.

## Architecture

### 1. Native Raspberry Pi Backend (`rpicam-vid` / `libcamera-vid`)
- Modern Raspberry Pi OS (Bullseye / Bookworm) utilizes the `libcamera` architecture.
- `RpiCamReader` spawns `rpicam-vid` (or `libcamera-vid`) in MJPEG streaming mode piping directly to `stdout`.
- Fast, zero-lag frame parser reconstructs JPEG frames using binary markers (`0xFFD8` to `0xFFD9`).

### 2. OpenCV Fallback
- Used when running on PC/Mac or when using a USB webcam.

### 3. Synthetic Test Pattern Fallback
- Serves an animated diagnostic test pattern if no physical camera is detected.

## Endpoints
- `/` - Modern Dark UI Dashboard
- `/video_feed` - Multipart MJPEG Stream
- `/api/camera/status` - JSON Diagnostics (Backend mode, FPS, Resolution, Frames)
- `/api/camera/snapshot` - Single JPEG frame capture
