from machine import Pin, ADC, Timer, PWM
from led import LED
from button import BUTTON
from potentiometer import POT
from encoder import ENCODER
from motor import MOTOR
from wifi import WIFI
import config_pin
import config_wifi

# ──────────────────────────────────────────────
#  Khởi tạo phần cứng
# ──────────────────────────────────────────────
# Chú ý: led_yellow và led_red dùng LED class (on/off) làm base,
# nhưng thực tế điều khiển qua pwm_yellow, pwm_red để chốt độ sáng.
# led_blue KHÔNG tạo – đèn Xanh chỉ dùng pwm_blue (tránh xung đột pin).
led_yellow, led_red = LED(config_pin.PIN_LED[1]), LED(config_pin.PIN_LED[2])

but1 = BUTTON(config_pin.PIN_BUTTON[0])   # Mode0: giữ = Xanh sáng | Mode1: Thuận
but2 = BUTTON(config_pin.PIN_BUTTON[1])   # Mode0: cạnh = Vàng lock 5s | Mode1: Nghịch
but3 = BUTTON(config_pin.PIN_BUTTON[2])   # Mode0: cạnh = Đỏ lock 5s  | Mode1: Stop

but_mode        = BUTTON(config_pin.PIN_MODE)         # Chuyển Mode 0 <-> 1
but_active_wifi = BUTTON(config_pin.PIN_ACTIVE_WIFI)  # Bật / tắt WiFi

pot     = POT(config_pin.PIN_ADC_POTEN)
encoder = ENCODER(config_pin.PIN_ENC_PHASEA, config_pin.PIN_ENC_PHASEB, 330)
motor   = MOTOR(config_pin.PIN_DRIVER_PWM, config_pin.PIN_DRIVER_IN1, config_pin.PIN_DRIVER_IN2)
wifi    = WIFI(config_wifi.ssid, config_wifi.passwd)

# ──────────────────────────────────────────────
#  PWM cho 3 đèn LED (điều chỉnh độ sáng theo ADC)
#  BUG FIX: Không tạo cả LED(pin) và PWM(pin) trên cùng 1 pin.
#  Đèn Xanh chỉ dùng pwm_blue; Vàng, Đỏ dùng PWM để chốt độ sáng.
# ──────────────────────────────────────────────
pwm_blue   = PWM(Pin(config_pin.PIN_LED[0]))
pwm_yellow = PWM(Pin(config_pin.PIN_LED[1]))
pwm_red    = PWM(Pin(config_pin.PIN_LED[2]))
pwm_blue.freq(1000)
pwm_yellow.freq(1000)
pwm_red.freq(1000)

def set_blue_pwm(adc_val):   pwm_blue.duty_u16(adc_val)
def set_yellow_pwm(adc_val): pwm_yellow.duty_u16(adc_val)
def set_red_pwm(adc_val):    pwm_red.duty_u16(adc_val)

def blue_off():   pwm_blue.duty_u16(0)
def yellow_off(): pwm_yellow.duty_u16(0)
def red_off():    pwm_red.duty_u16(0)

# ──────────────────────────────────────────────
#  Biến trạng thái
# ──────────────────────────────────────────────
flag_mode  = 0       # 0 = Mode 0 (LED Bài 2), 1 = Mode 1 (Motor Bài 3)
flag_wifi  = False   # WiFi đang hoạt động?

# Đèn Vàng – lock 5 s, CẤM ngắt lại
flag_yellow_lock   = False
timer_yellow_count = 0

# Đèn Đỏ – lock 5 s, CHO PHÉP ngắt lại (reset timer)
flag_red_lock      = False
timer_red_count    = 0

LOCK_TICKS = 50   # 50 × 100 ms = 5 s

# Trạng thái motor (Mode 1): 0=stop, 1=forward, 2=reverse
motor_state = 0

# Debounce / edge-detect các nút
prev_mode  = 1
prev_wifi  = 1
prev_but1  = 1
prev_but2  = 1
prev_but3  = 1

# ──────────────────────────────────────────────
#  Timer 100 ms – đếm ngược lock đèn Vàng & Đỏ
# ──────────────────────────────────────────────
def timer_100ms_cb(t):
    global flag_yellow_lock, timer_yellow_count
    global flag_red_lock,    timer_red_count

    if flag_yellow_lock:
        timer_yellow_count += 1
        if timer_yellow_count >= LOCK_TICKS:
            flag_yellow_lock   = False
            timer_yellow_count = 0
            yellow_off()   # dùng PWM tắt

    if flag_red_lock:
        timer_red_count += 1
        if timer_red_count >= LOCK_TICKS:
            flag_red_lock   = False
            timer_red_count = 0
            red_off()      # dùng PWM tắt

timer_lock = Timer(-1)
timer_lock.init(mode=Timer.PERIODIC, period=100, callback=timer_100ms_cb)

# ══════════════════════════════════════════════
#  MODE 0 – Tác vụ đèn (Bài 2)
# ══════════════════════════════════════════════

def task_blue_mode0(adc_val):
    """Đèn Xanh: sáng liên tục theo ADC khi giữ nút 1."""
    if but1.is_pressed() == 0:   # PULL_UP → 0 = nhấn
        set_blue_pwm(adc_val)
    else:
        blue_off()

def task_yellow_mode0_edge(adc_val):
    """Đèn Vàng: chốt mức sáng ADC hiện tại 5 s, CẤM ngắt khi đang lock."""
    global flag_yellow_lock, timer_yellow_count
    if flag_yellow_lock:
        return   # bỏ qua – cấm ngắt (dù vặn biến trở hay bấm thêm)
    # Chốt độ sáng theo ADC hiện tại
    set_yellow_pwm(adc_val)
    flag_yellow_lock   = True
    timer_yellow_count = 0

def task_red_mode0_edge(adc_val):
    """Đèn Đỏ: cập nhật độ sáng ADC mới + reset 5 s (CHO PHÉP ngắt)."""
    global flag_red_lock, timer_red_count
    # Cập nhật độ sáng MỚI và reset bộ đếm từ đầu
    set_red_pwm(adc_val)
    flag_red_lock   = True
    timer_red_count = 0

# ══════════════════════════════════════════════
#  MODE 1 – Tác vụ Motor (Bài 3)
# ══════════════════════════════════════════════

def task_mode1_forward(adc_val):
    """Nút 1 – Thuận: motor chạy thuận, đèn Xanh theo ADC."""
    global motor_state
    motor_state = 1
    motor.run_forward()
    motor.set_speed(int((adc_val * 100) / 65535))
    set_blue_pwm(adc_val)
    yellow_off()
    red_off()

def task_mode1_reverse(adc_val):
    """Nút 2 – Nghịch: motor chạy nghịch, đèn Vàng lock 5 s."""
    global motor_state, flag_yellow_lock, timer_yellow_count
    motor_state = 2
    motor.run_reverse()
    motor.set_speed(int((adc_val * 100) / 65535))
    if not flag_yellow_lock:
        set_yellow_pwm(adc_val)   # chốt mức sáng ADC hiện tại
        flag_yellow_lock   = True
        timer_yellow_count = 0
    blue_off()

def task_mode1_stop():
    """Nút 3 – Stop: motor phanh ngay, đèn Đỏ lock 5 s."""
    global motor_state, flag_red_lock, timer_red_count
    motor_state = 0
    motor.stop()
    # Lấy ADC hiện tại để set độ sáng đèn Đỏ
    set_red_pwm(pot.read_value())
    flag_red_lock   = True
    timer_red_count = 0
    blue_off()
    yellow_off()

# ══════════════════════════════════════════════
#  Vòng lặp chính
# ══════════════════════════════════════════════
while True:
    # 1. Đọc ADC biến trở
    adc_val = pot.read_value()   # 0 – 65535

    # ── Phát hiện cạnh nút MODE ──
    cur_mode = but_mode.is_pressed()
    if prev_mode == 1 and cur_mode == 0:    # cạnh xuống → toggle
        flag_mode = 1 - flag_mode
        blue_off()
        led_yellow.off_led()
        led_red.off_led()
        motor.stop()
    prev_mode = cur_mode

    # ── Phát hiện cạnh nút ACTIVE_WIFI ──
    cur_wifi_btn = but_active_wifi.is_pressed()
    if prev_wifi == 1 and cur_wifi_btn == 0:
        flag_wifi = not flag_wifi
        if flag_wifi:
            wifi.connect()
        else:
            wifi.disconnect()
    prev_wifi = cur_wifi_btn

    # ── Đọc trạng thái & cạnh nút 1-2-3 ──
    cur_but1 = but1.is_pressed()
    cur_but2 = but2.is_pressed()
    cur_but3 = but3.is_pressed()

    edge_but1 = (prev_but1 == 1 and cur_but1 == 0)
    edge_but2 = (prev_but2 == 1 and cur_but2 == 0)
    edge_but3 = (prev_but3 == 1 and cur_but3 == 0)

    # ══════════════════════════════
    if flag_mode == 0:
    # ══════════════════════════════
        # Đèn Xanh – liên tục khi giữ nút 1
        task_blue_mode0(adc_val)

        # Đèn Vàng – cạnh xuống, cấm ngắt khi lock
        if edge_but2:
            task_yellow_mode0_edge(adc_val)

        # Đèn Đỏ – cạnh xuống, cho phép ngắt lại (truyền adc_val để cập nhật độ sáng)
        if edge_but3:
            task_red_mode0_edge(adc_val)

        # Giao tiếp WiFi (Matlab)
        if flag_wifi:
            wifi.update()
            wifi.send(adc_val)

    # ══════════════════════════════
    else:  # flag_mode == 1
    # ══════════════════════════════
        # Nút 1 – Thuận (cạnh xuống kích hoạt)
        if edge_but1:
            task_mode1_forward(adc_val)

        # Nút 2 – Nghịch
        if edge_but2:
            task_mode1_reverse(adc_val)

        # Nút 3 – Stop
        if edge_but3:
            task_mode1_stop()

        # Cập nhật liên tục khi đang chạy thuận (dù đã thả nút)
        # Lưu đồ: "vặn biến trở → tốc độ + đèn Xanh thay đổi đồng thời"
        if motor_state == 1:
            motor.set_speed(int((adc_val * 100) / 65535))
            set_blue_pwm(adc_val)

        # Giao tiếp WiFi (gửi vận tốc encoder)
        if flag_wifi:
            wifi.update()
            wifi.send(encoder.get_velocity())

    # ── Lưu trạng thái prev ──
    prev_but1 = cur_but1
    prev_but2 = cur_but2
    prev_but3 = cur_but3