import network
from machine import I2S, Pin, ADC
import time
import urequests
from umqtt.simple import MQTTClient
import random
import math
import _thread

# ===========================
# CONFIGURACIÓN GENERAL
# ===========================
WIFI_SSID = ""
WIFI_PASSWORD = ""
MQTT_BROKER = "192.168.1.14"

MQTT_CLIENT_ID = f"dispositivo_hibrido_{random.randint(0, 10000)}"
MQTT_TOPIC_AUDIO = b"sensor/audio"
MQTT_TOPIC_AUDIO_RESP = b"sensor/audio/response"
MQTT_TOPIC_GAS = b"sensor/gas"

# LED indicador
try:
    led = Pin(2, Pin.OUT)
except:
    led = None

def blink_led(veces=2, delay=0.2):
    if led:
        for _ in range(veces):
            led.value(1)
            time.sleep(delay)
            led.value(0)
            time.sleep(delay)

# ===========================
# CONEXIÓN A WiFi
# ===========================
def conectar_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("🔌 Conectando a WiFi...")
        wlan.connect(ssid, password)
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            time.sleep(0.5)
            timeout -= 1
        if not wlan.isconnected():
            print("❌ Error de conexión WiFi")
            return False
    print("✅ Conectado a WiFi:", wlan.ifconfig())
    return True

# ===========================
# GRABACIÓN Y ENVÍO DE AUDIO
# ===========================
def grabar_y_enviar(buffer_size, ibuf_size, duracion_ms, cliente_mqtt):
    from os import remove
    if led: led.value(1)

    try:
        try: remove("audio.raw")
        except: pass

        i2s = I2S(
            0,
            sck=Pin(26), ws=Pin(25), sd=Pin(22),
            mode=I2S.RX, bits=16, format=I2S.MONO,
            rate=16000, ibuf=ibuf_size
        )
        time.sleep(0.5)

        with open("audio.raw", "wb") as f:
            inicio = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), inicio) < duracion_ms:
                buffer = bytearray(buffer_size)
                n = i2s.readinto(buffer)
                if n > 0:
                    f.write(buffer[:n])

        i2s.deinit()
        print("✅ Grabación terminada. Enviando bloques...")

        with open("audio.raw", "rb") as f:
            while True:
                chunk = f.read(1024)
                if not chunk: break
                urequests.post("http://192.168.1.14:5000/stream", data=chunk)

        urequests.get("http://192.168.1.14:5000/finalizar")
        print("📥 Descarga iniciada")
        cliente_mqtt.publish(MQTT_TOPIC_AUDIO_RESP, "ARCHIVO GUARDADO")
        blink_led(3, 0.2)

    except Exception as e:
        print("❌ Error:", e)
        cliente_mqtt.publish(MQTT_TOPIC_AUDIO_RESP, "HUBO UN FALLO")
        blink_led(2, 0.5)

    if led: led.value(0)

# ===========================
# SENSOR DE GAS MQ-135
# ===========================
PIN_SENSOR = 33
BITS_ADC = 4095
VOLTAJE_REF = 3.3
RL = 10.0
RZERO = 76.63
PARA = 116.6020682
PARB = -2.769034857

mq135 = ADC(Pin(PIN_SENSOR))
if hasattr(mq135, 'atten'):
    mq135.atten(ADC.ATTN_11DB)

def leer_mq135():
    suma = 0
    for _ in range(10):
        suma += mq135.read()
        time.sleep(0.1)
    adc_val = suma / 10
    voltaje = (adc_val / BITS_ADC) * VOLTAJE_REF
    if voltaje < 0.1: return float('inf')
    rs = ((VOLTAJE_REF - voltaje) / voltaje) * RL
    return rs

def calcular_ppm_co2(rs):
    if rs == float('inf') or rs <= 0: return 400
    ratio = rs / RZERO
    ppm = PARA * math.pow(ratio, PARB)
    return min(max(ppm, 380), 8000)

def categorizar_calidad(ppm):
    if ppm <= 400: return "Excelente"
    elif ppm <= 1000: return "Buena"
    elif ppm <= 2000: return "Moderada"
    elif ppm <= 5000: return "Mala"
    else: return "Peligrosa"

# ===========================
# MQTT
# ===========================
def mqtt_callback(topic, msg):
    print("📡 Mensaje recibido:", topic, msg)
    if topic == MQTT_TOPIC_AUDIO and msg == b"start":
        print("🟢 Activando grabación por MQTT...")
        grabar_y_enviar(2048, 16384, 60000, cliente)

def conectar_mqtt():
    try:
        c = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
        c.set_callback(mqtt_callback)
        c.connect()
        c.subscribe(MQTT_TOPIC_AUDIO)
        print("📻 Conectado a MQTT")
        return c
    except Exception as e:
        print("❌ Error MQTT:", e)
        return None

# ===========================
# FUNCIONES EN SEGUNDO NÚCLEO
# ===========================
def hilo_sensor_gas():
    print("⌛ Calentando sensor MQ-135...")
    time.sleep(30)
    while True:
        rs = leer_mq135()
        ppm = calcular_ppm_co2(rs)
        categoria = categorizar_calidad(ppm)
        print(f"📊 CO2: {ppm:.0f} ppm - {categoria}")
        try:
            cliente.publish(MQTT_TOPIC_GAS, f"{ppm:.0f} ppm - {categoria}")
        except Exception as e:
            print("❌ Error al publicar gas:", e)
        time.sleep(10)

# ===========================
# MAIN
# ===========================
def main():
    global cliente
    if not conectar_wifi(WIFI_SSID, WIFI_PASSWORD): return
    cliente = conectar_mqtt()
    if not cliente: return
    blink_led(5, 0.1)

    # Ejecutar lectura de gas en segundo núcleo
    _thread.start_new_thread(hilo_sensor_gas, ())

    while True:
        try:
            cliente.check_msg()
        except Exception as e:
            print("❌ Error MQTT:", e)
            cliente = conectar_mqtt()
        time.sleep(1)

if __name__ == "__main__":
    main()
