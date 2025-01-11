import cv2
import datetime
import requests
import time
import io

API_URL = "http://192.168.0.101:8002/api/detect"
CAPTURE_INTERVAL = 10
CAMERA_INDEX = 0

def capture_and_send():
    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        print("Error: Unable to access the camera.")
        return

    try:
        print(f"Starting image capture. Images will be sent to '{API_URL}' every {CAPTURE_INTERVAL} seconds.")
        while True:
            ret, frame = camera.read()
            if not ret:
                print("Error: Unable to capture frame from camera.")
                break

            _, buffer = cv2.imencode('.jpg', frame)
            image_bytes = io.BytesIO(buffer)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                response = requests.post(API_URL, files={'file': ('image.jpg', image_bytes.getvalue())})
            except requests.exceptions.RequestException as e:
                print(f"Error sending image to API: {e}")
                continue
            
            if response.status_code == 200:
                print(f"[{timestamp}] Image processed successfully. Annotated image received.")
            else:
                print(f"[{timestamp}] API Error: {response.status_code} - {response.text}")

            time.sleep(CAPTURE_INTERVAL)

    except KeyboardInterrupt:
        print("\nImage capture stopped by user.")

    finally:
        camera.release()
        print("Camera released.")

if __name__ == "__main__":
    capture_and_send()
