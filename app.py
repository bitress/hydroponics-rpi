import multiprocessing
import time
from datetime import datetime
import logging
import traceback
from typing import List, Dict, Any
import json
import statistics

from app.engine import db
from app.sensors.light_sensor import LightSensor
from app.sensors.tank_temperature import TemperatureMonitor
from app.sensors.ultrasonic import UltrasonicSensor
from app.sensors.ph_sensor import SensorReader

################################################################################
# Global Configuration and Constants
################################################################################

# Simple global dictionary mapping sensor 'map' types to default thresholds
SENSOR_THRESHOLDS = {
    'ultrasonic': 100.0,
    'ph': 7.0,
    'ph_temp': 25.0,
    'tank1': 25.0,
    'tank2': 25.0,
    'light': 500.0
}

################################################################################
# Helper Functions
################################################################################

def fetch_last_n_readings(connection, sensor_id: int, n: int = 5) -> List[float]:
    """
    Fetches the last `n` readings for a given sensor.
    """
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
    """
    Computes the median of the last `n` readings for a given sensor.
    """
    values = fetch_last_n_readings(connection, sensor_id, n=n)
    if not values:
        return None
    try:
        return statistics.median(values)
    except Exception as e:
        logger.error(f"Error computing median for Sensor ID {sensor_id} | Error: {e}\n{traceback.format_exc()}")
        return None

################################################################################
# Schedule and Threshold Functions
################################################################################

def is_active_schedule_for_sensor(db_conn, sensor_id: int) -> bool:
    """
    Checks if there is an active schedule for the given sensor.
    """
    try:
        query = """
            SELECT COUNT(*) as active_count
            FROM schedules
            WHERE is_active = 1
              AND target_type = 'sensor'
              AND target_id = %s
              AND (
                  (recurrence = 'none' AND NOW() BETWEEN start_time AND end_time)
                  OR
                  (recurrence = 'daily' AND 
                      (TIME(NOW()) BETWEEN TIME(start_time) AND TIME(end_time)))
                  OR
                  (recurrence = 'weekly' AND 
                      DAYOFWEEK(NOW()) = DAYOFWEEK(start_time) AND 
                      (TIME(NOW()) BETWEEN TIME(start_time) AND TIME(end_time)))
                  OR
                  (recurrence = 'monthly' AND 
                      DAY(NOW()) = DAY(start_time) AND 
                      (TIME(NOW()) BETWEEN TIME(start_time) AND TIME(end_time)))
              )
        """
        result = db_conn.fetch_all(query, (sensor_id,), dictionary=True)
        active_count = result[0]['active_count'] if result else 0
        is_active = active_count > 0
        logger.info(f"Sensor ID {sensor_id} Active Schedule Count: {active_count}")
        return is_active
    except Exception as e:
        logger.error(f"Failed to check active schedules for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")
        return False

def check_sensor_thresholds(db_conn, sensor_id: int, current_value: float) -> List[Dict[str, Any]]:
    """
    Checks if the current sensor value breaches any defined thresholds.
    Returns a list of breached thresholds.
    """
    try:
        query = """
            SELECT *
            FROM sensor_thresholds
            WHERE sensor_id = %s
              AND (
                  (threshold_type = 'min' AND %s < value)
                  OR
                  (threshold_type = 'max' AND %s > value)
              )
        """
        thresholds = db_conn.fetch_all(query, (sensor_id, current_value, current_value), dictionary=True)
        if thresholds:
            logger.info(f"Thresholds breached for Sensor ID {sensor_id}: {thresholds}")
        return thresholds
    except Exception as e:
        logger.error(f"Failed to check thresholds for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")
        return []

def activate_sensor_device_mapping(db_conn, sensor_id: int, thresholds: List[Dict[str, Any]]) -> None:
    """
    Activates or deactivates sensor-device mappings based on breached thresholds.
    Handles actions like 'alert', 'activate', and 'deactivate'.
    """
    try:
        for threshold in thresholds:
            action = threshold['action']
            # Implement action handling based on the 'action' field
            if action == 'alert':
                # Trigger alert (e.g., send notification)
                logger.info(f"Alert triggered for Sensor ID {sensor_id} due to threshold breach.")
                # TODO: Implement alert logic here (e.g., send email/SMS)
            elif action == 'activate':
                # Activate device mapping
                update_query = """
                    UPDATE sensor_device_mapping
                    SET status = 1, activation_time = NOW()
                    WHERE sensor_id = %s AND status = 0
                """
                db_conn.execute_query(update_query, (sensor_id,))
                logger.info(f"Activated sensor-device mapping for Sensor ID {sensor_id}.")
            elif action == 'deactivate':
                # Deactivate device mapping
                update_query = """
                    UPDATE sensor_device_mapping
                    SET status = 0, activation_time = NULL
                    WHERE sensor_id = %s AND status = 1
                """
                db_conn.execute_query(update_query, (sensor_id,))
                logger.info(f"Deactivated sensor-device mapping for Sensor ID {sensor_id}.")
    except Exception as e:
        logger.error(f"Failed to activate sensor-device mapping for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")

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
        logger.info(f"Data Inserted | Sensor ID: {sensor_id} | Value: {value:.2f}")
    except Exception as e:
        logger.error(f"Failed to insert data for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")

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

def fetch_latest_reading(connection, sensor_id: int):
    """
    Fetches the latest reading for a given sensor.
    """
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
    """
    Fetches all active cycles for a given sensor.
    """
    try:
        select_query = """
            SELECT cycle_id, cycle_number, interval_seconds, duration_minutes, pause, is_active
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
                'pause': cycle['pause'],
                'is_active': cycle['is_active']
            }
            for cycle in cycles
        ]
        logger.info(f"Fetched {len(cycles_list)} active cycles for Sensor ID {sensor_id}: {cycles_list}")
        return cycles_list
    except Exception as e:
        logger.error(f"Failed to fetch cycles for Sensor ID: {sensor_id} | Error: {e}\n{traceback.format_exc()}")
        return []

################################################################################
# Cycle Worker Function
################################################################################

def cycle_worker(sensor_id: int, sensor, cycle: Dict[str, Any], stop_event: multiprocessing.Event, db_conn, sensor_type: str):
    """
    Handles the execution of a single cycle for a sensor.
    Updates the cycle status to inactive after it completes.
    """
    cycle_number = cycle['cycle_number']
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
            logger.info(f"Cycle Worker {cycle_number} (Cycle ID: {cycle_id}) pausing for {pause} seconds.")
            time.sleep(pause)

    finally:
        # Update the cycle status to inactive after completion
        logger.info(f"Cycle Worker {cycle_number} (Cycle ID: {cycle_id}) for Sensor ID {sensor_id} has completed.")
        update_cycle_status(db_conn, sensor_id, cycle_id)

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

        # Initialize the appropriate sensor based on sensor_type
        if sensor_type == 'ultrasonic':
            sensor = UltrasonicSensor(trig_pin=18, echo_pin=15)
        elif sensor_type in ['ph', 'ph_temp']:
            sensor = SensorReader()
        elif sensor_type in ['tank1', 'tank2']:
            sensor = TemperatureMonitor()
        elif sensor_type == 'light':
            sensor = LightSensor()
            sensor.power_on()

        logger.info(f"Sensor ID {sensor_id} of type '{sensor_type}' initialized.")

        while not stop_event.is_set():
            # Check if there is an active schedule for this sensor
            if is_active_schedule_for_sensor(db_conn, sensor_id):
                logger.info(f"Active schedule detected for Sensor ID {sensor_id}. Activating all cycles.")
                # Activate all cycles for this sensor by setting is_active = 1
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

def is_active_schedule_for_device(db_conn, device_id: int) -> bool:
    """
    Checks if there is an active schedule for the given device.
    """
    try:
        query = """
            SELECT COUNT(*) as active_count
            FROM schedules
            WHERE is_active = 1
              AND target_type = 'device'
              AND target_id = %s
              AND (
                  (recurrence = 'none' AND NOW() BETWEEN start_time AND end_time)
                  OR
                  (recurrence = 'daily' AND 
                      (TIME(NOW()) BETWEEN TIME(start_time) AND TIME(end_time)))
                  OR
                  (recurrence = 'weekly' AND 
                      DAYOFWEEK(NOW()) = DAYOFWEEK(start_time) AND 
                      (TIME(NOW()) BETWEEN TIME(start_time) AND TIME(end_time)))
                  OR
                  (recurrence = 'monthly' AND 
                      DAY(NOW()) = DAY(start_time) AND 
                      (TIME(NOW()) BETWEEN TIME(start_time) AND TIME(end_time)))
              )
        """
        result = db_conn.fetch_all(query, (device_id,), dictionary=True)
        active_count = result[0]['active_count'] if result else 0
        return active_count > 0
    except Exception as e:
        logger.error(f"Failed to check active schedules for Device ID: {device_id} | Error: {e}\n{traceback.format_exc()}")
        return False


def activate_device(device_id: int):
    """
    Activates the device (e.g., turn on the GPIO pin).
    """
    try:
        logger.info(f"Activating Device ID {device_id}.")
        # Add GPIO logic here to turn on the device
        # Example: gpio.output(device_pin, gpio.HIGH)
    except Exception as e:
        logger.error(f"Failed to activate Device ID {device_id}: {e}\n{traceback.format_exc()}")

def deactivate_device(device_id: int):
    """
    Deactivates the device (e.g., turn off the GPIO pin).
    """
    try:
        logger.info(f"Deactivating Device ID {device_id}.")
        # Add GPIO logic here to turn off the device
        # Example: gpio.output(device_pin, gpio.LOW)
    except Exception as e:
        logger.error(f"Failed to deactivate Device ID {device_id}: {e}\n{traceback.format_exc()}")

def monitor_devices(db_conn, stop_event: multiprocessing.Event):
    """
    Monitors and activates/deactivates devices based on their schedules.
    """
    device_states = {}  # Keep track of current device states to avoid redundant actions

    while not stop_event.is_set():
        try:
            # Fetch all devices
            devices_query = "SELECT device_id, device_name FROM devices WHERE is_active = 1"
            devices = db_conn.fetch_all(devices_query, (), dictionary=True)

            for device in devices:
                device_id = device['device_id']
                device_name = device['device_name']

                # Check if there's an active schedule for the device
                is_active = is_active_schedule_for_device(db_conn, device_id)

                # Activate or deactivate the device based on schedule
                if is_active and device_states.get(device_id) != "active":
                    activate_device(device_id)
                    device_states[device_id] = "active"
                    logger.info(f"Device {device_name} (ID {device_id}) activated based on schedule.")
                elif not is_active and device_states.get(device_id) != "inactive":
                    deactivate_device(device_id)
                    device_states[device_id] = "inactive"
                    logger.info(f"Device {device_name} (ID {device_id}) deactivated based on schedule.")

        except Exception as e:
            logger.error(f"Error while monitoring devices: {e}\n{traceback.format_exc()}")

        time.sleep(10)  # Check schedules every 10 seconds

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
            
            device_monitor_process = multiprocessing.Process(
                target=monitor_devices,
                args=(main_db_conn, stop_event),
                name="Device-Monitor-Process")
            device_monitor_process.start()


        logger.info("All sensor processes have been started. Entering main loop.")

        while True:
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
