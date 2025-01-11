import smbus
import time

class LightSensor:
    DEVICE = 0x23

    POWER_DOWN = 0x00 
    POWER_ON   = 0x01 
    RESET      = 0x07

    CONTINUOUS_LOW_RES_MODE = 0x13
    CONTINUOUS_HIGH_RES_MODE_1 = 0x10
    CONTINUOUS_HIGH_RES_MODE_2 = 0x11
    ONE_TIME_HIGH_RES_MODE_1 = 0x20
    ONE_TIME_HIGH_RES_MODE_2 = 0x21
    ONE_TIME_LOW_RES_MODE = 0x23

    def __init__(self, bus_number=1, address=DEVICE):
        self.device_address = address
        self.bus = smbus.SMBus(bus_number)  # Initialize the bus (usually bus 1 for Raspberry Pi)

    def convert_to_number(self, data):
        result = (data[1] + (256 * data[0])) / 1.2  # Convert the raw data into light level
        return result

    def read_light(self, mode=ONE_TIME_HIGH_RES_MODE_1):
        """Reads light level in the specified mode"""
        data = self.bus.read_i2c_block_data(self.device_address, mode)
        return self.convert_to_number(data)

    def power_on(self):
        """Turn the sensor on"""
        self.bus.write_byte(self.device_address, self.POWER_ON)

    def power_down(self):
        """Turn the sensor off"""
        self.bus.write_byte(self.device_address, self.POWER_DOWN)

    def reset(self):
        """Reset the sensor"""
        self.bus.write_byte(self.device_address, self.RESET)
