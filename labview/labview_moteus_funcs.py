"""Legacy single-motor LabVIEW node signatures, routed to ID 1 on COM5."""
import math
from pathlib import Path
import sys

_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)
import rig_motor_runtime as runtime


_OWNER = "single"


def start():
    runtime.rig.begin(_OWNER, (1,))


def stop():
    runtime.rig.end(_OWNER)


def get_tel():
    async def sample(rig):
        return runtime.position_torque(await rig.query(rig.motors[0], leave_drive=True))
    return runtime.rig.perform(_OWNER, sample)


def _position(**kwargs):
    async def apply(rig):
        return runtime.position_torque(await rig.position(rig.motors[0], **kwargs))
    return runtime.rig.perform(_OWNER, apply)


def hold():
    return _position(position=math.nan, velocity=0)


def move(cmd=math.nan):
    return _position(position=cmd, accel_limit=8)


def torque(cmd=0.0):
    return _position(position=math.nan, velocity=0, feedforward_torque=cmd, kp_scale=0, kd_scale=0)


def vel_trq(vel_cmd, trq_cmd):
    return _position(position=math.nan, velocity=vel_cmd, maximum_torque=trq_cmd)

