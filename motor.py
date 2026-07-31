from machine import Pin,Timer,PWM
class MOTOR:
    def __init__(self,pin_pwm,pin_dir1,pin_dir2,freq=10000):
        self._pin_pwm=PWM(Pin(pin_pwm))
        self._pin_pwm.freq(freq)
        self._pin_pwm.duty_u16(0)
        self._pin_dir1=Pin(pin_dir1,Pin.OUT)
        self._pin_dir2=Pin(pin_dir2,Pin.OUT)
        self._pin_dir1.value(0)
        self._pin_dir2.value(0)
    def set_speed(self, speed_percent):
        self._pin_pwm.duty_u16(int((speed_percent*65535)/100))
    def run_forward(self):
        self._pin_dir1.value(1)
        self._pin_dir2.value(0)
    def run_reverse(self):   
        self._pin_dir1.value(0)
        self._pin_dir2.value(1)
    def stop(self):
        self._pin_dir1.value(0)
        self._pin_dir2.value(0)
        self._pin_pwm.duty_u16(0)