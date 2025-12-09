import socket
import json
import threading
import omni.usd
import omni.kit.app
from pxr import Gf, UsdGeom, Sdf

# ====== KONFIGURACJA ======
HOST = "192.168.1.235"  # IP Laptopa
PORT = 5005

# Pozycja bazowa kamery
START_POS = Gf.Vec3d(0.0, 150.0, 500.0) 

# --- CZUŁOŚĆ RUCHU (Nowe ustawienia) ---
# Skala dla ruchu lewo/prawo i góra/dół
TRANSLATION_SCALE_XY = 0.03 

# Skala dla ruchu przód/tył (GŁĘBIA)
# Zwiększ to, jeśli chcesz mocniejszy efekt przybliżania przy pochylaniu głowy.
TRANSLATION_SCALE_Z = 0.08  

# Czułość obrotu
ROTATION_SCALE = 0.015

# --- OPCJE RUCHU ---
# Czy odwrócić oś poziomą? (True = inwersja, False = normalnie)
INVERT_X_AXIS = True 

# --- OGRANICZENIA (Limity) ---
MAX_OFFSET_X = 80.0
MAX_OFFSET_Y = 50.0
MAX_OFFSET_Z = 150.0  # Zwiększone, żebyś mógł mocno się przybliżyć/oddalić
MAX_ROT_PITCH = 5.0 
MAX_ROT_YAW = 8.0   

# --- WYGŁADZANIE ---
SMOOTH_FACTOR = 0.06

# ====== ZMIENNE ======
current_head_data = None
data_lock = threading.Lock()
smooth_pos = START_POS
smooth_rot = Gf.Vec3d(0, 0, 0)

# ====== SIECIOWE ======
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.connect((HOST, PORT))
    print(f"✅ Połączono: {HOST}:{PORT}")
except Exception as e:
    print(f"❌ Błąd połączenia: {e}")
    sock = None

def network_listener():
    global current_head_data
    buffer = ""
    if not sock: return
    while True:
        try:
            data = sock.recv(1024).decode()
            if not data: break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                try:
                    obj = json.loads(line)
                    with data_lock:
                        current_head_data = obj
                except: pass
        except: break

if sock:
    threading.Thread(target=network_listener, daemon=True).start()

# ====== FUNKCJE POMOCNICZE ======
def clamp(n, minn, maxn):
    return max(min(n, maxn), minn)

def vec_lerp(v1, v2, t):
    return Gf.Vec3d(
        v1[0] + (v2[0] - v1[0]) * t,
        v1[1] + (v2[1] - v1[1]) * t,
        v1[2] + (v2[2] - v1[2]) * t
    )

# ====== SETUP KAMERY ======
def setup_camera_ops():
    stage = omni.usd.get_context().get_stage()
    if not stage: return None, None
    camera_prim = stage.GetPrimAtPath("/World/Camera")
    if not camera_prim: return None, None

    xform = UsdGeom.Xformable(camera_prim)
    
    translate_op = None
    rotate_op = None
    scale_op = None 

    for op in xform.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            translate_op = op
        elif op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
            rotate_op = op
        elif op.GetOpType() == UsdGeom.XformOp.TypeScale:
            scale_op = op

    if not translate_op: translate_op = xform.AddTranslateOp()
    if not rotate_op: rotate_op = xform.AddRotateXYZOp()
    
    new_order = [translate_op, rotate_op]
    if scale_op:
        new_order.append(scale_op)
        
    xform.SetXformOpOrder(new_order)
    return translate_op, rotate_op

# Inicjalizacja
cam_trans_op, cam_rot_op = setup_camera_ops()

# ====== UPDATE LOOP ======
def on_update(e):
    global current_head_data, smooth_pos, smooth_rot, cam_trans_op, cam_rot_op
    
    if cam_trans_op is None or cam_rot_op is None:
        cam_trans_op, cam_rot_op = setup_camera_ops()
        if cam_trans_op is None: return

    target_data = None
    with data_lock:
        if current_head_data: target_data = current_head_data
    
    if not target_data: return

    # Pobieranie danych
    raw_x = float(target_data.get("x", 0))
    raw_y = float(target_data.get("y", 0))
    raw_z = float(target_data.get("z", 0)) # Odległość głowy
    raw_pitch = float(target_data.get("pitch", 0))
    raw_yaw = float(target_data.get("yaw", 0))

    # --- OBLICZENIA POZYCJI ---
    
    # 1. Oś X (Inwersja)
    val_x = -raw_x if INVERT_X_AXIS else raw_x
    offset_x = clamp(val_x * TRANSLATION_SCALE_XY, -MAX_OFFSET_X, MAX_OFFSET_X)
    
    # 2. Oś Y (Góra/Dół - zazwyczaj odwrócona w USD)
    offset_y = clamp(-raw_y * TRANSLATION_SCALE_XY, -MAX_OFFSET_Y, MAX_OFFSET_Y)
    
    # 3. Oś Z (Głębia / Przód-Tył)
    # raw_z to odległość w mm (dużo = daleko, mało = blisko).
    # Omniverse Z: mniejsze Z = bliżej (do przodu).
    # Więc zależność jest prosta (więcej = dalej), ale musimy to przeskalować.
    offset_z = clamp(raw_z * TRANSLATION_SCALE_Z, -MAX_OFFSET_Z, MAX_OFFSET_Z)

    target_pos = START_POS + Gf.Vec3d(offset_x, offset_y, offset_z)

    # --- OBLICZENIA ROTACJI ---
    t_pitch = clamp(raw_pitch * ROTATION_SCALE, -MAX_ROT_PITCH, MAX_ROT_PITCH)
    t_yaw = clamp(raw_yaw * ROTATION_SCALE, -MAX_ROT_YAW, MAX_ROT_YAW)
    
    target_rot = Gf.Vec3d(t_pitch, t_yaw, 0)

    # Wygładzanie
    smooth_pos = vec_lerp(smooth_pos, target_pos, SMOOTH_FACTOR)
    smooth_rot = vec_lerp(smooth_rot, target_rot, SMOOTH_FACTOR)

    try:
        cam_trans_op.Set(smooth_pos)
        cam_rot_op.Set(smooth_rot)
    except Exception:
        cam_trans_op = None
        cam_rot_op = None

# ====== START ======
try: 
    if _update_sub: _update_sub = None
except: pass

app = omni.kit.app.get_app()
_update_sub = app.get_update_event_stream().create_subscription_to_pop(on_update)

print(f"✅ Tryb: Inverted X + Depth Z.")