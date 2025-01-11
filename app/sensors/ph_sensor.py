import spidev
import time

class SensorReader:
    def __init__(self, bus=0, device=0, max_speed_hz=1350000):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device) 
        self.spi.max_speed_hz = max_speed_hz
    
    def read_channel(self, channel):
        """Read from the given channel (0-7)"""
        if channel < 0 or channel > 7:
            raise ValueError("Channel must be between 0 and 7")
        
        # MCP3008 uses 3 bytes for a read command
        r = self.spi.xfer2([1, (8 + channel) << 4, 0])
        return ((r[1] & 3) << 8) + r[2]
    
    def read_ph(self):
        """Read from the pH sensor (connected to channel 0)"""
        pH_value = self.read_channel(0)
        
        voltage = (pH_value / 1023.0) * 3.3
        # print(f"pH ADC Value: {pH_value}")
        # print(f"pH Voltage: {voltage:.2f} V")
        
        pH = (voltage - 2.5) / 0.18 
        # print(f"pH Value: {pH:.2f}")
        
        return pH
    
    def read_temperature(self):
        """Read from the temperature sensor (LM35, connected to channel 1)"""
        temp_value = self.read_channel(1)
        
        voltage = (temp_value / 1023.0) * 3.3
        temperature = voltage * 100
        
        return temperature

    def cleanup(self):
        """Close the SPI connection when done"""
        self.spi.close()