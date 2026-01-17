import socket
import json
import cv2
import time

# ====== KONFIGURACJA SIECI ======
HOST = "0.0.0.0"  # Nasłuchuj na wszystkich interfejsach
PORT = 5005

# ====== KONFIGURACJA KAMERY ======
# 0 to zazwyczaj kamera wbudowana. Jeśli masz USB, spróbuj 1.
cap = cv2.VideoCapture(0)

# Ładowanie detektora twarzy
# Używamy standardowego haarcascade
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# ====== START SERWERA ======
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)

print(f"📡 Serwer czeka na połączenie na porcie {PORT}...")
print(f"👉 Sprawdź IP tego laptopa (ipconfig) i wpisz je w Omniverse.")

conn, addr = server_socket.accept()
print(f"✅ Połączono z: {addr}")

# Pobieramy rozdzielczość kamery, żeby znaleźć środek
ret, sample_frame = cap.read()
if ret:
    height, width, _ = sample_frame.shape
    center_x_screen = width // 2
    center_y_screen = height // 2
else:
    center_x_screen = 320
    center_y_screen = 240

try:
    while True:
        ret, frame = cap.read()
        if not ret: break

        # Obracamy obraz (lustro), żeby ruch był intuicyjny
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        data = {}

        if len(faces) > 0:
            # Bierzemy największą twarz (najbliższą)
            (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
            
            # --- KLUCZOWE OBLICZENIA ---
            # Środek twarzy
            face_center_x = x + w // 2
            face_center_y = y + h // 2
            
            # Obliczamy przesunięcie od środka ekranu
            offset_x = face_center_x - center_x_screen
            offset_y = face_center_y - center_y_screen
            
            # Z = GŁĘBIA = SZEROKOŚĆ TWARZY (w)
            # Im większe 'w', tym bliżej jesteś.
            depth_z = float(w)

            # Rysujemy ramkę na podglądzie (Laptop)
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            cv2.putText(frame, f"Z: {depth_z}", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

            data = {
                "found": True,
                "x": int(offset_x),
                "y": int(offset_y),
                "z": int(depth_z)  # <--- To jest ta wartość, której brakowało
            }
            
            # DEBUG W KONSOLI LAPTOPA
            print(f"Wysyłam: X={offset_x}, Y={offset_y}, Z={depth_z}")
            
        else:
            data = {"found": False}
            # print("Nie widzę twarzy...")

        # Wysyłanie JSON
        message = json.dumps(data) + "\n"
        try:
            conn.sendall(message.encode())
        except:
            print("❌ Klient rozłączony. Czekam ponownie...")
            conn, addr = server_socket.accept()

        # Pokaż okno z podglądem na laptopie
        cv2.imshow('Tracker Twarzy', frame)
        
        # 'q' żeby wyjść
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except Exception as e:
    print(f"Błąd: {e}")

finally:
    cap.release()
    conn.close()
    server_socket.close()
    cv2.destroyAllWindows()