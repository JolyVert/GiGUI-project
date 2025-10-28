import socket
import json
import cv2
import mediapipe as mp
import numpy as np

# === Налаштування TCP-сервера ===
HOST = "192.168.0.231"   
PORT = 5005

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  
server.bind((HOST, PORT))
server.listen(1)
print(f"Server listening on {HOST}:{PORT}")

conn, addr = server.accept()
print(f"Connected by {addr}")

# === Налаштування Mediapipe ===
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

cap = cv2.VideoCapture(0)

model_points = np.array([
    (0.0, 0.0, 0.0),             # nose
    (0.0, -330.0, -65.0),        # chin
    (-225.0, 170.0, -135.0),     # left eye
    (225.0, 170.0, -135.0),      # right eye
    (-150.0, -150.0, -125.0),    # left mouse
    (150.0, -150.0, -125.0)      # right mouse
])

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(frame_rgb)
        h, w, _ = frame.shape

        if results.multi_face_landmarks:
            face_landmarks = results.multi_face_landmarks[0]
            landmarks = face_landmarks.landmark

            image_points = np.array([
                (landmarks[1].x * w, landmarks[1].y * h),     
                (landmarks[152].x * w, landmarks[152].y * h), 
                (landmarks[33].x * w, landmarks[33].y * h),   
                (landmarks[263].x * w, landmarks[263].y * h), 
                (landmarks[61].x * w, landmarks[61].y * h),   
                (landmarks[291].x * w, landmarks[291].y * h)  
            ], dtype="double")

            focal_length = w
            center = (w / 2, h / 2)
            camera_matrix = np.array([[focal_length, 0, center[0]],
                                      [0, focal_length, center[1]],
                                      [0, 0, 1]], dtype="double")
            dist_coeffs = np.zeros((4, 1))

            success, rotation_vec, translation_vec = cv2.solvePnP(model_points, image_points, camera_matrix, dist_coeffs)

            if success:
                rotation_mat, _ = cv2.Rodrigues(rotation_vec)
                pose_mat = cv2.hconcat((rotation_mat, translation_vec))
                _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(pose_mat)

                pitch, yaw, roll = [float(angle) for angle in euler_angles]

                data = {"pitch": pitch, "yaw": yaw, "roll": roll}
                msg = json.dumps(data) + "\n"
                try:
                    conn.sendall(msg.encode())
                except Exception as e:
                    print("Connection lost:", e)
                    break

                cv2.putText(frame, f"Yaw: {yaw:.2f}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                cv2.putText(frame, f"Pitch: {pitch:.2f}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                cv2.putText(frame, f"Roll: {roll:.2f}", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

        cv2.imshow("Head Tracking Server", frame)
        if cv2.waitKey(1) & 0xFF == 27:  # ESC
            break

except KeyboardInterrupt:
    print("\nStopped manually")

finally:
    cap.release()
    conn.close()
    server.close()
    cv2.destroyAllWindows()
