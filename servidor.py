from flask import Flask, request, send_file
import wave
import os

app = Flask(__name__)

RAW_FILE = "grabacion.raw"
WAV_FILE = "grabacion.wav"

total_bytes = 0

@app.route('/stream', methods=['POST'])
def stream():
    global total_bytes
    if not request.data or len(request.data) < 128:  # bytes arbitrarios, ajusta si es necesario
        print("⚠️ Paquete ignorado: muy poco contenido")
        return 'Paquete vacío o silencioso', 204  # código personalizado (No Content)
    
    with open(RAW_FILE, 'ab') as f:
        f.write(request.data)
        total_bytes += len(request.data)
        print(f"📦 Bytes recibidos: {total_bytes}")
    return 'Bloque recibido', 200


@app.route('/finalizar', methods=['GET'])
def finalizar():
    # Leer datos y convertir a WAV
    with open(RAW_FILE, 'rb') as raw:
        data = raw.read()

    with wave.open(WAV_FILE, 'wb') as wav:
        wav.setnchannels(1)        # Mono
        wav.setsampwidth(2)        # 16 bits
        wav.setframerate(16000)    # 16kHz
        wav.writeframes(data)

    # Elimina RAW si ya no se usará
    os.remove(RAW_FILE)

    # Enviar archivo como descarga
    return send_file(WAV_FILE, as_attachment=True)

if __name__ == "__main__":
    # Elimina residuos de ejecuciones anteriores
    if os.path.exists(RAW_FILE):
        os.remove(RAW_FILE)
    if os.path.exists(WAV_FILE):
        os.remove(WAV_FILE)

    app.run(host="0.0.0.0", port=5000)
