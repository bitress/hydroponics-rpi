import multiprocessing
import time
from datetime import datetime
import logging
import traceback
from typing import List, Dict, Any
import json
import os
import statistics

from app.engine import db
from app.sensors.light_sensor import LightSensor
from app.sensors.tank_temperature import TemperatureMonitor
from app.sensors.ultrasonic import UltrasonicSensor
from app.sensors.ph_sensor import SensorReader
from app.sensors.relay import RelayController
from app.sensors.dht22 import DHT22Sensor
from app.sensors.camera import CameraCapture
from app.sensors.pump import PumpActivator
from app.actuators.feeder import Feeder

################################################################################
# Logger Configuration
################################################################################

class TableFormatter(logging.Formatter):
    """
    Custom logging formatter to display logs in a structured table format.
    """
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
    """
    Configures the logger with both stream and file handlers.
    """
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
# Database Interaction Functions
################################################################################

def update_cycle_status(db_conn, sensor_id: int, cycle_id: int) -> None:
    """
    Updates the cycle status to inactive after completion.
    """
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


def insert_sensor_data(db_conn, sensor_id: int, value: float) -> None:
    """
    Inserts a new sensor reading into the sensor_data table or saves it to JSON if no connection.
    """
    try:
        insert_query = """
            INSERT INTO sensor_data (sensor_id, value, reading_time) 
            VALUES (%s, %s, %s)
        """
        data = (sensor_id, value, datetime.now())
        db_conn.execute_query(insert_query, data)
        logger.info(f"Data Inserted | Sensor ID: {sensor_id} | Value: {value:.2f}")
        sync_offline_data(db_conn)

    except Exception as e:
        logger.error(f"Failed to insert data for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")
        logger.info("Saving data to JSON queue due to connection issue.")
        save_to_json_queue(sensor_id, value)


def save_to_json_queue(sensor_id: int, value: float) -> None:
    """
    Saves sensor data to a JSON queue file when the database is unavailable.
    """
    queue_file = "sensor_data_queue.json"
    entry = {
        "sensor_id": sensor_id,
        "value": value,
        "reading_time": datetime.now().isoformat()
    }
    
    if os.path.exists(queue_file):
        with open(queue_file, "r") as file:
            queue_data = json.load(file)
    else:
        queue_data = []

    queue_data.append(entry)

    with open(queue_file, "w") as file:
        json.dump(queue_data, file, indent=4)
    logger.info(f"Data queued: {entry}")


def sync_offline_data(db_conn) -> None:
    """
    Syncs queued sensor data from JSON file to the database.
    """
    queue_file = "sensor_data_queue.json"
    
    if not os.path.exists(queue_file):
        logger.info("No offline data to sync.")
        return

    try:
        with open(queue_file, "r") as file:
            queue_data = json.load(file)

        for entry in queue_data:
            insert_query = """
                INSERT INTO sensor_data (sensor_id, value, reading_time) 
                VALUES (%s, %s, %s)
            """
            data = (entry["sensor_id"], entry["value"], entry["reading_time"])
            db_conn.execute_query(insert_query, data)
            logger.info(f"Synced data from JSON | Sensor ID: {entry['sensor_id']} | Value: {entry['value']:.2f}")
        
        os.remove(queue_file)
        logger.info("Offline data synced and queue cleared.")

    except Exception as e:
        logger.error(f"Failed to sync offline data | Error: {e}\n{traceback.format_exc()}")


def fetch_cycles(db_conn, sensor_id: int) -> List[Dict[str, Any]]:
    """
    Fetches all active cycles for a given sensor, falls back to local JSON data if no internet.
    """
    try:
        # Attempt to fetch from the database
        select_query = """
            SELECT cycle_id, interval_seconds, duration_minutes, pause, is_active
            FROM cycles
            WHERE sensor_id = %s AND is_active = '1'
            ORDER BY cycle_id
        """
        cycles = db_conn.fetch_all(select_query, (sensor_id,), dictionary=True)
        if not cycles:
            raise ValueError("No cycles fetched from DB")

        cycles_list = [
            {
                'cycle_id': cycle['cycle_id'],
                'cycle_number': 1,
                'interval_seconds': cycle['interval_seconds'],
                'duration_minutes': cycle['duration_minutes'],
                'pause': cycle['pause'],
                'is_active': cycle['is_active']
            }
            for cycle in cycles
        ]
        logger.info(f"Fetched {len(cycles_list)} active cycles for Sensor ID {sensor_id}: {cycles_list}")
        return cycles_list
    except Exception as e:
        logger.error(f"Failed to fetch cycles for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")

        json_file_path = "sensors.json"
        if os.path.exists(json_file_path):
            try:
                with open(json_file_path, "r") as file:
                    json_data = json.load(file)
                    for table in json_data:
                        if table.get("name") == "sensors":
                            sensors = table.get("data", [])
                            fallback_data = [
                                {
                                    "sensor_name": sensor["sensor_name"],
                                    "sensor_id": int(sensor["id"]),
                                    "config": json.loads(sensor["config"])
                                }
                                for sensor in sensors if int(sensor["id"]) == sensor_id
                            ]
                            logger.info(f"Fetched {len(fallback_data)} sensors from JSON.")
                            return fallback_data
            except Exception as json_error:
                logger.error(f"Error reading JSON file: {json_error}")
        else:
            logger.error("Fallback JSON file not found.")
        return []

################################################################################
# Cycle Worker Function
################################################################################

def cycle_worker(sensor_id: int, sensor, cycle: Dict[str, Any], stop_event: multiprocessing.Event, db_conn, sensor_type: str):
    """
    Handles the execution of a single cycle for a sensor.
    Updates the cycle status to inactive after it completes.
    """
    cycle_number = 1
    cycle_id = cycle['cycle_id']
    interval = cycle['interval_seconds']
    duration = cycle['duration_minutes'] * 60
    pause = cycle['pause']
    map_value = sensor_type

    logger.info(f"Cycle Worker {cycle_number} (Cycle ID: {cycle_id}) started for Sensor ID {sensor_id}. Duration: {duration}s, Interval: {interval}s, Map: {map_value}")

    cycle_start = time.time()
    try:
        while not stop_event.is_set():
            elapsed_time = time.time() - cycle_start
            remaining_time = max(0, duration - elapsed_time)

            if remaining_time <= 0:
                break

            try:
                # Perform sensor-specific actions here
                if isinstance(sensor, UltrasonicSensor):
                    dist = sensor.get_median_distance()
                    if dist is not None:
                        insert_sensor_data(db_conn, sensor_id, dist)
                elif isinstance(sensor, DHT22Sensor):
                    if map_value == 'env_temp':
                        temperature_c = sensor.read_temperature()
                        if temperature_c is not None:
                            insert_sensor_data(db_conn, sensor_id, temperature_c)
                    if map_value == 'humidity':
                        humidity = sensor.read_humidity()
                        if humidity is not None:
                            insert_sensor_data(db_conn, sensor_id, humidity)
                elif isinstance(sensor, CameraCapture):
                    try:
                        sensor.start()
                    except RuntimeError as e:
                        logger.info(e)
                elif isinstance(sensor, SensorReader):
                    if map_value == 'ph':
                        ph = sensor.read_ph()
                        if ph is not None:
                            insert_sensor_data(db_conn, sensor_id, ph)
                            
                elif isinstance(sensor, TemperatureMonitor):
                    sensor.monitor_temperatures()
                    if map_value == 'tank1':
                        tank_1 = sensor.get_tank_1_temp()
                        logger.info(tank_1)
                        if tank_1 is not None:
                            insert_sensor_data(db_conn, sensor_id, tank_1)
                    elif map_value == 'tank2':
                        tank_2 = sensor.get_tank_2_temp()
                        logger.info(tank_2)

                        if tank_2 is not None:
                            insert_sensor_data(db_conn, sensor_id, tank_2)

                elif isinstance(sensor, LightSensor):
                    light_level = sensor.read_light()
                    if light_level is not None:
                        insert_sensor_data(db_conn, sensor_id, light_level)
                
                elif isinstance(sensor, PumpActivator):
                    if map_value == 'pump_2':
                        sensor.run_pump(duration=interval) 
                    elif map_value == 'pump_tank':
                        sensor.run_pump(duration=interval)         

            except Exception as e:
                logger.error(f"Error in Cycle {cycle_number} | Sensor ID {sensor_id}: {e}\n{traceback.format_exc()}")

            time.sleep(interval)

        if pause > 0 and not stop_event.is_set():
            logger.info(f"Cycle Worker {cycle_number} (Cycle ID: {cycle_id}) pausing for {pause} seconds.")
            time.sleep(pause)

    finally:
        # Update the cycle status to inactive after completion
        logger.info(f"Cycle Worker {cycle_number} (Cycle ID: {cycle_id}) for Sensor ID {sensor_id} has completed.")
        # update_cycle_status(db_conn, sensor_id, cycle_id)

################################################################################
# Sensor Runner Function
################################################################################

def run_sensor(sensor_id: int, stop_event: multiprocessing.Event, sensor_type: str):
    """
    Initializes and runs sensor processes, managing cycles based on the is_active flag.
    Starts cycles only if they are active, otherwise waits for cycles to be activated.
    """
    sensor = None
    db_conn = None
    cycle_processes = {}

    try:
        db_conn = db
        if not db_conn:
            logger.error(f"Database connection unavailable for Sensor ID {sensor_id}.")
            return

        if sensor_type == 'ultrasonic':
            sensor = UltrasonicSensor(trig_pin=18, echo_pin=15)
        elif sensor_type in ['ph']:
            sensor = SensorReader()
        elif sensor_type in ['tank1', 'tank2']:
            sensor = TemperatureMonitor()
        elif sensor_type == 'light':
            sensor = LightSensor()
            sensor.power_on()
        elif sensor_type in ['env_temp', 'humidity']:
            sensor = DHT22Sensor()
        elif sensor_type == 'camera':
            sensor = CameraCapture()
        elif sensor_type  == 'pump_tank':
            sensor = PumpActivator(gpio_pin=16)
        elif sensor_type ==  'pump_2':
            sensor = PumpActivator(gpio_pin=20)

        logger.info(f"Sensor ID {sensor_id} of type '{sensor_type}' initialized.")

        while not stop_event.is_set():
            activate_all_cycles(db_conn, sensor_id)

            # Fetch all active cycles for this sensor
            cycles = fetch_cycles(db_conn, sensor_id)
            active_cycle_ids = {cycle['cycle_id'] for cycle in cycles}

            # Start cycles that are active and not already running
            for cycle in cycles:
                cycle_id = cycle['cycle_id']
                if cycle_id not in cycle_processes:
                    # Start a new cycle process
                    process = multiprocessing.Process(
                        target=cycle_worker,
                        args=(sensor_id, sensor, cycle, stop_event, db_conn, sensor_type),
                        name=f"Sensor-{sensor_id}-Cycle-{cycle_id}-Process"
                        # daemon=False by default
                    )
                    process.start()
                    cycle_processes[cycle_id] = process
                    logger.info(f"Started Cycle ID {cycle_id} for Sensor ID {sensor_id}.")

            # Terminate cycles that are no longer active
            for cycle_id in list(cycle_processes.keys()):
                if cycle_id not in active_cycle_ids:
                    process = cycle_processes.pop(cycle_id)
                    if process.is_alive():
                        logger.info(f"Terminating Cycle ID {cycle_id} for Sensor ID {sensor_id} as it is no longer active.")
                        process.terminate()
                        process.join(timeout=5)
                        if process.is_alive():
                            logger.warning(f"Cycle ID {cycle_id} for Sensor ID {sensor_id} did not terminate gracefully.")

            if not active_cycle_ids:
                logger.info(f"No active cycles found for Sensor ID {sensor_id}. Waiting for cycles to be activated...")
            else:
                logger.info(f"Monitoring active cycles for Sensor ID {sensor_id}.")

            time.sleep(10)  # Wait before the next cycle check

    except Exception as e:
        logger.error(f"Error in {sensor_type}_sensor for Sensor ID {sensor_id}: {e}\n{traceback.format_exc()}")
    finally:
        # Terminate all running cycle processes
        for cycle_id, process in cycle_processes.items():
            if process.is_alive():
                logger.info(f"Terminating Cycle ID {cycle_id} for Sensor ID {sensor_id} during shutdown.")
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    logger.warning(f"Cycle ID {cycle_id} for Sensor ID {sensor_id} did not terminate gracefully.")
        cycle_processes.clear()

        # Power down sensors if necessary
        if sensor_type == 'light' and sensor:
            sensor.power_down()
            logger.info(f"LightSensor for Sensor ID {sensor_id} powered down.")

        # Close database connection
        if db_conn:
            db_conn.close()
            logger.info(f"Database connection closed for Sensor ID {sensor_id}.")

def activate_all_cycles(db_conn, sensor_id: int) -> None:
    """
    Activates all cycles for a given sensor by setting is_active = 1.
    """
    try:
        update_query = """
            UPDATE cycles
            SET is_active = '1'
            WHERE sensor_id = %s AND is_active = '0'
        """
        db_conn.execute_query(update_query, (sensor_id,))
        logger.info(f"All cycles for Sensor ID {sensor_id} have been activated.")
    except Exception as e:
        logger.error(f"Failed to activate all cycles for Sensor ID {sensor_id} | Error: {e}\n{traceback.format_exc()}")

################################################################################
# Sensor Fetching Function
################################################################################

def fetch_sensors_from_db(db_conn) -> Dict[int, str]:
    """
    Fetches all active sensors from the database and maps their IDs to their types.
    """
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
                else:
                    logger.warning(f"Sensor ID {sensor['id']} has no 'map' configuration.")
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON decode error for Sensor ID {sensor['id']}: {json_err}")
        logger.info(f"Fetched {len(sensor_map)} active sensors from the database.")
        return sensor_map
    except Exception as e:
        logger.error(f"Failed to fetch sensors from database | Error: {e}\n{traceback.format_exc()}")
        return {}


################################################################################
# Main Function
################################################################################

def main() -> None:
    """
    Main entry point of the application. Initializes and manages sensor processes.
    """
    stop_event = multiprocessing.Event()
    processes = {}

    try:
        main_db_conn = db
        if not main_db_conn:
            logger.critical("Main database connection is unavailable. Exiting application.")
            return

        sensor_processes_info = fetch_sensors_from_db(main_db_conn)

        for sensor_id, sensor_type in sensor_processes_info.items():
            process = multiprocessing.Process(
                target=run_sensor,
                args=(sensor_id, stop_event, sensor_type),
                name=f"Sensor-{sensor_id}-Process"
                # Removed daemon=True to allow child processes
            )
            process.start()
            processes[sensor_id] = process
            logger.info(f"Started process for Sensor ID {sensor_id} with Sensor Type '{sensor_type}'.")
            

        logger.info("All sensor processes have been started. Entering main loop.")

        while True:
            controller = RelayController()
            controller.run()
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Initiating graceful shutdown...")
        stop_event.set()
    except Exception as e:
        logger.error(f"Error in main program: {e}\n{traceback.format_exc()}")
        stop_event.set()
    finally:
        logger.info("Shutting down all sensor processes...")
        for sensor_id, process in processes.items():
            process.join(timeout=5)
            if process.is_alive():
                logger.warning(f"Process for Sensor ID {sensor_id} is still alive. Terminating...")
                process.terminate()
            logger.info(f"Process for Sensor ID {sensor_id} has been terminated.")
        logger.info("All sensor processes have been shut down. Exiting application.")

################################################################################
# Entry Point
################################################################################

if __name__ == "__main__":
    main()