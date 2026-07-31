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
but3 = BUTTON(config_pin.PIN_BUTTON[2])   # Mode0: cạnh = Đỏ lock 5s  | Mode1: Dừng

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
flag_mode    = 0       # 0 = Mode 0 (LED), 1 = Mode 1 (Motor)
flag_wifi    = False   # WiFi đang hoạt động?
flag_blue_on = False   # Đèn Xanh đang sáng? (dùng cho khóa chéo)

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

# Trạng thái motor (Mode 1): 0=dung, 1=thuan, 2=nghich
motor_state = 0

# Debounce / edge-detect các nút
prev_mode  = 1
prev_wifi  = 1
prev_but1  = 1
prev_but2  = 1
prev_but3  = 1

# Flag từ ISR – main loop đọc để thực hiện hardware call và print
flag_log_yellow_done = False
flag_log_red_done    = False
flag_do_yellow_off   = False   # ISR yêu cầu main loop tắt đèn Vàng
flag_do_red_off      = False   # ISR yêu cầu main loop tắt đèn Đỏ

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
            flag_do_yellow_off   = True   # Main loop sẽ gọi yellow_off()
            flag_log_yellow_done = True

    if flag_red_lock:
        timer_red_count += 1
        if timer_red_count >= LOCK_TICKS:
            flag_red_lock       = False
            timer_red_count     = 0
            flag_do_red_off     = True    # Main loop sẽ gọi red_off()
            flag_log_red_done   = True

timer_lock = Timer(-1)
timer_lock.init(mode=Timer.PERIODIC, period=100, callback=timer_100ms_cb)

# ══════════════════════════════════════════════
#  MODE 0 – Tác vụ đèn (Bài 2)
# ══════════════════════════════════════════════

def task_blue_mode0(adc_val):
    """Lưu đồ đèn Xanh:
    Nút Xanh đang nhấn? → Đèn Vàng và Đỏ đang tắt? → Bật Xanh + PWM theo ADC"""
    global flag_blue_on
    if but1.is_pressed() == 0:                          # Nút đang được nhấn
        if not flag_yellow_lock and not flag_red_lock:  # Cả Vàng và Đỏ đều đang tắt
            set_blue_pwm(adc_val)
            if not flag_blue_on:
                print(f"[LED]   Den Xanh: SANG | ADC={adc_val}")
            flag_blue_on = True
        else:                                           # Vàng hoặc Đỏ đang sáng → khóa chéo
            if flag_blue_on:
                print("[LED]   Den Xanh: TAT (Vang/Do dang sang - khoa cheo)")
            blue_off()
            flag_blue_on = False
    else:                                               # Thả nút
        if flag_blue_on:
            print("[LED]   Den Xanh: TAT (Tha nut 1)")
        blue_off()
        flag_blue_on = False


def task_yellow_mode0_edge(adc_val):
    """Lưu đồ đèn Vàng:
    Nút nhấn? → Đèn Xanh và Đỏ đang tắt? → Cờ Timer == 0? → Chốt ADC + Lock 5s (CẤM NGẮT)"""
    global flag_yellow_lock, timer_yellow_count

    # Khóa chéo: Xanh hoặc Đỏ đang sáng → BỎ QUA
    if flag_blue_on or flag_red_lock:
        print("[LED]   Den Vang: Bo qua (Xanh/Do dang sang - khoa cheo)")
        return

    # Cờ Timer Vang == 0? Nếu không (= đang lock) → CẤM NGẮT
    if flag_yellow_lock:
        print("[LED]   Den Vang: Dang LOCK -> Bo qua lenh moi (cam ngat)")
        return

    # Chốt giá trị ADC hiện tại và bắt đầu đếm 5s
    set_yellow_pwm(adc_val)
    flag_yellow_lock   = True
    timer_yellow_count = 0
    print(f"[LED]   Den Vang: SANG + LOCK 5s | ADC={adc_val} | Duty={adc_val}")


def task_red_mode0_edge(adc_val):
    """Lưu đồ đèn Đỏ:
    Nút nhấn? → Đèn Xanh và Vàng đang tắt? → Cập nhật ADC + Lock 5s (CHO PHÉP RESET)"""
    global flag_red_lock, timer_red_count

    # Khóa chéo: Xanh hoặc Vàng đang sáng → BỎ QUA
    if flag_blue_on or flag_yellow_lock:
        print("[LED]   Den Do: Bo qua (Xanh/Vang dang sang - khoa cheo)")
        return

    # Cập nhật độ sáng MỚI và reset bộ đếm từ đầu (CHO PHÉP nhấn lại/reset)
    set_red_pwm(adc_val)
    flag_red_lock   = True
    timer_red_count = 0
    print(f"[LED]   Den Do: SANG + LOCK 5s (reset) | ADC={adc_val} | Duty={adc_val}")


# ══════════════════════════════════════════════
#  MODE 1 – Tác vụ Motor (Bài 3)
# ══════════════════════════════════════════════

def task_mode1_forward(adc_val):
    """Nút 1 – Thuận: motor chạy thuận, đèn Xanh theo ADC.
    Tắt Vàng và Đỏ (xóa lock cũ)."""
    global motor_state, flag_blue_on
    global flag_yellow_lock, timer_yellow_count
    global flag_red_lock, timer_red_count
    motor_state = 1
    speed_pct   = int((adc_val * 100) / 65535)
    motor.run_forward()
    motor.set_speed(speed_pct)
    # Đèn Xanh bật, Vàng và Đỏ tắt (reset lock)
    set_blue_pwm(adc_val)
    flag_blue_on = True
    yellow_off()
    flag_yellow_lock   = False
    timer_yellow_count = 0
    red_off()
    flag_red_lock   = False
    timer_red_count = 0
    print(f"[BTN]   Nut THUAN duoc nhan")
    print(f"[MOTOR] CHAY THUAN | IN1=1 IN2=0 | Speed={speed_pct}% | ADC={adc_val}")
    print(f"[LED]   Xanh SANG | Vang TAT | Do TAT")


def task_mode1_reverse(adc_val):
    """Nút 2 – Nghịch: đảo chiều ngay lập tức bám theo biến trở.
    Chỉ lock Vàng 5s (cảnh báo lùi) - CẤM ngắt lại.
    Không lock Đỏ (theo mô tả)."""
    global motor_state, flag_yellow_lock, timer_yellow_count, flag_blue_on
    motor_state = 2
    speed_pct   = int((adc_val * 100) / 65535)
    print(f"[BTN]   Nut NGHICH duoc nhan")
    print(f"[MOTOR] Brake cung 150ms...")
    # Brake cứng trước khi đảo chiều – bảo vệ driver khỏi current spike
    motor.stop()
    utime.sleep_ms(150)
    motor.run_reverse()
    motor.set_speed(speed_pct)
    print(f"[MOTOR] CHAY NGHICH | IN1=0 IN2=1 | Speed={speed_pct}% | ADC={adc_val}")
    # Lock Vàng – CẤM ngắt lại (chỉ lock nếu chưa lock)
    if not flag_yellow_lock:
        set_yellow_pwm(adc_val)
        flag_yellow_lock   = True
        timer_yellow_count = 0
        print(f"[LED]   Vang SANG + LOCK 5s (canh bao lui) | ADC={adc_val}")
    else:
        print(f"[LED]   Vang dang LOCK -> Giu nguyen")
    # Tắt Xanh
    blue_off()
    flag_blue_on = False
    print(f"[LED]   Xanh TAT")


def task_mode1_stop():
    """Nút 3 – Dừng: motor phanh ngay lập tức.
    Lock Đỏ 5s (đặc tính cãm ngắt – báo dừng khẩn cấp) theo mô tả."""
    global motor_state, flag_red_lock, timer_red_count, flag_blue_on
    motor_state = 0
    motor.stop()
    # Tắt Xanh
    blue_off()
    flag_blue_on = False
    # Lock Đỏ 5s – CẤM ngắt lại (báo dừng khẩn cấp)
    adc_now = pot.read_value()
    if not flag_red_lock:
        set_red_pwm(adc_now)
        flag_red_lock   = True
        timer_red_count = 0
        print(f"[BTN]   Nut DUNG duoc nhan")
        print(f"[MOTOR] PHANH DUNG | IN1=0 IN2=0")
        print(f"[LED]   Do SANG + LOCK 5s (bao dung khan cap) | ADC={adc_now}")
        print(f"[LED]   Xanh TAT")
    else:
        print(f"[BTN]   Nut DUNG duoc nhan")
        print(f"[MOTOR] PHANH DUNG | IN1=0 IN2=0")
        print(f"[LED]   Do dang LOCK -> Giu nguyen | Xanh TAT")


# ══════════════════════════════════════════════
#  Vòng lặp chính
# ══════════════════════════════════════════════
while True:
  try:
    # 1. Đọc ADC biến trở
    adc_val = pot.read_value()   # 0 – 65535

    # ── Thực hiện lệnh hardware từ Timer ISR (an toàn trong main loop) ──
    if flag_do_yellow_off:
        flag_do_yellow_off = False
        yellow_off()
    if flag_do_red_off:
        flag_do_red_off = False
        red_off()

    # ── In log từ Timer ISR (an toàn, gọi từ main loop) ──
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
        flag_blue_on = False
        led_yellow.off_led()
        led_red.off_led()
        motor.stop()
        motor_state        = 0
        flag_yellow_lock   = False
        timer_yellow_count = 0
        flag_red_lock      = False
        timer_red_count    = 0
        print(f"[BTN]   Nut MODE duoc nhan -> Chuyen sang MODE {flag_mode}")
        print(f"[LED]   Tat het den | Motor STOP | Xoa lock Vang/Do")
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

    # ══════════════════════════════
    if flag_mode == 0:
    # ══════════════════════════════
        # Đèn Xanh – liên tục khi giữ nút 1
        # Khóa chéo: không sáng khi Vàng đang lock (xử lý trong task)
        task_blue_mode0(adc_val)

        # Đèn Vàng – cạnh xuống nút 2
        # Khóa chéo: tắt Xanh trước, cấm ngắt khi lock (xử lý trong task)
        if edge_but2:
            task_yellow_mode0_edge(adc_val)

        # Đèn Đỏ – cạnh xuống nút 3
        # Khóa chéo: tắt Xanh trước, cho phép ngắt/reset (xử lý trong task)
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
        # Nút 1 – Thuận (cạnh xuống)
        if edge_but1:
            task_mode1_forward(adc_val)

        # Nút 3 – Dừng (cạnh xuống)
        if edge_but3:
            task_mode1_stop()

        # Nút 2 – Nghịch (cạnh xuống)
        if edge_but2:
            task_mode1_reverse(adc_val)

        # Cập nhật liên tục khi đang chạy thuận (theo lưu đồ: Cờ Timer Xanh)
        if motor_state == 1:
            speed_now = int((adc_val * 100) / 65535)
            motor.set_speed(speed_now)
            set_blue_pwm(adc_val)
            flag_blue_on = True
            print(f"[MOTOR] Dang THUAN | Speed={speed_now}% | ADC={adc_val}", end='\r')
        else:
            if flag_blue_on:
                blue_off()
                flag_blue_on = False

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
    utime.sleep_ms(2000)  # Dừng lại 2s để đọc lỗi trước khi tiếp tục
