import time
import adafruit_dht
import board

class DHT22Sensor:
    def __init__(self):
        """
        Initialize the DHT22 sensor.
        :param pin: The GPIO pin to which the DHT22 sensor is connected.
        """
        self.dht_device = adafruit_dht.DHT22(board.D17)

    def read_temperature(self):
        """
        Reads the temperature from the DHT22 sensor.
        :return: Temperature in Celsius or None if an error occurs.
        """
        try:
            return self.dht_device.temperature
        except RuntimeError as err:
            print(f"Error reading temperature: {err.args[0]}")
            return None

    def cleanup(self):
        """
        Perform any necessary cleanup.
        """
        self.dht_device.exit()

