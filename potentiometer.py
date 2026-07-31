from machine import Pin,ADC
class POT:
    def __init__(self,pin):
        self._pin=ADC(Pin(pin))
    def read_value(self):
        return self._pin.read_u16()




        
