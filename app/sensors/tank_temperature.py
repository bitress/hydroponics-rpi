import os
import glob
import time
import logging
import threading
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SensorLogger")


class TemperatureSensor:
    def __init__(self, sensor_id: str, tank_name: str):
        self.sensor_id = sensor_id
        self.tank_name = tank_name
        self.device_folder = f"/sys/bus/w1/devices/{sensor_id}"

    def read_temp_raw(self) -> Optional[List[str]]:
        """Read the raw data from the sensor."""
        device_file = os.path.join(self.device_folder, 'w1_slave')
        try:
            with open(device_file, 'r') as f:
                lines = f.readlines()
            return lines
        except FileNotFoundError:
            logger.error(f"Device file {device_file} not found for sensor {self.sensor_id}.")
            return None
        except Exception as e:
            logger.error(f"Error reading from sensor {self.sensor_id}: {e}")
            return None

    def read_temp(self) -> Optional[float]:
        """Parse the raw data and return the temperature in Celsius."""
        lines = self.read_temp_raw()
        if not lines:
            return None

        # Wait for a valid reading
        while lines[0].strip()[-3:] != 'YES':
            time.sleep(0.2)
            lines = self.read_temp_raw()
            if not lines:
                return None

        # Extract temperature value
        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            temp_string = lines[1][equals_pos + 2:]
            try:
                temp_c = float(temp_string) / 1000.0
                if -50 <= temp_c <= 150:  # Validate temperature range
                    return temp_c
                else:
                    logger.warning(f"Invalid temperature reading from sensor {self.sensor_id}: {temp_c} °C")
                    return None
            except ValueError:
                logger.error(f"Invalid temperature value from sensor {self.sensor_id}: {temp_string}")
                return None

    def get_tank_label(self) -> str:
        """Return the tank name associated with this sensor."""
        return self.tank_name


class TemperatureMonitor:
    def __init__(self):
        self.sensors = self.initialize_sensors()
        self.tank_1_temp: Optional[float] = None
        self.tank_2_temp: Optional[float] = None
        self._lock = threading.Lock()  # Thread-safe access to temperature variables
        self._stop_event = threading.Event()

    def initialize_sensors(self) -> List[TemperatureSensor]:
        """Initialize all sensors and map them to their respective tank labels."""
        # Configuration for sensor-to-tank mapping
        sensor_to_tank: Dict[str, str] = {
            '28-000000856211': 'Tank 1',
            '28-00000085aff4': 'Tank 2',
        }

        sensors = []
        base_dir = '/sys/bus/w1/devices/'
        device_folders = glob.glob(os.path.join(base_dir, '28*'))

        for device_folder in device_folders:
            sensor_id = os.path.basename(device_folder)
            tank_label = sensor_to_tank.get(sensor_id, f"Unknown Tank ({sensor_id})")
            sensor = TemperatureSensor(sensor_id, tank_label)
            sensors.append(sensor)
            logger.info(f"Initialized sensor {sensor_id} for {tank_label}.")

        if not sensors:
            logger.warning("No temperature sensors found.")
        return sensors

    def monitor_temperatures(self):
        """Continuously monitor and store temperatures for each sensor."""
        logger.info("Starting temperature monitoring.")
        while not self._stop_event.is_set():
            for sensor in self.sensors:
                temp = sensor.read_temp()
                if temp is not None:
                    with self._lock:
                        if sensor.get_tank_label() == "Tank 1":
                            self.tank_1_temp = temp
                        elif sensor.get_tank_label() == "Tank 2":
                            self.tank_2_temp = temp
                        else:
                            logger.info(f"Temperature from {sensor.get_tank_label()}: {temp} °C")
            time.sleep(1)  # Adjust the sleep interval as needed

    def get_tank_1_temp(self) -> Optional[float]:
        """Return the latest temperature of Tank 1."""
        with self._lock:
            return self.tank_1_temp

    def get_tank_2_temp(self) -> Optional[float]:
        """Return the latest temperature of Tank 2."""
        with self._lock:
            return self.tank_2_temp

    def stop_monitoring(self):
        """Stop the temperature monitoring loop."""
        self._stop_event.set()
        logger.info("Temperature monitoring stopped.")
