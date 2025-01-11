import RPi.GPIO as GPIO
import time
import logging
import traceback

class UltrasonicSensor:
    def __init__(self, trig_pin: int, echo_pin: int):
        self.trig_pin = trig_pin
        self.echo_pin = echo_pin
        self.setup_gpio()

    def setup_gpio(self):
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.trig_pin, GPIO.OUT)
            GPIO.setup(self.echo_pin, GPIO.IN)
            GPIO.output(self.trig_pin, False)
            time.sleep(2)  # Allow sensor to settle
            logging.info(f"UltrasonicSensor GPIO setup successful (Trig: {self.trig_pin}, Echo: {self.echo_pin}).")
        except Exception as e:
            logging.error(f"GPIO setup failed: {e}\n{traceback.format_exc()}")
            raise

    def get_distance(self) -> float:
        try:
            GPIO.output(self.trig_pin, True)
            time.sleep(0.00001)
            GPIO.output(self.trig_pin, False)

            start_time = time.time()
            stop_time = time.time()

            # Wait for echo start
            timeout = 1  # 1 second timeout
            while GPIO.input(self.echo_pin) == 0:
                start_time = time.time()
                if start_time - start_time > timeout:
                    raise TimeoutError("Echo start timeout")

            # Wait for echo end
            while GPIO.input(self.echo_pin) == 1:
                stop_time = time.time()
                if stop_time - start_time > timeout:
                    raise TimeoutError("Echo end timeout")

            elapsed_time = stop_time - start_time
            distance = (elapsed_time * 34300) / 2  # Speed of sound 343 m/s
            return distance
        except TimeoutError as te:
            logging.warning(f"Timeout while reading distance: {te}")
            return None
        except Exception as e:
            logging.error(f"Error reading distance: {e}\n{traceback.format_exc()}")
            return None

    def get_median_distance(self, samples: int = 5) -> float:
        distances = []
        for i in range(samples):
            dist = self.get_distance()
            if dist is not None:
                distances.append(dist)
                logging.debug(f"Sample {i+1}: Distance = {dist} cm")
            else:
                logging.debug(f"Sample {i+1}: Distance reading failed.")
            time.sleep(0.05)  # Small delay between samples
        if distances:
            median_distance = sorted(distances)[len(distances) // 2]
            logging.debug(f"Median Distance: {median_distance} cm")
            return median_distance
        logging.debug("No valid distance readings.")
        return None

    def cleanup(self):
        try:
            GPIO.cleanup()
            logging.info("UltrasonicSensor GPIO cleanup successful.")
        except Exception as e:
            logging.error(f"GPIO cleanup failed: {e}\n{traceback.format_exc()}")
