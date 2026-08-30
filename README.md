# AgriSentinel - Autonomous Crop Protection Robot

AgriSentinel is an AI-assisted autonomous crop protection robot utilizing species-specific adaptive frequency repellent technology.

---

## Camera Subsystem Testing

The `edge/camera_test.py` module provides a standalone local FastAPI server streaming live video from the connected camera module / webcam via OpenCV.

### Prerequisites

Ensure the dependencies are installed:
```bash
pip install -r requirements.txt
```

### Running the Camera Test Server

You can run the camera test server using either of the following commands:

```bash
# Option 1: Direct Python execution
python -m edge.camera_test

# Option 2: Using Uvicorn directly
uvicorn edge.camera_test:app --host 0.0.0.0 --port 8000 --reload
```

### Accessing the Live Stream & Diagnostics

Open your browser and navigate to:
* **Web UI Dashboard:** [http://localhost:8000](http://localhost:8000)
* **Raw Video MJPEG Stream:** [http://localhost:8000/video_feed](http://localhost:8000/video_feed)
* **Camera Diagnostics JSON:** [http://localhost:8000/api/camera/status](http://localhost:8000/api/camera/status)
* **Single Snapshot JPEG:** [http://localhost:8000/api/camera/snapshot](http://localhost:8000/api/camera/snapshot)

### Running Automated Tests

Run pytest to verify the camera streaming and endpoints:
```bash
pytest tests/ -v
```

