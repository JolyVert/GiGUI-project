import socket
import json
import cv2
import time
import numpy as np

# ====== KONFIGURACJA ======
HOST = "0.0.0.0"
PORT = 5005
CAP_ID = 0  # Zmień na 1, jeśli masz kamerę USB

# Parametry wygładzania (zmniejszają drgania Haar Cascade)
HISTORY_LEN = 5  # Średnia z ilu klatek? (Więcej = płynniej, ale wolniej)

# ====== INICJALIZACJA ======
cap = cv2.VideoCapture(CAP_ID)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST, PORT))
server_socket.listen(1)

print(f"📡 Serwer (OpenCV Stable) nasłuchuje na porcie {PORT}...")
conn, addr = server_socket.accept()
print(f"✅ Połączono z: {addr}")

# Bufory historii do wygładzania
history_x = []
history_y = []
history_z = []

try:
    while True:
        ret, frame = cap.read()
        if not ret: break

        # Obracamy i konwertujemy na szary (szybciej)
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Wykrywanie twarzy
        faces = face_cascade.detectMultiScale(gray, 1.1, 5)

        h, w_screen, _ = frame.shape
        center_x_screen = w_screen // 2
        center_y_screen = h // 2
        
        data = {"found": False}

        if len(faces) > 0:
            # Wybieramy największą twarz
            (x, y, w, h_face) = max(faces, key=lambda f: f[2] * f[3])

            # Środek twarzy
            curr_x = (x + w // 2) - center_x_screen
            curr_y = (y + h_face // 2) - center_y_screen
            curr_z = float(w) # Szerokość jako głębia

            # --- FILTR WYGŁADZAJĄCY (Anti-Jitter) ---
            history_x.append(curr_x)
            history_y.append(curr_y)
            history_z.append(curr_z)

            if len(history_x) > HISTORY_LEN:
                history_x.pop(0)
                history_y.pop(0)
                history_z.pop(0)

            # Oblicz średnią
            smooth_x = int(sum(history_x) / len(history_x))
            smooth_y = int(sum(history_y) / len(history_y))
            smooth_z = int(sum(history_z) / len(history_z))

            data = {
                "found": True,
                "x": smooth_x,
                "y": smooth_y,
                "z": smooth_z
            }

            # Rysowanie (wizualizacja)
            cv2.rectangle(frame, (x, y), (x+w, y+h_face), (0, 255, 0), 2)
            cv2.circle(frame, (x + w//2, y + h_face//2), 5, (0, 0, 255), -1)
            cv2.putText(frame, f"Z: {smooth_z}", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
        
        else:
            # Jeśli zgubi twarz, czyścimy historię powoli
            if len(history_x) > 0:
                history_x.pop(0)
                history_y.pop(0)
                history_z.pop(0)

        # Wysyłanie JSON
        try:
            msg = json.dumps(data) + "\n"
            conn.sendall(msg.encode())
        except (BrokenPipeError, ConnectionResetError):
            print("⚠️ Zerwano połączenie. Czekam...")
            conn, addr = server_socket.accept()
            print("✅ Ponowne połączenie!")

        cv2.imshow('Tracker Twarzy (Stable)', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except Exception as e:
    print(f"Błąd: {e}")

finally:
    cap.release()
    conn.close()
    server_socket.close()
    cv2.destroyAllWindows()