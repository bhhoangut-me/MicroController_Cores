from machine import Pin
class BUTTON:
    def __init__(self,pin):
        self._pin=Pin(pin,Pin.IN,Pin.PULL_UP) 
    def is_pressed(self):
        return self._pin.value()




        
