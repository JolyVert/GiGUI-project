import socket
import json
import threading
import omni.usd
import omni.kit.app
from pxr import Gf, UsdGeom

# ====== KONFIGURACJA ======
HOST = "192.168.1.129" 
PORT = 5005
CAMERA_PATH = "/World/Camera" 

# --- KALIBRACJA RUCHU ---
TRANSLATION_SCALE_XY = 0.2  
TRANSLATION_SCALE_Z = 1.0  # Duża czułość głębi

BASE_FACE_SIZE = 65.0       # Wielkość twarzy "w spoczynku" (wyreguluj to patrząc w konsolę)

# --- WYGŁADZANIE (ANTY-DRGANIA) ---
SMOOTH_FACTOR = 0.05        # Zmniejszyłem na 0.05 (wolniejszy, bardziej "filmowy" ruch)
Z_HISTORY_FRAMES = 20       # Średnia z ilu klatek? (Im więcej, tym mniej drgań, ale wolniejsza reakcja na zoom)

# ====== ZMIENNE ======
current_head_data = {"found": False}
data_lock = threading.Lock()
sock = None
running = True

START_POS = Gf.Vec3d(0, 50, 300) 
smooth_pos = START_POS
target_pos_memory = START_POS 

# Bufor historii dla osi Z (żeby usunąć szum)
z_history = [] 

# ====== WĄTEK SIECIOWY ======
def network_thread():
    global current_head_data, sock
    print(f"🔌 Łączenie z {HOST}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
        print("✅ POŁĄCZONO!")
    except Exception as e:
        print(f"❌ Błąd: {e}")
        return

    buffer = ""
    while running:
        try:
            chunk = sock.recv(1024).decode()
            if not chunk: break
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                try:
                    obj = json.loads(line)
                    with data_lock:
                        current_head_data = obj
                except: pass
        except: break

threading.Thread(target=network_thread, daemon=True).start()

# ====== SETUP KAMERY ======
def get_camera_ops():
    stage = omni.usd.get_context().get_stage()
    if not stage: return None, None
    prim = stage.GetPrimAtPath(CAMERA_PATH)
    if not prim.IsValid(): return None, None
    xform = UsdGeom.Xformable(prim)
    translate_op = None
    for op in xform.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            translate_op = op
            break
    if not translate_op: translate_op = xform.AddTranslateOp()
    return translate_op, None

# Inicjalizacja
cam_trans, _ = get_camera_ops()
if cam_trans:
    START_POS = cam_trans.Get()
    smooth_pos = START_POS
    target_pos_memory = START_POS

# ====== PĘTLA UPDATE ======
def on_update(e):
    global smooth_pos, target_pos_memory, z_history

    target_data = None
    with data_lock:
        target_data = current_head_data.copy()
    
    if target_data.get("found", False):
        raw_x = float(target_data.get("x", 0))
        raw_y = float(target_data.get("y", 0))
        raw_z = float(target_data.get("z", 0)) 

        # --- ALGORYTM USUWANIA DRGAŃ (ŚREDNIA KROCZĄCA) ---
        # 1. Dodajemy nowy wynik do listy
        z_history.append(raw_z)
        
        # 2. Jeśli lista jest za długa, usuwamy najstarszy wynik
        if len(z_history) > Z_HISTORY_FRAMES:
            z_history.pop(0)
            
        # 3. Obliczamy średnią z całej listy
        avg_z = sum(z_history) / len(z_history)

        # --------------------------------------------------
        
        # Teraz używamy avg_z zamiast raw_z do obliczeń
        diff_z = avg_z - BASE_FACE_SIZE
        offset_z = -(diff_z * TRANSLATION_SCALE_Z)

        off_x = -raw_x * TRANSLATION_SCALE_XY
        off_y = -raw_y * TRANSLATION_SCALE_XY

        target_pos_memory = Gf.Vec3d(
            START_POS[0] + off_x,
            START_POS[1] + off_y,
            START_POS[2] + offset_z 
        )
    else:
        # Opcjonalnie: Jeśli zgubimy twarz, czyścimy historię, żeby nie "pamiętała" starych danych przy powrocie
        # Ale nie resetujemy pozycji kamery (efekt Freeze)
        if len(z_history) > 0:
            z_history.clear()

    # Wygładzanie (Lerp)
    smooth_pos = Gf.Vec3d(
        smooth_pos[0] + (target_pos_memory[0] - smooth_pos[0]) * SMOOTH_FACTOR,
        smooth_pos[1] + (target_pos_memory[1] - smooth_pos[1]) * SMOOTH_FACTOR,
        smooth_pos[2] + (target_pos_memory[2] - smooth_pos[2]) * SMOOTH_FACTOR
    )

    trans_op, _ = get_camera_ops()
    if trans_op:
        trans_op.Set(smooth_pos)

try: _sub = None 
except: pass
app = omni.kit.app.get_app()
_sub = app.get_update_event_stream().create_subscription_to_pop(on_update)
print("🚀 STABILIZACJA WŁĄCZONA (Anti-Jitter)")