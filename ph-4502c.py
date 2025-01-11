import spidev
import time
import logging

# Setup logging to display debug information
logging.basicConfig(level=logging.INFO)

# Create an SPI instance
spi = spidev.SpiDev()
spi.open(0, 0)  # SPI bus 0, device (CE0)
spi.max_speed_hz = 1350000

# Constants for calibration (adjust based on your sensors)
PH_OFFSET = 2.5   # pH sensor offset
PH_SLOPE = 0.18   # pH sensor slope (mV per pH unit)
TEMP_SLOPE = 100  # LM35 gives 10mV per °C, so 100mV = 1°C

def read_channel(channel):
    """Read from the given channel (0-7) of the MCP3008 ADC"""
    if channel > 7 or channel < 0:
        logging.error("Invalid channel. Must be between 0 and 7.")
        return -1
    # MCP3008 uses 3 bytes for a read command
    r = spi.xfer2([1, (8 + channel) << 4, 0])
    # The result is in the last byte
    return ((r[1] & 3) << 8) + r[2]

def adc_to_voltage(adc_value, vref=3.3, max_adc=1023):
    """Convert ADC value to voltage"""
    return (adc_value / max_adc) * vref

def read_ph(channel=1):
    """Read the pH sensor value from the specified channel (default: 1)"""
    pH_value = read_channel(channel)
    if pH_value == -1:
        return None

    voltage = adc_to_voltage(pH_value)
    logging.debug(f"pH ADC Value: {pH_value}, Voltage: {voltage:.2f} V")
    
    # Convert voltage to pH value using calibration values
    pH = (voltage - PH_OFFSET) / PH_SLOPE
    logging.info(f"pH Value: {pH:.2f}")
    
    return pH

def read_temperature(channel=2):
    """Read temperature sensor (LM35) value from the specified channel (default: 2)"""
    temp_value = read_channel(channel)
    if temp_value == -1:
        return None

    voltage = adc_to_voltage(temp_value)
    temperature = voltage * TEMP_SLOPE  # LM35 gives 10mV per degree Celsius
    logging.debug(f"Temperature ADC Value: {temp_value}, Voltage: {voltage:.2f} V")
    logging.info(f"Temperature: {temperature:.2f} °C")
    
    return temperature

def main():
    """Main function to continuously read from sensors"""
    try:
        while True:
            # Read pH and temperature values
            ph = read_ph()
            if ph is not None:
                logging.info(f"Current pH: {ph:.2f}")
            else:
                logging.error("Failed to read pH sensor.")

            temperature = read_temperature()
            if temperature is not None:
                logging.info(f"Current Temperature: {temperature:.2f} °C")
            else:
                logging.error("Failed to read temperature sensor.")

            # Sleep for a while before reading again
            time.sleep(2)

    except KeyboardInterrupt:
        logging.info("Exiting due to KeyboardInterrupt.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        spi.close()

if __name__ == "__main__":
    main()
