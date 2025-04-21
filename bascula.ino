#include "Adafruit_HX711.h"
#include <WiFi.h>
#include <PubSubClient.h>

const uint8_t DATA_PIN = 5;
const uint8_t CLOCK_PIN = 4;

Adafruit_HX711 hx711(DATA_PIN, CLOCK_PIN);

// Configuración WiFi y MQTT
const char* ssid = "";
const char* password = "";
const char* mqtt_server = "192.168.1.14";
const char* mqtt_topic = "sensor/carga";

WiFiClient espClient;
PubSubClient client(espClient);

// Variables para calibración
float calibration_factor = 23100.00;
float offset = 0;
float units;
float lastSentWeight = 0;

// Variables para control de tiempo (declaradas globalmente)
unsigned long lastMsg = 0;  // <<--- Declaración movida aquí
#define MSG_INTERVAL 2000
#define WEIGHT_THRESHOLD 0.1

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Conectando a ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi conectado");
  Serial.println("Dirección IP: ");
  Serial.println(WiFi.localIP());
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Intentando conexión MQTT...");
    if (client.connect("ESP32Client")) {
      Serial.println("conectado");
    } else {
      Serial.print("falló, rc=");
      Serial.print(client.state());
      Serial.println(" intentando de nuevo en 5 segundos");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {delay(10);}
  
  Serial.println("Iniciando sistema de pesaje HX711");
  
  hx711.begin();
  Serial.println("Iniciando tara...");
  
  offset = hx711.readChannelBlocking(CHAN_A_GAIN_128);
  
  Serial.println("Coloca la báscula vacía y envía 't' para tarar");
  Serial.println("Coloca un peso conocido y ajusta con '+' y '-' para calibrar");
  Serial.println("Envía 'c' para confirmar la calibración");

  setup_wifi();
  client.setServer(mqtt_server, 1883);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  int32_t reading = hx711.readChannelBlocking(CHAN_A_GAIN_128);
  units = (reading - offset) / calibration_factor;
  float currentWeight = abs(units);
  
  Serial.print("Peso: ");
  Serial.print(currentWeight, 1);
  Serial.println(" kg");

  // Publicar datos MQTT
  unsigned long now = millis();
  if (now - lastMsg > MSG_INTERVAL && currentWeight > WEIGHT_THRESHOLD) {
    if (abs(currentWeight - lastSentWeight) >= WEIGHT_THRESHOLD) {
      lastMsg = now;
      lastSentWeight = currentWeight;
      
      char payload[10];
      dtostrf(currentWeight, 1, 1, payload);
      
      client.publish(mqtt_topic, payload);
      Serial.print("Datos enviados: ");
      Serial.println(payload);
    }
  }

  if (Serial.available()) {
    char temp = Serial.read();
    
    if (temp == 't' || temp == 'T') {
      offset = hx711.readChannelBlocking(CHAN_A_GAIN_128);
      Serial.println("Báscula tarada");
    }
    
    if (temp == '+') calibration_factor += 100;
    else if (temp == '-') calibration_factor -= 100;
    else if (temp == 'a') calibration_factor += 10;
    else if (temp == 'z') calibration_factor -= 10;
    else if (temp == 'c' || temp == 'C') {
      Serial.print("Calibración finalizada. Factor: ");
      Serial.println(calibration_factor);
    }
  }
  
  delay(100);
}