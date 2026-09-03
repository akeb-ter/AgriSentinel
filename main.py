import os
import uvicorn
from edge.camera_test import app

def main():
    """Main entry point for AgriSentinel."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    print("\n==================================================")
    print(" AgriSentinel Main Loop Starting")
    print(f" Web Interface: http://{host}:{port}")
    print("==================================================\n")
    
    # Start the FastAPI server containing the camera stream and web interface
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()

