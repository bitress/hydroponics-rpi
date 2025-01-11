import multiprocessing
import time
from datetime import datetime
import logging
import traceback
from typing import List, Dict, Any
import json
import threading
import statistics

from app.engine import db
from app.sensors.light_sensor import LightSensor
from app.sensors.tank_temperature import TemperatureMonitor
from app.sensors.ultrasonic import UltrasonicSensor
from app.sensors.ph_sensor import SensorReader


################################################################################
# NEW: Simple global dictionary mapping sensor 'map' types to default thresholds
################################################################################

SENSOR_THRESHOLDS = {
    'ultrasonic': 100.0,
    'ph': 7.0,
    'ph_temp': 25.0,
    'tank1': 25.0,
    'tank2': 25.0,
    'light': 500.0
}


################################################################################
# NEW: Helper functions to fetch multiple readings and compute median
################################################################################

def fetch_last_n_readings(connection, sensor_id: int, n: int = 5) -> List[float]:
    try:
        query = """
            SELECT value
            FROM sensor_data
            WHERE sensor_id = %s
            ORDER BY reading_time DESC
            LIMIT %s
        """
        results = connection.fetch_all(query, (sensor_id, n), dictionary=True)
        values = [row['value'] for row in results if 'value' in row]
        return values
    except Exception as e:
        logger.error(f"Failed to fetch the last {n} readings for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")
        return []

def fetch_sensor_median(connection, sensor_id: int, n: int = 5) -> float:
    values = fetch_last_n_readings(connection, sensor_id, n=n)
    if not values:
        return None
    try:
        return statistics.median(values)
    except Exception as e:
        logger.error(f"Error computing median for Sensor ID {sensor_id} | Error: {e}\n{traceback.format_exc()}")
        return None


################################################################################
# Existing Logger Configuration
################################################################################

class TableFormatter(logging.Formatter):
    def __init__(self):
        self.timestamp_width = 20
        self.level_width = 10
        self.process_width = 25
        self.message_width = 150
        super().__init__()

    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        level = record.levelname
        process = record.processName
        message = record.getMessage()

        if len(message) > self.message_width - 3:
            message = message[:self.message_width - 6] + '...'

        formatted = f"{timestamp:<{self.timestamp_width}} | {level:<{self.level_width}} | {process:<{self.process_width}} | {message:<{self.message_width}}"
        return formatted

def configure_logging() -> logging.Logger:
    logger = logging.getLogger("SensorLogger")
    logger.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(TableFormatter())
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler('sensor_logs.log')
    file_handler.setFormatter(TableFormatter())
    logger.addHandler(file_handler)

    return logger

logger = configure_logging()


################################################################################
# Existing Functions
################################################################################

def insert_sensor_data(db_conn, sensor_id: int, value: float) -> None:
    try:
        insert_query = """
            INSERT INTO sensor_data (sensor_id, value, reading_time) 
            VALUES (%s, %s, %s)
        """
        data = (sensor_id, value, datetime.now())
        db_conn.execute_query(insert_query, data)
        logger.info(f"Data Inserted | Sensor ID: {sensor_id} | Value: {value:.2f}")
    except Exception as e:
        logger.error(f"Failed to insert data for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")

def update_cycle_status(db_conn, sensor_id: int, cycle_id: int) -> None:
    try:
        update_query = """
            UPDATE cycles
            SET is_active = '0'
            WHERE sensor_id = %s AND cycle_id = %s
        """
        db_conn.execute_query(update_query, (sensor_id, cycle_id))
        logger.info(f"Updated cycle ID {cycle_id} to inactive for Sensor ID {sensor_id}.")
    except Exception as e:
        logger.error(f"Failed to update cycle status for Sensor ID: {sensor_id}, Cycle ID: {cycle_id} | Error: {e}\n{traceback.format_exc()}")

def fetch_latest_reading(connection, sensor_id: int):
    query = """
        SELECT value, reading_time
        FROM sensor_data
        WHERE sensor_id = %s
        ORDER BY reading_time DESC
        LIMIT 1
    """
    results = connection.fetch_all(query, (sensor_id,), dictionary=True)
    if results:
        return results[0]
    return None

def fetch_cycles(db_conn, sensor_id: int) -> List[Dict[str, Any]]:
    try:
        select_query = """
            SELECT cycle_id, cycle_number, interval_seconds, duration_minutes, pause
            FROM cycles
            WHERE sensor_id = %s AND is_active = '1'
            ORDER BY cycle_id
        """
        cycles = db_conn.fetch_all(select_query, (sensor_id,), dictionary=True)
        cycles_list = [
            {
                'cycle_id': cycle['cycle_id'],
                'cycle_number': cycle['cycle_number'],
                'interval_seconds': cycle['interval_seconds'],
                'duration_minutes': cycle['duration_minutes'],
                'pause': cycle['pause']
            }
            for cycle in cycles
        ]
        logger.info(f"Fetched {len(cycles_list)} cycles for Sensor ID {sensor_id}: {cycles_list}")
        return cycles_list
    except Exception as e:
        logger.error(f"Failed to fetch cycles for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")
        return []

def cycle_worker(sensor_id: int, sensor, cycle: Dict[str, Any], stop_event: multiprocessing.Event, db_conn, sensor_type: str):
    cycle_number = cycle['cycle_number']
    cycle_id = cycle['cycle_id']
    interval = cycle['interval_seconds']
    duration = cycle['duration_minutes'] * 60
    pause = cycle['pause']
    map_value = sensor_type

    logger.info(f"Cycle Worker {cycle_number} (Cycle ID: {cycle_id}) started for Sensor ID {sensor_id}. Duration: {duration}s, Interval: {interval}s, Map: {map_value}")

    cycle_start = time.time()
    while not stop_event.is_set():
        elapsed_time = time.time() - cycle_start
        remaining_time = max(0, duration - elapsed_time)

        if remaining_time <= 0:
            break

        try:
            if isinstance(sensor, UltrasonicSensor):
                dist = sensor.get_median_distance()
                if dist is not None:
                    insert_sensor_data(db_conn, sensor_id, dist)

            elif isinstance(sensor, SensorReader):
                if map_value == 'ph':
                    ph = sensor.read_ph()
                    if ph is not None:
                        insert_sensor_data(db_conn, sensor_id, ph)
                elif map_value == 'ph_temp':
                    temperature = sensor.read_temperature()
                    if temperature is not None:
                        insert_sensor_data(db_conn, sensor_id, temperature)

            elif isinstance(sensor, TemperatureMonitor):
                if map_value == 'tank1':
                    tank_1 = sensor.get_tank_1_temp()
                    if tank_1 is not None:
                        insert_sensor_data(db_conn, sensor_id, tank_1)
                elif map_value == 'tank2':
                    tank_2 = sensor.get_tank_2_temp()
                    if tank_2 is not None:
                        insert_sensor_data(db_conn, sensor_id, tank_2)

            elif isinstance(sensor, LightSensor):
                light_level = sensor.read_light()
                if light_level is not None:
                    insert_sensor_data(db_conn, sensor_id, light_level)

        except Exception as e:
            logger.error(f"Error in Cycle {cycle_number} | Sensor ID {sensor_id}: {e}\n{traceback.format_exc()}")

        time.sleep(interval)

    if pause > 0 and not stop_event.is_set():
        time.sleep(pause)

def run_sensor(sensor_id: int, stop_event: multiprocessing.Event, sensor_type: str) -> None:
    sensor = None
    db_conn = None

    try:
        db_conn = db
        if not db_conn:
            return

        if sensor_type == 'ultrasonic':
            sensor = UltrasonicSensor(trig_pin=18, echo_pin=15)
        elif sensor_type in ['ph', 'ph_temp']:
            sensor = SensorReader()
        elif sensor_type in ['tank1', 'tank2']:
            sensor = TemperatureMonitor()
        elif sensor_type == 'light':
            sensor = LightSensor()
            sensor.power_on()

        while not stop_event.is_set():
            cycles = fetch_cycles(db_conn, sensor_id)
            if not cycles:
                time.sleep(10)
                continue

            for cycle in cycles:
                if stop_event.is_set():
                    break
                cycle_worker(sensor_id, sensor, cycle, stop_event, db_conn, sensor_type)
                update_cycle_status(db_conn, sensor_id, cycle['cycle_id'])

    except Exception as e:
        logger.error(f"Error in {sensor_type}_sensor for Sensor ID {sensor_id}: {e}\n{traceback.format_exc()}")
    finally:
        if sensor_type == 'light' and sensor:
            sensor.power_down()
        if db_conn:
            db_conn.close()

def fetch_sensors_from_db(db_conn) -> Dict[int, str]:
    try:
        select_query = """
            SELECT id, config
            FROM sensors
            WHERE is_active = 1
        """
        sensors = db_conn.fetch_all(select_query, (), dictionary=True)
        sensor_map = {}
        for sensor in sensors:
            try:
                config = json.loads(sensor['config'])
                sensor_type = config.get('map')
                if sensor_type:
                    sensor_map[sensor['id']] = sensor_type
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON decode error for Sensor ID {sensor['id']}: {json_err}")
        return sensor_map
    except Exception as e:
        logger.error(f"Failed to fetch sensors from database | Error: {e}\n{traceback.format_exc()}")
        return {}


################################################################################
# Main Function
################################################################################

def main() -> None:
    stop_event = multiprocessing.Event()
    processes = {}

    try:
        main_db_conn = db
        if not main_db_conn:
            return

        sensor_processes_info = fetch_sensors_from_db(main_db_conn)

        for sensor_id, sensor_type in sensor_processes_info.items():
            process = multiprocessing.Process(
                target=run_sensor,
                args=(sensor_id, stop_event, sensor_type),
                name=f"Sensor-{sensor_id}-Process",
                daemon=True
            )
            process.start()
            processes[sensor_id] = process

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        stop_event.set()
    except Exception as e:
        logger.error(f"Error in main program: {e}\n{traceback.format_exc()}")
        stop_event.set()
    finally:
        for process in processes.values():
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()

if __name__ == "__main__":
    main()
