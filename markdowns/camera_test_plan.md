# Camera Test Implementation Plan

## Objective
Create a locally hosted camera test to verify the hardware (Camera Module/Webcam) is functioning correctly and can stream video. This aligns with the vision capture component outlined in `blueprint.md`.

## Proposed Approach
We will create a standalone Python script using the project's designated backend framework (FastAPI) and OpenCV. The script will capture frames from the camera and stream them as an MJPEG feed to a local web endpoint, allowing you to view the output in a browser.

## Files to Create
1. **`edge/camera_test.py`** [NEW]
   - Initializes OpenCV video capture (`cv2.VideoCapture(0)`).
   - Sets up a minimal FastAPI application.
   - Provides a generator function to yield JPEG-encoded frames.
   - Creates a `/video_feed` endpoint returning a `StreamingResponse`.
   - Creates a `/` (root) endpoint returning a simple HTML page with an `<img>` tag to display the stream.

2. **`requirements.txt`** [NEW]
   - Add necessary dependencies: `fastapi`, `uvicorn`, `opencv-python`.

## Verification Steps
1. Install dependencies via `pip install -r requirements.txt`.
2. Run the application using Uvicorn: `python -m uvicorn edge.camera_test:app --host 0.0.0.0 --port 8000`.
3. Open a web browser and navigate to `http://localhost:8000` or `http://127.0.0.1:8000` to see the live feed.

