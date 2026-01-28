from machine import Pin
import network
import socket
import time
import json
import urequests  # Library untuk HTTP request di MicroPython

# ===== KONFIGURASI WiFi =====
WIFI_SSID = "LAB RPL"      # Ganti dengan nama WiFi Anda
WIFI_PASSWORD = "#rpl1234"    # Ganti dengan password WiFi Anda

# ===== KONFIGURASI FLASK SERVER =====
FLASK_SERVER = "http://10.137.248.227:5000/"  # GANTI dengan IP komputer Flask Anda
API_ENDPOINT = f"{FLASK_SERVER}/api/sensor"

# ===== Pin Configuration =====
# Sensor 1 (Luar/Entry)
TRIG_PIN_1 = 5
ECHO_PIN_1 = 18

# Sensor 2 (Dalam/Exit)
TRIG_PIN_2 = 19
ECHO_PIN_2 = 21

# Initialize Sensors
trigger1 = Pin(TRIG_PIN_1, Pin.OUT)
echo1 = Pin(ECHO_PIN_1, Pin.IN, Pin.PULL_DOWN)
trigger2 = Pin(TRIG_PIN_2, Pin.OUT)
echo2 = Pin(ECHO_PIN_2, Pin.IN, Pin.PULL_DOWN)

CALIBRATION_FACTOR = 58.0

# ===== Konfigurasi Deteksi =====
DETECTION_THRESHOLD = 100  # cm - jarak untuk mendeteksi objek
DETECTION_TIMEOUT = 4000   # ms - maksimal waktu dari sensor1 ke sensor2 (4 detik)
MIN_DISTANCE_CHANGE = 30   # cm - perubahan jarak minimum untuk trigger
DEBOUNCE_TIME = 800        # ms - waktu tunggu setelah deteksi (0.8 detik)

# Counter data
counter_data = {
    "masuk": 0,
    "keluar": 0,
    "total": 0,
    "last_event": "none",
    "sensor1_distance": 0,
    "sensor2_distance": 0
}

# State untuk deteksi
state = {
    "sensor1_triggered": False,
    "sensor2_triggered": False,
    "trigger_time": 0,
    "last_detection": "none",
    "baseline_dist1": 0,
    "baseline_dist2": 0,
    "calibrated": False,
    "last_event_time": 0,
    "both_clear": True
}

def connect_wifi():
    """Connect to WiFi"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    time.sleep(1)
    
    print("Connecting to WiFi...")
    print(f"SSID: {WIFI_SSID}")
    
    try:
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        timeout = 15
        while not wlan.isconnected() and timeout > 0:
            print(".", end="")
            time.sleep(1)
            timeout -= 1
        print()
        
        if wlan.isconnected():
            print("WiFi Connected!")
            print("IP Address:", wlan.ifconfig()[0])
            return wlan.ifconfig()[0]
        else:
            print("WiFi Connection Failed - Timeout")
            return None
            
    except Exception as e:
        print(f"WiFi Error: {e}")
        return None

def send_to_flask(direction):
    """Kirim data ke Flask server"""
    try:
        payload = {"direction": direction}
        headers = {"Content-Type": "application/json"}
        
        print(f"Mengirim ke Flask: {direction}")
        response = urequests.post(API_ENDPOINT, json=payload, headers=headers)
        
        if response.status_code == 200:
            print(f"✓ Data '{direction}' berhasil dikirim ke Flask")
            return True
        else:
            print(f"✗ Flask error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Gagal kirim ke Flask: {e}")
        return False

def single_measure(trigger, echo):
    """Satu kali pengukuran"""
    trigger.value(0)
    time.sleep_ms(2)
    trigger.value(1)
    time.sleep_us(10)
    trigger.value(0)
    
    count = 0
    while echo.value() == 0 and count < 5000:
        count += 1
    if count >= 5000:
        return None
    
    start = time.ticks_us()
    
    count = 0
    while echo.value() == 1 and count < 5000:
        count += 1
    if count >= 5000:
        return None
    
    end = time.ticks_us()
    return time.ticks_diff(end, start)

def measure_distance(trigger, echo):
    """Ambil 2 sampel dan hitung rata-rata"""
    valid_readings = []
    
    for i in range(2):
        duration = single_measure(trigger, echo)
        if duration is not None:
            distance = duration / CALIBRATION_FACTOR
            if 1 <= distance <= 400:
                valid_readings.append(distance)
        time.sleep_ms(20)
    
    if len(valid_readings) >= 1:
        return sum(valid_readings) / len(valid_readings)
    return -1

def detect_direction(dist1, dist2):
    """Deteksi arah gerakan berdasarkan jarak sensor"""
    global state, counter_data
    
    # Kalibrasi baseline
    if not state["calibrated"]:
        if dist1 > 0 and dist2 > 0:
            state["baseline_dist1"] = dist1
            state["baseline_dist2"] = dist2
            state["calibrated"] = True
            print(f"✓ Baseline: S1={dist1:.1f}cm, S2={dist2:.1f}cm")
            print(f"✓ Deteksi: perubahan > {MIN_DISTANCE_CHANGE}cm dari baseline")
        else:
            print(f"⚠ Menunggu data valid... S1={dist1:.1f} S2={dist2:.1f}")
        return
    
    current_time = time.ticks_ms()
    
    # Debounce
    if time.ticks_diff(current_time, state["last_event_time"]) < DEBOUNCE_TIME:
        return
    
    # Hitung perubahan dari baseline
    change1 = abs(state["baseline_dist1"] - dist1) if dist1 > 0 and state["baseline_dist1"] > 0 else 0
    change2 = abs(state["baseline_dist2"] - dist2) if dist2 > 0 and state["baseline_dist2"] > 0 else 0
    
    # Deteksi objek
    sensor1_detected = dist1 > 0 and change1 > MIN_DISTANCE_CHANGE
    sensor2_detected = dist2 > 0 and change2 > MIN_DISTANCE_CHANGE
    
    # Cek kedua sensor clear
    both_clear = not sensor1_detected and not sensor2_detected
    
    # Reset jika timeout atau clear
    if time.ticks_diff(current_time, state["trigger_time"]) > DETECTION_TIMEOUT or \
       (both_clear and state["both_clear"]):
        if state["sensor1_triggered"] or state["sensor2_triggered"]:
            print("⚠ Timeout/Clear - reset state")
        state["sensor1_triggered"] = False
        state["sensor2_triggered"] = False
    
    state["both_clear"] = both_clear
    
    # LOGIKA MASUK (Sensor 1 -> Sensor 2)
    if sensor1_detected and not state["sensor1_triggered"] and not state["sensor2_triggered"]:
        state["sensor1_triggered"] = True
        state["trigger_time"] = current_time
        print(f">>> S1 triggered: Δ{change1:.1f}cm (menunggu S2...)")
    
    if state["sensor1_triggered"] and sensor2_detected and not state["sensor2_triggered"]:
        state["sensor2_triggered"] = True
        counter_data["masuk"] += 1
        counter_data["total"] = counter_data["masuk"] - counter_data["keluar"]
        counter_data["last_event"] = "masuk"
        state["last_detection"] = "masuk"
        state["last_event_time"] = current_time
        print(f"✅ MASUK! Δ1={change1:.1f}cm Δ2={change2:.1f}cm | Total: {counter_data['total']}")
        
        # KIRIM KE FLASK
        send_to_flask("in")
        
        state["sensor1_triggered"] = False
        state["sensor2_triggered"] = False
        return
    
    # LOGIKA KELUAR (Sensor 2 -> Sensor 1)
    if sensor2_detected and not state["sensor2_triggered"] and not state["sensor1_triggered"]:
        state["sensor2_triggered"] = True
        state["trigger_time"] = current_time
        print(f"<<< S2 triggered: Δ{change2:.1f}cm (menunggu S1...)")
    
    if state["sensor2_triggered"] and sensor1_detected and not state["sensor1_triggered"]:
        state["sensor1_triggered"] = True
        counter_data["keluar"] += 1
        counter_data["total"] = counter_data["masuk"] - counter_data["keluar"]
        counter_data["last_event"] = "keluar"
        state["last_detection"] = "keluar"
        state["last_event_time"] = current_time
        print(f"❌ KELUAR! Δ1={change1:.1f}cm Δ2={change2:.1f}cm | Total: {counter_data['total']}")
        
        # KIRIM KE FLASK
        send_to_flask("out")
        
        state["sensor1_triggered"] = False
        state["sensor2_triggered"] = False
        return

def start_server(ip):
    """Start web server (optional - untuk monitoring lokal)"""
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(5)
    
    print("=" * 50)
    print("Web Server Running!")
    print(f"Open browser: http://{ip}")
    print("=" * 50)
    
    return s

# Connect WiFi
ip = connect_wifi()
if ip is None:
    print("Cannot start without WiFi!")
    raise SystemExit

# Start local server (optional)
server = start_server(ip)

print("\n" + "=" * 50)
print("People Counter Active!")
print(f"Flask Server: {FLASK_SERVER}")
print("=" * 50)
print("\nKalibrasi baseline dalam 3 detik...")
print("⚠ PASTIKAN SENSOR SUDAH DI POSISI FINAL!")
print("⚠ Tidak ada objek di depan sensor!")
time.sleep(3)
print(f"✓ Deteksi: perubahan jarak > {MIN_DISTANCE_CHANGE}cm dari baseline")
print(f"✓ Timeout: {DETECTION_TIMEOUT/1000:.1f} detik")
print(f"✓ Debounce: {DEBOUNCE_TIME/1000:.1f} detik")
print("Sensor 1 -> Sensor 2 = MASUK ✅ (in)")
print("Sensor 2 -> Sensor 1 = KELUAR ❌ (out)")
print()

last_update = 0

while True:
    try:
        # Update sensor data
        if time.ticks_diff(time.ticks_ms(), last_update) > 150:
            dist1 = measure_distance(trigger1, echo1)
            time.sleep_ms(30)
            dist2 = measure_distance(trigger2, echo2)
            
            counter_data["sensor1_distance"] = dist1
            counter_data["sensor2_distance"] = dist2
            
            detect_direction(dist1, dist2)
            
            last_update = time.ticks_ms()
        
        # Handle web requests (optional - untuk monitoring lokal)
        server.settimeout(0.1)
        try:
            conn, addr = server.accept()
            request = conn.recv(1024).decode()
            
            if '/data' in request:
                response = json.dumps(counter_data)
                conn.send('HTTP/1.1 200 OK\n')
                conn.send('Content-Type: application/json\n')
                conn.send('Connection: close\n\n')
                conn.sendall(response)
            elif '/reset' in request:
                counter_data["masuk"] = 0
                counter_data["keluar"] = 0
                counter_data["total"] = 0
                counter_data["last_event"] = "none"
                conn.send('HTTP/1.1 200 OK\r\n')
                conn.send('Connection: close\r\n\r\n')
                conn.sendall('OK')
                print("✓ Counter direset!")
            elif '/calibrate' in request:
                state["calibrated"] = False
                state["sensor1_triggered"] = False
                state["sensor2_triggered"] = False
                print("\n⚙ Kalibrasi ulang dalam 3 detik...")
                print("Pastikan tidak ada objek di depan sensor!")
                time.sleep(3)
                
                samples1 = []
                samples2 = []
                for i in range(5):
                    d1 = measure_distance(trigger1, echo1)
                    time.sleep_ms(100)
                    d2 = measure_distance(trigger2, echo2)
                    if d1 > 0:
                        samples1.append(d1)
                    if d2 > 0:
                        samples2.append(d2)
                    time.sleep_ms(200)
                
                if len(samples1) >= 3 and len(samples2) >= 3:
                    state["baseline_dist1"] = sum(samples1) / len(samples1)
                    state["baseline_dist2"] = sum(samples2) / len(samples2)
                    state["calibrated"] = True
                    print(f"✓ Baseline baru: S1={state['baseline_dist1']:.1f}cm, S2={state['baseline_dist2']:.1f}cm")
                    conn.send('HTTP/1.1 200 OK\r\n')
                    conn.send('Connection: close\r\n\r\n')
                    conn.sendall('OK')
                else:
                    print("✗ Kalibrasi gagal!")
                    conn.send('HTTP/1.1 500 ERROR\r\n')
                    conn.send('Connection: close\r\n\r\n')
                    conn.sendall('FAILED')
            
            conn.close()
        except OSError:
            pass
            
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.close()
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(1)