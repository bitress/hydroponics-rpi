import RPi.GPIO as GPIO
import time

# Pin setup
SERVO_PIN = 6  # GPIO 18 (pin 12)
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# Initialize PWM
pwm = GPIO.PWM(SERVO_PIN, 50)  # 50 Hz frequency
pwm.start(0)  # Start PWM with 0% duty cycle

def set_angle(angle):
    """Set the servo to a specific angle."""
    duty_cycle = 2 + (angle / 18)  # Map angle to duty cycle
    GPIO.output(SERVO_PIN, True)
    pwm.ChangeDutyCycle(duty_cycle)
    time.sleep(0.5)
    GPIO.output(SERVO_PIN, False)
    pwm.ChangeDutyCycle(0)

def feeder_action():
    """Simulate feeder opening and closing."""
    print("Feeder opening...")
    set_angle(90)  # Open position
    time.sleep(2)  # Stay open for 2 seconds (adjust as needed)
    print("Feeder closing...")
    set_angle(0)  # Closed position

try:
    while True:
        command = input("Press Enter to activate feeder or 'q' to quit: ")
        if command.lower() == 'q':
            break
        feeder_action()

except KeyboardInterrupt:
    print("Exiting program")

finally:
    pwm.stop()
    GPIO.cleanup()
