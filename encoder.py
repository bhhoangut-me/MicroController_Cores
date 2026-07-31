from machine import Pin,Timer
class ENCODER:
    def __init__(self,pin_phase_A,pin_phase_B,ppr):
        self._phaseA=Pin(pin_phase_A,Pin.IN)
        self._phaseB=Pin(pin_phase_B,Pin.IN)
        self._phaseA.irq(trigger=Pin.IRQ_FALLING|Pin.IRQ_RISING,handler=self._interrupt_phaseA)
        self._count=0
        self._ppr=ppr
        self._velocity=0
        self._last_count=0
        self.timer=Timer(-1)
        self.timer.init(mode=Timer.PERIODIC,period=20,callback=self._interrupt_timer)
    def _interrupt_timer(self,tim):
        delta_count=self._count-self._last_count
        self._last_count=self._count
        self._velocity=(delta_count*60)/(0.02*self._ppr*2)
    def _interrupt_phaseA(self,pin):
        if(self._phaseA.value()==1):
            if(self._phaseB.value()==0):
                self._count+=1
            else:
                self._count-=1
        else:
            if(self._phaseB.value()==0):
                self._count-=1
            else:
                self._count+=1

    def get_count(self):
        return self._count
    def get_angle(self):
        return (self._count*360)/(self._ppr*2)
    def get_velocity(self):
        return self._velocity