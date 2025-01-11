import cv2
import os
import datetime
import requests

# Configuration
API_URL = "http://192.168.0.101:8002/api/detect"  # Replace with your API endpoint
SAVE_DIRECTORY = "captured_images"
os.makedirs(SAVE_DIRECTORY, exist_ok=True)

CAPTURE_INTERVAL = 10  # Capture an image every 10 seconds
CAMERA_INDEX = 0  # Use 0 for the first connected USB camera


def capture_and_send():
    # Open the USB camera
    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        print("Error: Unable to access the camera.")
        return

    try:
        print(f"Starting image capture. Images will be sent to '{API_URL}' every {CAPTURE_INTERVAL} seconds.")
        while True:
            # Capture a frame
            ret, frame = camera.read()
            if not ret:
                print("Error: Unable to capture frame from camera.")
                break

            # Generate a unique filename with a timestamp
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            image_path = os.path.join(SAVE_DIRECTORY, f"image_{timestamp}.jpg")

            # Save the captured image locally
            #cv2.imwrite(image_path, frame)
            print(f"Image captured and saved to: {image_path}")

            # Send the image to the API
            with open(image_path, 'rb') as img_file:
                response = requests.post(API_URL, files={'file': img_file})
            
            # Handle the response
            if response.status_code == 200:
                # Save the annotated image from the API response
                result_image_path = os.path.join(SAVE_DIRECTORY, f"result_{timestamp}.jpg")
                with open(result_image_path, 'wb') as result_file:
                    result_file.write(response.content)
                print(f"Annotated image saved to: {result_image_path}")
            else:
                print(f"API Error: {response.status_code} - {response.text}")

            # Wait for the next capture
            cv2.waitKey(CAPTURE_INTERVAL * 1000)

    except KeyboardInterrupt:
        print("\nImage capture stopped by user.")

    finally:
        # Release the camera
        camera.release()
        print("Camera released.")


if __name__ == "__main__":
    capture_and_send()
