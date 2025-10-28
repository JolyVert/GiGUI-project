import omni.usd
from pxr import UsdGeom
import asyncio
import socket
import json
from collections import deque

HOST = "192.168.0.231"
PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((HOST, PORT))
print(f"Connected {HOST}:{PORT}")
sock.setblocking(False)

stage = omni.usd.get_context().get_stage()
cam_path = "/World/Camera"

cam_prim = stage.GetPrimAtPath(cam_path)
if not cam_prim or not cam_prim.IsValid():
    print("New camera created")
    cam_prim = stage.DefinePrim(cam_path, "Camera")

cam_xform = UsdGeom.Xformable(cam_prim)

rotate_attr = None
for op in cam_xform.GetOrderedXformOps():
    if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
        rotate_attr = op
        break
if rotate_attr is None:
    rotate_attr = cam_xform.AddRotateXYZOp()


# =======================
yaw = pitch = roll = 0.0
buffer = ""
yaw_hist = deque(maxlen=15)
pitch_hist = deque(maxlen=15)

# =======================
def smooth_angle(curr, target, alpha=0.03, dead_zone=2.0, scale=0.2, clamp=None):
    delta = target - curr
    if abs(delta) < dead_zone:
        target = curr  
    target *= scale   
    if clamp:
        target = max(min(target, clamp[1]), clamp[0])
    return curr * (1 - alpha) + target * alpha

# =======================
async def recv_data():
    global yaw, pitch, roll, buffer
    while True:
        try:
            data = sock.recv(1024).decode()
            if not data:
                await asyncio.sleep(0.01)
                continue

            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                try:
                    obj = json.loads(line)
                    pitch = float(obj.get("pitch", 0.0))
                    yaw   = float(obj.get("yaw", 0.0))
                except json.JSONDecodeError:
                    pass

        except BlockingIOError:
            await asyncio.sleep(0.01)
        except Exception as e:
            print("Connection error:", e)
            break


# =======================
async def update_camera():
    global yaw, pitch
    curr_pitch, curr_yaw = 0.0, 0.0

    while True:
        yaw_hist.append(yaw)
        pitch_hist.append(pitch)

        yaw_avg = sum(yaw_hist) / len(yaw_hist)
        pitch_avg = sum(pitch_hist) / len(pitch_hist)

        curr_pitch = smooth_angle(curr_pitch, pitch_avg, alpha=0.03, dead_zone=2.0, scale=0.15, clamp=(-5, 5))
        curr_yaw   = smooth_angle(curr_yaw, yaw_avg, alpha=0.03, dead_zone=1.5, scale=0.2, clamp=(-30, 30))

        rotate_attr.Set((curr_pitch, curr_yaw, 0.0))

        await asyncio.sleep(0.03)  # ~33 FPS 

asyncio.ensure_future(recv_data())
asyncio.ensure_future(update_camera())
