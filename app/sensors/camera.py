import cv2
import datetime
import requests
import time
import io

class CameraCapture:
    def __init__(self):
        """
        Initializes the CameraCapture instance.

        :param api_url: The URL of the API to send images to.
        :param capture_interval: Time interval (in seconds) between captures.
        :param camera_index: Index of the camera to use.
        """
        self.api_url = "https://lettuce.ebasura.online/api/detect"
        self.capture_interval = 1
        self.camera_index = 0
        self.camera = cv2.VideoCapture(self.camera_index)

        if not self.camera.isOpened():
            raise RuntimeError("Error: Unable to access the camera.")

    def capture_frame(self):
        """
        Captures a frame from the camera.
        :return: Captured frame or None if capture fails.
        """
        ret, frame = self.camera.read()
        if not ret:
            print("Error: Unable to capture frame from camera.")
            return None
        return frame

    def send_image(self, image):
        """
        Sends the captured image to the API.
        :param image: The image to send.
        """
        _, buffer = cv2.imencode('.jpg', image)
        image_bytes = io.BytesIO(buffer)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            response = requests.post(self.api_url, files={'file': ('image.jpg', image_bytes.getvalue())})
        except requests.exceptions.RequestException as e:
            print(f"[{timestamp}] Error sending image to API: {e}")
            return

        if response.status_code == 200:
            print(f"[{timestamp}] Image processed successfully. Annotated image received.")
        else:
            print(f"[{timestamp}] API Error: {response.status_code} - {response.text}")

    def start(self):
        """
        Starts the capture and send process.
        """
        try:
            print(f"Starting image capture. Images will be sent to '{self.api_url}' every {self.capture_interval} seconds.")
            while True:
                frame = self.capture_frame()
                if frame is not None:
                    self.send_image(frame)
                time.sleep(self.capture_interval)
        except KeyboardInterrupt:
            print("\nImage capture stopped by user.")
        finally:
            self.cleanup()

    def cleanup(self):
        """
        Releases the camera resource.
        """
        self.camera.release()
        print("Camera released.")


