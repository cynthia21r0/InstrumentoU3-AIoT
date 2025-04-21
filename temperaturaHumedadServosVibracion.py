import network
import time
import usocket
from umqtt.simple import MQTTClient
from machine import I2C, Pin, PWM

# === CONFIGURACIÓN WiFi y MQTT ===
WIFI_SSID = ""
WIFI_PASSWORD = ""
MQTT_BROKER = "192.168.1.14"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "esp32-sensor-actuador"

# === TÓPICOS MQTT ===
TOPIC_TEMP = "sensor/temperatura"
TOPIC_HUM = "sensor/humedad"
TOPIC_VIBRAR = "actuador/vibracion"

# === CONEXIÓN WiFi ===
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando a WiFi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            pass
    print("✅ Conectado a WiFi:", wlan.ifconfig())

# === CONEXIÓN MQTT ===
def connect_mqtt():
    # Primero verificar conexión con usocket
    try:
        addr = usocket.getaddrinfo(MQTT_BROKER, MQTT_PORT)[0][-1]
        print("📡 Probando conexión socket con broker:", addr)
        sock = usocket.socket()
        sock.connect(addr)
        print("✅ Conexión socket exitosa")
        sock.close()
    except Exception as e:
        print("❌ Error al conectar con socket:", e)
        return None
    
    # Luego intentar conexión MQTT
    for intento in range(3):
        try:
            client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER, port=MQTT_PORT)
            client.connect()
            print("✅ Conectado al broker MQTT")
            return client
        except Exception as e:
            print(f"❌ Intento {intento+1} fallido al conectar MQTT:", e)
            time.sleep(2)
    
    print("❌ No se pudo conectar al broker después de varios intentos.")
    return None

# === CLASE DEL SENSOR HDC1080 ===
class HDC1080:
    HDC1080_ADDR = 0x40
    REG_TEMP = 0x00
    REG_HUM = 0x01
    REG_CONFIG = 0x02
    REG_MANUFACTURER_ID = 0xFE
    REG_DEVICE_ID = 0xFF
    
    def __init__(self, i2c, address=HDC1080_ADDR):
        self.i2c = i2c
        self.address = address
        self.init_sensor()
    
    def init_sensor(self):
        config = bytearray([self.REG_CONFIG, 0x10, 0x00])
        self.i2c.writeto(self.address, config)
        time.sleep_ms(20)
    
    def read_register16(self, register):
        self.i2c.writeto(self.address, bytes([register]))
        data = self.i2c.readfrom(self.address, 2)
        return (data[0] << 8) | data[1]
        
    def read_temperature(self):
        self.i2c.writeto(self.address, bytes([self.REG_TEMP]))
        time.sleep_ms(20)
        data = self.i2c.readfrom(self.address, 2)
        raw_temp = (data[0] << 8) | data[1]
        return (raw_temp / 65536.0) * 165.0 - 40.0
        
    def read_humidity(self):
        self.i2c.writeto(self.address, bytes([self.REG_HUM]))
        time.sleep_ms(20)
        data = self.i2c.readfrom(self.address, 2)
        raw_hum = (data[0] << 8) | data[1]
        return (raw_hum / 65536.0) * 100.0

# === CONFIGURACIÓN DRV2605 (MOTOR DE VIBRACIÓN) ===
DRV2605_ADDR = 0x5A
MODE = 0x01
REAL_TIME_PLAYBACK = 0x02
WAVEFORM_SEQ = 0x04
GO = 0x0C
LIBRARY_SELECTION = 0x03

def write_register(i2c, reg, val):
    try:
        i2c.writeto_mem(DRV2605_ADDR, reg, bytes([val]))
    except Exception as e:
        print("⚠️ Error escribiendo en registro", reg, ":", e)

def read_register(i2c, reg):
    try:
        return int.from_bytes(i2c.readfrom_mem(DRV2605_ADDR, reg, 1), 'big')
    except Exception as e:
        print("⚠️ Error leyendo registro", reg, ":", e)
        return None

def drv2605_init(i2c):
    print("🎛️ Iniciando DRV2605...")
    write_register(i2c, MODE, 0x00)  # Salir de standby
    write_register(i2c, MODE, 0x01)  # Modo disparo interno
    write_register(i2c, LIBRARY_SELECTION, 1)  # Librería 1: ERM
    print("✅ DRV2605 inicializado.")

def vibrar(i2c, efecto=117):
    print("🔊 ¡Vibrando con efecto", efecto, "!")
    write_register(i2c, WAVEFORM_SEQ, efecto)
    write_register(i2c, WAVEFORM_SEQ + 1, 0)
    write_register(i2c, GO, 1)

# Función para mover un servo a un ángulo específico
def mover_servo(servo, angulo):
    # Convertir el ángulo (0-180) a duty (40-115 aprox para 50Hz)
    duty = int((angulo / 180) * 75 + 40)
    servo.duty(duty)

# Callback para mensajes MQTT
def mqtt_callback(topic, msg):
    global i2c
    if topic == TOPIC_VIBRAR.encode() and msg == b'activar':
        print("🔥 Activando vibración máxima!")
        vibrar(i2c, 47)  # 117 es el efecto más intenso
        time.sleep(1)  # Vibra por 5 segundos
        vibrar(i2c, 0)  # Detener vibración
        client.publish(TOPIC_VIBRAR, f"{47}")

# === FUNCIÓN PRINCIPAL ===
def main():
    global i2c, client
    
    # Conectar WiFi
    connect_wifi()
    
    # Configurar I2C - usamos un solo bus para ambos dispositivos
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
    
    # Inicializar sensor HDC1080
    sensor = HDC1080(i2c)
    
    # Inicializar DRV2605 (vibrador)
    drv2605_init(i2c)
    
    # Configurar servos
    servo1 = PWM(Pin(14), freq=50)
    servo2 = PWM(Pin(27), freq=50)
    
    # Inicializar servos en posición 0
    mover_servo(servo1, 0)
    mover_servo(servo2, 0)
    
    # Conectar MQTT
    client = connect_mqtt()
    if client is None:
        print("No se pudo conectar a MQTT. Reiniciando...")
        time.sleep(10)
        import machine
        machine.reset()
    
    # Configurar callback y suscribirse al tópico de vibración
    client.set_callback(mqtt_callback)
    client.subscribe(TOPIC_VIBRAR)
    
    print("🛜 Sistema listo. Monitoreando temperatura y esperando comandos MQTT...")
    
    temperatura_alta = False
    ultima_lectura = time.time()
    
    try:
        while True:
            # Verificar mensajes MQTT (no bloqueante)
            client.check_msg()
            
            # Leer y publicar valores del sensor cada 5 segundos
            tiempo_actual = time.time()
            if tiempo_actual - ultima_lectura >= 5:
                temp = sensor.read_temperature()
                hum = sensor.read_humidity()
                print(f"Temp: {temp:.2f} °C | Hum: {hum:.2f} %")
                
                # Publicar en MQTT
                client.publish(TOPIC_TEMP, f"{temp:.2f}")
                client.publish(TOPIC_HUM, f"{hum:.2f}")
                
                # Verificar si la temperatura es mayor a 25°C
                if temp > 30.0 and not temperatura_alta:
                    temperatura_alta = True
                    print("¡Temperatura alta! Moviendo servos a 90 grados")
                    mover_servo(servo1, 90)
                    mover_servo(servo2, 90)
                    
                    # Activar vibración como alerta adicional
                    vibrar(i2c, 70)  # Efecto suave de alerta
                    
                # Si la temperatura baja de 25°C y los servos están activados
                elif temp <= 30.0 and temperatura_alta:
                    temperatura_alta = False
                    print("Temperatura normal. Regresando servos a posición inicial")
                    mover_servo(servo1, 0)
                    mover_servo(servo2, 0)
                
                ultima_lectura = tiempo_actual
            
            # Pequeña pausa para no saturar el procesador
            time.sleep(0.1)
                
    except KeyboardInterrupt:
        # Limpiar recursos al detener el programa
        servo1.deinit()
        servo2.deinit()
        client.disconnect()
        print("Programa detenido")

# === EJECUTAR ===
if __name__ == "__main__":
    main()