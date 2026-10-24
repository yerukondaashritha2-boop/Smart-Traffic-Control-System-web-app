import cv2
import serial
import time
from ultralytics import YOLO

# ==========================================
# CONFIGURATION
# ==========================================
# 1. ESP32-CAM Stream URL (Replace with the IP printed in your Arduino Serial Monitor)
STREAM_URL = "http://192.168.1.100/stream"

# 2. Arduino Serial Port (e.g., 'COM3' for Windows, '/dev/ttyACM0' for Linux/Mac)
ARDUINO_PORT = "COM3"
BAUD_RATE = 9600

# 3. YOLO Model
# For a real project, train a YOLOv8 model specifically for Indian Ambulances.
# For testing, we will use the standard YOLOv8 nano model (downloads automatically).
MODEL_PATH = "yolov8n.pt" 
AMBULANCE_CLASS_ID = 2  # In standard COCO dataset, 2 = 'car', 7 = 'truck'. 
                        # Change this to your custom Ambulance class ID once trained.

# ==========================================
# INITIALIZATION
# ==========================================
print("[INFO] Connecting to Arduino on {}...".format(ARDUINO_PORT))
try:
    arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
    time.sleep(2) # Give Arduino time to reset after serial connection
    print("[INFO] Arduino connected successfully.")
except Exception as e:
    print(f"[ERROR] Could not connect to Arduino: {e}")
    exit()

print("[INFO] Loading YOLO model...")
model = YOLO(MODEL_PATH)

print(f"[INFO] Connecting to ESP32-CAM stream at {STREAM_URL}...")
cap = cv2.VideoCapture(STREAM_URL)

if not cap.isOpened():
    print("[ERROR] Failed to open video stream. Check IP address and Wi-Fi connection.")
    exit()

# State variables
emergency_active = False
frames_without_ambulance = 0
DEBOUNCE_THRESHOLD = 15 # Wait for 15 consecutive frames without detection before resetting

# ==========================================
# MAIN LOOP
# ==========================================
while True:
    ret, frame = cap.read()
    if not ret:
        print("[WARNING] Frame dropped or stream disconnected. Reconnecting...")
        cap = cv2.VideoCapture(STREAM_URL)
        time.sleep(1)
        continue

    # Run YOLOv8 inference
    results = model(frame, verbose=False)
    
    ambulance_detected_in_frame = False

    # Parse detections
    for result in results:
        boxes = result.boxes
        for box in boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])
            
            # Check if detected object is our target class with > 50% confidence
            if class_id == AMBULANCE_CLASS_ID and confidence > 0.50:
                ambulance_detected_in_frame = True
                
                # Draw bounding box for visualization
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(frame, f"AMBULANCE: {confidence:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # ------------------------------------------
    # PRIORITY LOGIC & ARDUINO COMMUNICATION
    # ------------------------------------------
    if ambulance_detected_in_frame:
        frames_without_ambulance = 0 # Reset counter
        if not emergency_active:
            print("[ALERT] Ambulance detected! Sending Priority Request to Arduino...")
            arduino.write(b'A')
            emergency_active = True
    else:
        # If we had an emergency, but the ambulance is gone, wait a few frames (debounce) 
        # to ensure it wasn't just a missed detection glitch.
        if emergency_active:
            frames_without_ambulance += 1
            if frames_without_ambulance >= DEBOUNCE_THRESHOLD:
                print("[INFO] Ambulance cleared. Restoring Normal Operation...")
                arduino.write(b'N')
                emergency_active = False

    # Overlay System Status on the video feed
    status_text = "STATUS: PRIORITY OVERRIDE" if emergency_active else "STATUS: NORMAL ADAPTIVE"
    color = (0, 0, 255) if emergency_active else (0, 255, 0)
    cv2.putText(frame, status_text, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # Display the frame
    cv2.imshow("ESP32-CAM Smart Traffic Control", frame)

    # Press 'q' to quit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup
cap.release()
cv2.destroyAllWindows()
arduino.close()
print("[INFO] System shutdown.")
