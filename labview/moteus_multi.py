"""Multi-motor LabVIEW entry points. Array order is motor ID 1, then ID 2."""
import math
import operator
from pathlib import Path
import sys

_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)
import rig_motor_runtime as runtime


_OWNER = "multi"


def start_multi(num_motors=1):
    count = operator.index(num_motors)
    if count not in (1, 2):
        raise ValueError("Number of motors must be 1 or 2")
    runtime.rig.begin(_OWNER, tuple(range(1, count + 1)))


def stop_multi():
    runtime.rig.end(_OWNER)


def _columns(rows):
    return [list(column) for column in zip(*rows)]


def modes(num_motors, mode_list, pos_cmds, max_torques, vel_cmds, trq_cmds):
    """Return [[positions], [torques]]. Preserve the VI's four mode numbers."""
    async def apply(rig):
        if num_motors != len(rig.motors):
            raise ValueError("Number of motors differs from start_multi")
        commands = []
        for i in range(len(rig.motors)):
            mode = mode_list[i]
            if mode == 0:
                commands.append(None)
            elif mode == 1:
                commands.append(dict(position=pos_cmds[i], accel_limit=0.5,
                                     velocity_limit=0.1, maximum_torque=0.15))
            elif mode == 2:
                commands.append(dict(position=math.nan, velocity=vel_cmds[i],
                                     maximum_torque=max_torques[i]))
            elif mode == 3:
                commands.append(dict(position=math.nan, velocity=0, feedforward_torque=trq_cmds[i],
                                     kp_scale=0, kd_scale=0))
            else:
                raise ValueError(f"Invalid mode {mode} for motor {i + 1}")
        rows = []
        for motor, command in zip(rig.motors, commands):
            state = (await rig.query(motor, leave_drive=True) if command is None
                     else await rig.position(motor, **command))
            rows.append(runtime.position_torque(state))
        return _columns(rows)
    return runtime.rig.perform(_OWNER, apply)


def move(pos_cmds):
    async def apply(rig):
        if type(pos_cmds) is not list:
            raise TypeError("pos_cmds must be a list")
        if len(pos_cmds) != len(rig.motors):
            raise ValueError("Length of pos_cmds must match number of motors")
        rows = [runtime.position_torque(await rig.position(
            motor, position=pos, accel_limit=50, velocity_limit=100))
            for motor, pos in zip(rig.motors, pos_cmds)]
        return _columns(rows)
    return runtime.rig.perform(_OWNER, apply)


def _indexed_position(index, **kwargs):
    async def apply(rig):
        if not 0 <= index < len(rig.motors):
            raise ValueError(f"Motor index {index} out of range")
        return runtime.position_torque(await rig.position(rig.motors[index], **kwargs))
    return runtime.rig.perform(_OWNER, apply)


def torque(id, cmd=0.0):
    return _indexed_position(id, position=math.nan, velocity=0, feedforward_torque=cmd,
                             kp_scale=0, kd_scale=0)


def vel_trq(id, vel_cmd=0.0, trq_cmd=0.0):
    return _indexed_position(id, position=math.nan, velocity=vel_cmd, maximum_torque=trq_cmd)


def just_tel(num_motors):
    """Return positions in startup order. This read does not change the drive mode."""
    async def sample(rig):
        return [(await rig.query(m)).values[runtime.moteus.Register.POSITION] for m in rig.motors]
    return runtime.rig.perform(_OWNER, sample)
