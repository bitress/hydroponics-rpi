
import RPi.GPIO as GPIO
import time
import logging
from app.engine import db

class PumpActivator:
    def __init__(self, gpio_pin):
        """Initialize the pump GPIO pin."""
        self.gpio_pin = gpio_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.OUT)
        GPIO.output(self.gpio_pin, GPIO.HIGH)
        logging.info(f"Pump initialized on GPIO{self.gpio_pin}")

    def run_pump(self, duration=5):
        """Activate the pump for a specified duration (default 5 seconds)."""
        logging.info("Activating pump")
        GPIO.output(self.gpio_pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(self.gpio_pin, GPIO.LOW)
        logging.info("Pump deactivated")
