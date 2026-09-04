import os
import sys
import cv2
import platform
import time
import argparse
from pathlib import Path

# Determine if we are on Windows (Mock Mode) or Linux (Real Inference)
IS_WINDOWS = platform.system() == 'Windows'

if not IS_WINDOWS:
    try:
        from edge_impulse_linux.image import ImageImpulseRunner
    except ImportError:
        print("ERROR: edge_impulse_linux package not found. Install it with: pip3 install edge_impulse_linux")
        sys.exit(1)

def main(model_path, camera_index=0, headless=False):
    print("[*] Starting Inference Test...")
    print(f"[*] Platform: {platform.system()} - {'MOCK MODE' if IS_WINDOWS else 'REAL MODE'}")
    print(f"[*] Mode: {'HEADLESS (Terminal logging)' if headless else 'GUI (cv2.imshow)'}")
    print(f"[*] Loading model: {model_path}")
    
    runner = None
    if not IS_WINDOWS:
        runner = ImageImpulseRunner(model_path)
        try:
            model_info = runner.init()
            print(f"[*] Model Info: {model_info}")
            # Automatically fetch labels from the Edge Impulse model properties
            labels = model_info['model_parameters']['labels']
            print(f"[*] Extracted Labels from Model: {labels}")
        except Exception as e:
            print(f"[!] Failed to initialize Edge Impulse runner: {e}")
            return
    else:
        print("[*] Running on Windows. The Linux AARCH64 .eim file cannot be executed directly.")
        print("[*] Initializing MOCK UI to test the camera and pipeline...")

    print(f"[*] Opening camera index {camera_index}...")
    if IS_WINDOWS:
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(camera_index)
        
    if not cap.isOpened():
        print(f"[!] Could not open camera at index {camera_index}.")
        return

    print("[*] Inference running. Press Ctrl+C in terminal (or 'q' in GUI window) to stop.\n")
    
    frame_count = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[!] Failed to grab frame from camera.")
                time.sleep(1)
                continue
                
            frame_count += 1
            detections = []
            
            # Perform Inference
            if IS_WINDOWS:
                # === MOCK MODE ===
                time.sleep(0.05)
                h, w = frame.shape[:2]
                box_x, box_y, box_w, box_h = int(w * 0.3), int(h * 0.3), int(w * 0.4), int(h * 0.4)
                detections.append({
                    "label": "pest_mock",
                    "confidence": 0.95,
                    "box": (box_x, box_y, box_w, box_h)
                })
            else:
                # === REAL INFERENCE MODE (Raspberry Pi) ===
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                try:
                    features, cropped = runner.get_features_from_image(rgb_frame)
                    res = runner.classify(features)
                    
                    if "bounding_boxes" in res.get("result", {}):
                        for bb in res["result"]["bounding_boxes"]:
                            confidence = bb.get('value', 0.0)
                            if confidence > 0.5:
                                detections.append({
                                    "label": bb.get('label', 'unknown'),
                                    "confidence": confidence,
                                    "box": (bb.get('x', 0), bb.get('y', 0), bb.get('width', 0), bb.get('height', 0))
                                })
                    elif "classification" in res.get("result", {}):
                        for label, confidence in res["result"]["classification"].items():
                            if confidence > 0.5:
                                detections.append({
                                    "label": label,
                                    "confidence": confidence,
                                    "box": None
                                })
                except Exception as e:
                    print(f"[!] Inference error: {e}")

            # Terminal Output (Always prints, perfect for SSH / Remote Shell)
            if detections:
                det_strs = [
                    f"{d['label']} ({d['confidence']*100:.1f}%)" + 
                    (f" @ box {d['box']}" if d['box'] else "") 
                    for d in detections
                ]
                print(f"[Frame {frame_count:04d}] DETECTED: {', '.join(det_strs)}")
            elif frame_count % 30 == 0:
                print(f"[Frame {frame_count:04d}] Scanning... (no pests detected)")

            # Optional GUI window (only when not headless)
            if not headless:
                for d in detections:
                    if d["box"]:
                        x, y, w_b, h_b = d["box"]
                        cv2.rectangle(frame, (x, y), (x + w_b, y + h_b), (0, 255, 0) if IS_WINDOWS else (255, 0, 0), 2)
                        cv2.putText(frame, f"{d['label']}: {d['confidence']:.2f}", (x, max(15, y - 10)), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if IS_WINDOWS else (255, 0, 0), 2)
                    else:
                        cv2.putText(frame, f"{d['label']}: {d['confidence']:.2f}", (10, 30), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                                    
                try:
                    cv2.imshow("Inference Output", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                except cv2.error:
                    print("[!] No GUI display detected. Switching automatically to headless mode.")
                    headless = True

    except KeyboardInterrupt:
        print("\n[*] Stopped by user.")

    # Cleanup
    print("[*] Cleaning up resources...")
    cap.release()
    if not headless:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
    if runner:
        runner.stop()
    print("[*] Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Edge Impulse Inference Testing")
    parser.add_argument("--headless", action="store_true", help="Run without opening a GUI window (for SSH/remote shell)")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--model", type=str, default=None, help="Path to .eim model file")
    args = parser.parse_args()

    base_dir = Path(__file__).parent
    if args.model:
        eim_path = Path(args.model)
    else:
        eim_path = base_dir / "models" / "agrisentinel-linux-aarch64-v5-impulse-#1.eim"
    
    if not eim_path.exists():
        print(f"[!] Error: Model file not found at {eim_path}")
        sys.exit(1)
        
    main(str(eim_path.absolute()), camera_index=args.camera, headless=args.headless)

