"""LabVIEW setup functions for one explicitly selected rig motor."""
from pathlib import Path
import sys

_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)
import rig_motor_runtime as runtime


_OWNER = "setup"


def start(id):
    """Select the specified motor ID and stop it to clear errors."""
    runtime.rig.begin(_OWNER, (id,))


def just_tel():
    """Read the selected controller's current position."""
    async def sample(rig):
        state = await rig.query(rig.motors[0])
        return state.values[runtime.moteus.Register.POSITION]
    return runtime.rig.perform(_OWNER, sample)


def rezero():
    """Set the output position to zero, then return the position register."""
    async def apply(rig):
        motor = rig.motors[0]
        await rig.io(motor, "set output exact", motor.set_output_exact())
        return (await rig.query(motor)).values[runtime.moteus.Register.POSITION]
    return runtime.rig.perform(_OWNER, apply)


def pos_lims(min, max):
    """Set the same volatile minimum and maximum positions as the original VI."""
    async def apply(rig):
        motor = rig.motors[0]
        stream = runtime.moteus.Stream(motor)
        await rig.io(motor, "stop diagnostic telemetry", stream.write_message(b"tel stop"))
        await rig.io(motor, "flush diagnostic stream", stream.flush_read())
        await rig.io(motor, "set minimum", stream.command(
            f"conf set servopos.position_min {min}".encode("utf8")))
        await rig.io(motor, "set maximum", stream.command(
            f"conf set servopos.position_max {max}".encode("utf8")))
    return runtime.rig.perform(_OWNER, apply)


def close():
    """Release the setup session before starting another VI in the same Python host."""
    runtime.rig.end(_OWNER)
