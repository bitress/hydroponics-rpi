import RPi.GPIO as GPIO
import time
from app.engine import db

class RelayController:
    def __init__(self):
        self.RELAY_PINS = {}
        self.RELAY_NAMES = {}
        self.load_relay_config()

    def load_relay_config(self):
        """Load relay configuration from database"""
        query = "SELECT id, relay_name, gpio FROM relays ORDER BY id"
        try:
            relays = db.fetch_all(query)
            if relays:
                for relay in relays:
                    relay_id = relay[0]
                    self.RELAY_NAMES[relay_id] = relay[1]
                    self.RELAY_PINS[relay_id] = relay[2]
                print("Relay configuration loaded from database")
            else:
                print("No relay configuration found in database")
        except Exception as e:
            print(f"Error loading relay configuration: {e}")

    def setup_gpio(self):
        """Initialize GPIO pins."""
        GPIO.setmode(GPIO.BCM)
        for relay_id, pin in self.RELAY_PINS.items():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
            print(f"Initialized {self.RELAY_NAMES[relay_id]} on GPIO{pin}")

    def control_relay(self, relay_id, status):
        """Control a single relay."""
        pin = self.RELAY_PINS.get(relay_id)
        if pin is not None:
            GPIO.output(pin, GPIO.HIGH if status else GPIO.LOW)
            print(f"Relay {relay_id} ({self.RELAY_NAMES[relay_id]}) set to {'ON' if status else 'OFF'}")

    def fetch_and_update_relays(self):
        """Fetch relay statuses from database and update GPIO pins."""
        query = """
            SELECT id, relay_name, relay_status, control_mode, gpio 
            FROM relays 
            ORDER BY id
        """
        
        try:
            relays = db.fetch_all(query)
            
            if not relays:
                print("No relays found in database")
                return

            print("\nCurrent Relay States:")
            print("-" * 50)
            print("ID | Name   | Status | Mode     | GPIO")
            print("-" * 50)

            for relay in relays:
                relay_id = relay[0]
                relay_name = relay[1]
                status = relay[2]
                control_mode = relay[3]
                gpio = relay[4]

                print(f"{relay_id:2d} | {relay_name:6s} | {('ON' if status else 'OFF'):6s} | {control_mode:8s} | GPIO{gpio}")
                
                if control_mode.lower() == 'manual':
                    self.control_relay(relay_id, bool(status))
            
            print("-" * 50)

        except Exception as e:
            print(f"Database error: {e}")

    def run(self):
        """Main loop to control relays."""
        self.setup_gpio() 
        
        try:
            while True:
                self.fetch_and_update_relays()
                time.sleep(1)
        except KeyboardInterrupt:
            GPIO.cleanup()
            print("\nProgram terminated by user")

def main():
    controller = RelayController()
    controller.run()

if __name__ == '__main__':
    main()
