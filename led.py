from machine import Pin
class LED:
    def __init__(self,pin):
        self._led=Pin(pin,Pin.OUT) 
    def on_led(self):
        self._led.value(1)
    def off_led(self):
        self._led.value(0)



        
