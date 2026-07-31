from machine import Pin, ADC, Timer, PWM
import utime
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

print("[SYSTEM] Khoi dong xong. Mode=0 | WiFi=OFF")
print(f"[PIN]   LED={config_pin.PIN_LED} | BTN={config_pin.PIN_BUTTON} | MODE={config_pin.PIN_MODE} | WIFI_BTN={config_pin.PIN_ACTIVE_WIFI}")
print(f"[PIN]   ADC={config_pin.PIN_ADC_POTEN} | ENC_A={config_pin.PIN_ENC_PHASEA} | ENC_B={config_pin.PIN_ENC_PHASEB}")
print(f"[PIN]   MOTOR PWM={config_pin.PIN_DRIVER_PWM} | IN1={config_pin.PIN_DRIVER_IN1} | IN2={config_pin.PIN_DRIVER_IN2}")
print("-" * 50)

# Trạng thái motor (Mode 1): 0=stop, 1=forward, 2=reverse
motor_state = 0

# Debounce / edge-detect các nút
prev_mode  = 1
prev_wifi  = 1
prev_but1  = 1
prev_but2  = 1
prev_but3  = 1

# Flag tu ISR – main loop doc de thuc hien hardware call va print
flag_log_yellow_done = False
flag_log_red_done    = False
flag_do_yellow_off   = False   # ISR yeu cau main loop tat den Vang
flag_do_red_off      = False   # ISR yeu cau main loop tat den Do

# ──────────────────────────────────────────────
#  Timer 100 ms – đếm ngược lock đèn Vàng & Đỏ
# ──────────────────────────────────────────────
def timer_100ms_cb(t):
    global flag_yellow_lock, timer_yellow_count
    global flag_red_lock,    timer_red_count
    global flag_log_yellow_done, flag_log_red_done
    global flag_do_yellow_off, flag_do_red_off

    if flag_yellow_lock:
        timer_yellow_count += 1
        if timer_yellow_count >= LOCK_TICKS:
            flag_yellow_lock     = False
            timer_yellow_count   = 0
            flag_do_yellow_off   = True  # Main loop se goi yellow_off()
            flag_log_yellow_done = True

    if flag_red_lock:
        timer_red_count += 1
        if timer_red_count >= LOCK_TICKS:
            flag_red_lock       = False
            timer_red_count     = 0
            flag_do_red_off     = True   # Main loop se goi red_off()
            flag_log_red_done   = True

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
        print("[LED]   Den Vang: Dang LOCK -> Bo qua lenh moi")
        return   # bỏ qua – cấm ngắt (dù vặn biến trở hay bấm thêm)
    # Chốt độ sáng theo ADC hiện tại
    set_yellow_pwm(adc_val)
    flag_yellow_lock   = True
    timer_yellow_count = 0
    print(f"[LED]   Den Vang: LOCK 5s | ADC={adc_val} | Duty={adc_val}")

def task_red_mode0_edge(adc_val):
    """Đèn Đỏ: cập nhật độ sáng ADC mới + reset 5 s (CHO PHÉP ngắt)."""
    global flag_red_lock, timer_red_count
    # Cập nhật độ sáng MỚI và reset bộ đếm từ đầu
    set_red_pwm(adc_val)
    flag_red_lock   = True
    timer_red_count = 0
    print(f"[LED]   Den Do: LOCK 5s (reset) | ADC={adc_val} | Duty={adc_val}")

# ══════════════════════════════════════════════
#  MODE 1 – Tác vụ Motor (Bài 3)
# ══════════════════════════════════════════════

def task_mode1_forward(adc_val):
    """Nút 1 – Thuận: motor chạy thuận, đèn Xanh theo ADC."""
    global motor_state
    motor_state = 1
    speed_pct = int((adc_val * 100) / 65535)
    motor.run_forward()
    motor.set_speed(speed_pct)
    set_blue_pwm(adc_val)
    yellow_off()
    red_off()
    print(f"[MOTOR] THUAN | Toc do={speed_pct}% | ADC={adc_val}")
    print(f"[LED]   Xanh ON | Vang OFF | Do OFF")

def task_mode1_reverse(adc_val):
    """Nút 2 – Nghịch: brake cứng 150ms rồi đảo chiều, đèn Vàng lock 5 s."""
    global motor_state, flag_yellow_lock, timer_yellow_count
    motor_state = 2
    speed_pct = int((adc_val * 100) / 65535)
    print(f"[MOTOR] Brake cung 150ms...")
    # Brake cứng trước khi đảo chiều – bảo vệ driver khỏi current spike
    motor.stop()
    utime.sleep_ms(150)
    motor.run_reverse()
    motor.set_speed(speed_pct)
    print(f"[MOTOR] NGHICH | Toc do={speed_pct}% | ADC={adc_val}")
    if not flag_yellow_lock:
        set_yellow_pwm(adc_val)   # chốt mức sáng ADC hiện tại
        flag_yellow_lock   = True
        timer_yellow_count = 0
        print(f"[LED]   Vang LOCK 5s | ADC={adc_val}")
    blue_off()

def task_mode1_stop():
    """Nút 3 – Stop: motor phanh ngay, đèn Đỏ lock 5 s."""
    global motor_state, flag_red_lock, timer_red_count
    motor_state = 0
    motor.stop()
    # Lấy ADC hiện tại để set độ sáng đèn Đỏ
    adc_now = pot.read_value()
    set_red_pwm(adc_now)
    flag_red_lock   = True
    timer_red_count = 0
    blue_off()
    yellow_off()
    print(f"[MOTOR] STOP")
    print(f"[LED]   Do LOCK 5s | ADC={adc_now} | Xanh OFF | Vang OFF")

# ══════════════════════════════════════════════
#  Vòng lặp chính
# ══════════════════════════════════════════════
while True:
  try:
    # 1. Đọc ADC biến trở
    adc_val = pot.read_value()   # 0 – 65535

    # ── Thuc hien lenh hardware tu Timer ISR (an toan trong main loop) ──
    if flag_do_yellow_off:
        flag_do_yellow_off = False
        yellow_off()
    if flag_do_red_off:
        flag_do_red_off = False
        red_off()

    # ── In log tu Timer ISR (an toan, goi tu main loop) ──
    if flag_log_yellow_done:
        flag_log_yellow_done = False
        print("[LED]   Den Vang: HET LOCK 5s -> TAT")
    if flag_log_red_done:
        flag_log_red_done = False
        print("[LED]   Den Do: HET LOCK 5s -> TAT")

    # ── Phát hiện cạnh nút MODE ──
    cur_mode = but_mode.is_pressed()
    if prev_mode == 1 and cur_mode == 0:    # cạnh xuống → toggle
        flag_mode = 1 - flag_mode
        blue_off()
        led_yellow.off_led()
        led_red.off_led()
        motor.stop()
        print(f"[BTN]   Nut MODE duoc nhan -> Chuyen sang MODE {flag_mode}")
        print(f"[LED]   Tat het den | Motor STOP")
    prev_mode = cur_mode

    # ── Phát hiện cạnh nút ACTIVE_WIFI ──
    cur_wifi_btn = but_active_wifi.is_pressed()
    if prev_wifi == 1 and cur_wifi_btn == 0:
        flag_wifi = not flag_wifi
        if flag_wifi:
            print("[BTN]   Nut WIFI duoc nhan -> Bat WiFi AP...")
            wifi.connect()
            print(f"[WIFI]  AP dang hoat dong | IP: {wifi._wifi.ifconfig()[0]}")
        else:
            print("[BTN]   Nut WIFI duoc nhan -> Tat WiFi")
            wifi.disconnect()
            print("[WIFI]  Da ngat ket noi")
    prev_wifi = cur_wifi_btn

    # ── Đọc trạng thái & cạnh nút 1-2-3 ──
    cur_but1 = but1.is_pressed()
    cur_but2 = but2.is_pressed()
    cur_but3 = but3.is_pressed()

    edge_but1 = (prev_but1 == 1 and cur_but1 == 0)
    edge_but2 = (prev_but2 == 1 and cur_but2 == 0)
    edge_but3 = (prev_but3 == 1 and cur_but3 == 0)

    if edge_but1: print(f"[BTN]   Nut 1 duoc nhan (Mode={flag_mode})")
    if edge_but2: print(f"[BTN]   Nut 2 duoc nhan (Mode={flag_mode})")
    if edge_but3: print(f"[BTN]   Nut 3 duoc nhan (Mode={flag_mode})")

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

        # Giao tiếp WiFi – gửi điện áp biến trở (0.0 – 3.3 V)
        if flag_wifi:
            wifi.update()
            voltage = round((adc_val / 65535) * 3.3, 4)
            wifi.send(voltage)
            print(f"[WIFI]  Mode0 - Gui voltage: {voltage}V | ADC={adc_val}", end='\r')

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
        if motor_state == 1:
            speed_now = int((adc_val * 100) / 65535)
            motor.set_speed(speed_now)
            set_blue_pwm(adc_val)
            print(f"[MOTOR] Dang THUAN | Speed={speed_now}% | ADC={adc_val}", end='\r')

        # Giao tiếp WiFi – gửi góc (degree) và vận tốc (RPM)
        if flag_wifi:
            wifi.update()
            angle    = round(encoder.get_angle(), 2)
            velocity = round(encoder.get_velocity(), 2)
            wifi.send(f"{angle},{velocity}")
            print(f"[WIFI]  Mode1 - Goc={angle}deg | Toc do={velocity}RPM", end='\r')

    # ── Lưu trạng thái prev ──
    prev_but1 = cur_but1
    prev_but2 = cur_but2
    prev_but3 = cur_but3

  except Exception as e:
    print(f"[CRASH] LOI: {e}")
    import utime
    utime.sleep_ms(2000)  # Dung lai 2s de doc loi truoc khi tiep tuc
