# app/sensors/tank_temperature.py

import os
import glob
import time
import logging
import threading
from app.engine import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SensorLogger")

class TemperatureSensor:
    def __init__(self, sensor_id, tank_name):
        self.sensor_id = sensor_id
        self.tank_name = tank_name
        self.device_folder = f"/sys/bus/w1/devices/{sensor_id}"

    def read_temp_raw(self):
        """Read the raw data from the sensor"""
        device_file = os.path.join(self.device_folder, 'w1_slave')
        try:
            with open(device_file, 'r') as f:
                lines = f.readlines()
            return lines
        except FileNotFoundError:
            logger.error(f"Device file {device_file} not found.")
            return []

    def read_temp(self):
        """Parse the raw data and return the temperature in Celsius"""
        lines = self.read_temp_raw()
        if not lines:
            return None

        while lines[0].strip()[-3:] != 'YES':  
            time.sleep(0.2)
            lines = self.read_temp_raw()
            if not lines:
                return None
        
        equals_pos = lines[1].find('t=')  
        if equals_pos != -1:
            temp_string = lines[1][equals_pos + 2:]  
            try:
                temp_c = float(temp_string) / 1000.0  
                return temp_c
            except ValueError:
                logger.error(f"Invalid temperature value: {temp_string}")
                return None

    def get_tank_label(self):
        """Returns the tank name"""
        return self.tank_name


class TemperatureMonitor:
    def __init__(self):
        self.sensors = self.initialize_sensors()
        self.tank_1_temp = None
        self.tank_2_temp = None

    def get_tank_1_temp(self):
        """
        Returns the latest temperature of Tank 1.
        """
        return self.tank_1_temp

    def get_tank_2_temp(self):
        """
        Returns the latest temperature of Tank 2.
        """
        return self.tank_2_temp

    def initialize_sensors(self):
        """Initialize all sensors and map them to their respective tank labels"""
        sensor_to_tank = {
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
        
        if not sensors:
            logger.warning("No temperature sensors found.")
        
        return sensors

    def monitor_temperatures(self, stop_event: threading.Event):
        """Continuously monitor and store temperatures for each sensor"""
        logger.info("Starting temperature monitoring.")
        while not stop_event.is_set():
            for sensor in self.sensors:
                temp = sensor.read_temp()

                if sensor.get_tank_label() == "Tank 1":
                    self.tank_1_temp = temp
                elif sensor.get_tank_label() == "Tank 2":
                    self.tank_2_temp = temp
                else:
                    logger.info(f"Temperature from {sensor.get_tank_label()}: {temp} °C")
                    continue 
            time.sleep(1)  # Adjust the sleep interval as needed

    def stop_monitoring(self):
        """Stop the temperature monitoring loop"""
        self._stop_event.set()
