import RPi.GPIO as GPIO
import time

class Feeder:
    def __init__(self, servo_pin):
        """
        Initialize the feeder with the specified servo pin.
        
        :param servo_pin: GPIO pin number connected to the servo motor.
        """
        self.servo_pin = servo_pin
        
        # Setup GPIO and PWM for the servo motor
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.servo_pin, GPIO.OUT)
        self.pwm = GPIO.PWM(self.servo_pin, 50)  # 50 Hz for servo
        self.pwm.start(0)  # Initialize with 0 duty cycle (neutral)

    def set_angle(self, angle):
        """
        Rotate the servo to a specific angle.
        
        :param angle: The target angle in degrees (0 to 180).
        """
        duty_cycle = 2 + (angle / 18)  # Convert angle to duty cycle
        GPIO.output(self.servo_pin, True)
        self.pwm.ChangeDutyCycle(duty_cycle)
        time.sleep(0.5)  # Allow time for the servo to reach the position
        GPIO.output(self.servo_pin, False)
        self.pwm.ChangeDutyCycle(0)  # Stop sending signal

    def open_feeder(self, open_duration=2):
        """
        Open the feeder for a specified duration and then close it.
        
        :param open_duration: Time (in seconds) the feeder remains open.
        """
        print("Opening feeder...")
        self.set_angle(90)  # Open position
        time.sleep(open_duration)
        print("Closing feeder...")
        self.set_angle(0)  # Closed position

    def cleanup(self):
        """
        Clean up GPIO resources.
        """
        self.pwm.stop()
        GPIO.cleanup()