import RPi.GPIO as GPIO
import time
import logging
from app.engine import db

# Constants for GPIO Modes and Relay States
GPIO_MODE = GPIO.BCM
GPIO_OFF = GPIO.LOW
GPIO_ON = GPIO.HIGH
RELAY_STATUS_ON = 1
RELAY_STATUS_OFF = 0

class RelayController:
    def __init__(self):
        self.RELAY_PINS = {}
        self.RELAY_NAMES = {}
        self.RELAY_CONTROL_MODES = {}
        self.load_relay_config()

    def load_relay_config(self):
        """Load relay configuration from the database."""
        query = """
        SELECT r.id, d.device_name, d.gpio, r.relay_status, r.control_mode
        FROM relays r
        INNER JOIN devices d ON d.device_id = r.device_id
        ORDER BY r.id;
        """
        try:
            relays = db.fetch_all(query)
            if relays:
                for relay in relays:
                    relay_id = relay[0]
                    self.RELAY_NAMES[relay_id] = relay[1]
                    self.RELAY_PINS[relay_id] = relay[2]
                    self.RELAY_CONTROL_MODES[relay_id] = relay[4]
                logging.info("Relay configuration loaded from database")
            else:
                logging.warning("No relay configuration found in the database")
        except Exception as e:
            logging.error(f"Error loading relay configuration: {e}")

    def setup_gpio(self):
        """Initialize GPIO pins for relays."""
        GPIO.setmode(GPIO_MODE)
        for relay_id, pin in self.RELAY_PINS.items():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO_OFF)
            logging.info(f"Initialized {self.RELAY_NAMES[relay_id]} on GPIO{pin}")

    def control_relay(self, relay_id, status):
        """Control a single relay."""
        pin = self.RELAY_PINS.get(relay_id)
        if pin is not None:
            GPIO.output(pin, GPIO_ON if status else GPIO_OFF)
            logging.info(f"Relay {relay_id} ({self.RELAY_NAMES[relay_id]}) set to {'ON' if status else 'OFF'}")
        else:
            logging.error(f"GPIO pin for relay {relay_id} not found")

    def fetch_and_update_relays(self):
        """Fetch relay statuses from the database and update GPIO pins."""
        query = """
               SELECT r.id, d.device_name, d.gpio, r.relay_status, r.control_mode
        FROM relays r
        INNER JOIN devices d ON d.device_id = r.device_id
        ORDER BY r.id;

        """
        
        try:
            relays = db.fetch_all(query)
            if not relays:
                logging.warning("No relays found in database")
                return

            logging.info("\nCurrent Relay States:")
            logging.info("-" * 50)
            logging.info("ID | Name   | Status | Mode     | GPIO")
            logging.info("-" * 50)

            for relay in relays:
                relay_id, relay_name, gpio, status, control_mode = relay

                logging.info(f"{relay_id:2d} | {relay_name:6s} | {('ON' if status else 'OFF'):6s} | {control_mode:8s} | GPIO{gpio}")

                # Update relay status only for manual control mode
                if control_mode.lower() == 'manual':
                    self.control_relay(relay_id, bool(status))

            logging.info("-" * 50)

        except Exception as e:
            logging.error(f"Database error: {e}")

    def run(self):
        """Main loop to control relays."""
        self.setup_gpio() 
        
        try:
            while True:
                self.fetch_and_update_relays()
                time.sleep(1)
        except KeyboardInterrupt:
            GPIO.cleanup()
            logging.info("\nProgram terminated by user")
        except Exception as e:
            GPIO.cleanup()
            logging.error(f"Unexpected error: {e}")
