import time
import schedule
from datetime import datetime
import traceback

from app.engine import db
from app.sensors.light_sensor import LightSensor
from app.sensors.tank_temperature import TemperatureMonitor
from app.sensors.ultrasonic import UltrasonicSensor
from app.sensors.ph_sensor import SensorReader
from app.sensors.relay import RelayController
from app.sensors.dht22 import DHT22Sensor
from app.sensors.camera import CameraCapture
from app.actuators.feeder import Feeder

ultrasonic_sensor = UltrasonicSensor(trig_pin=18, echo_pin=15)
dht22_sensor = DHT22Sensor()
camera_sensor = CameraCapture()
ph_sensor = SensorReader()
temperature_monitor = TemperatureMonitor()
light_sensor = LightSensor()

def gather_sensor_data():
    try:
        # Ultrasonic Sensor
        dist = ultrasonic_sensor.get_median_distance()
        if dist is not None:
            insert_sensor_data(db, sensor_id=5, value=dist)  

        # DHT22 Sensor
        temperature_c = dht22_sensor.read_temperature()
        if temperature_c is not None:
            insert_sensor_data(db, sensor_id=8, value=temperature_c)  

        # Camera Capture
        camera_sensor.start()

        # pH Sensor
        ph = ph_sensor.read_ph()
        if ph is not None:
            insert_sensor_data(db, sensor_id=2, value=ph)  

        # Temperature Monitor
        tank_1 = temperature_monitor.get_tank_1_temp()
        if tank_1 is not None:
            insert_sensor_data(db, sensor_id=3, value=tank_1)  
        tank_2 = temperature_monitor.get_tank_2_temp()
        if tank_2 is not None:
            insert_sensor_data(db, sensor_id=4, value=tank_2)  

        # Light Sensor
        light_level = light_sensor.read_light()
        if light_level is not None:
            insert_sensor_data(db, sensor_id=6, value=light_level)  

    except Exception as e:
        print(f"Error gathering sensor data: {e}\n{traceback.format_exc()}")

def insert_sensor_data(db_conn, sensor_id: int, value: float) -> None:
    """
    Inserts a new sensor reading into the sensor_data table.
    """
    try:
        insert_query = """
            INSERT INTO sensor_data (sensor_id, value, reading_time) 
            VALUES (%s, %s, %s)
        """
        data = (sensor_id, value, datetime.now())
        db_conn.execute_query(insert_query, data)
        print(f"Data Inserted | Sensor ID: {sensor_id} | Value: {value:.2f}")
    except Exception as e:
        print(f"Failed to insert data for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")

schedule.every().hour.do(gather_sensor_data)

while True:
    schedule.run_pending()
    time.sleep(1)