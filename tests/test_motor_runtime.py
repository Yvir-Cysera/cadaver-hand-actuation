"""Hardware-free tests: replace port inventory, transport, controller, and stream."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "labview"))
import rig_motor_runtime as rt
import labview_moteus_funcs as single
import moteus_multi as multi
import setup_funcs as setup


class MotorTest(unittest.TestCase):
    def setUp(self):
        test = self
        self.events = []
        self.fail = {}
        self.receivers = set()
        self.in_flight = 0
        self.peak = 0
        self.rig = rt.Rig()
        self.ports = [SimpleNamespace(device=p, serial_number=s) for p, s in rt.ROUTES.values()]

        class Adapter:
            def __init__(self, path):
                self.port = path
                test.events.append(("open", path))
                if test.fail.get(("open", path)):
                    raise OSError("port busy")

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                test.events.append(("close", self.port))

        class Controller:
            def __init__(self, id, transport):
                self.id = id
                test.assertEqual(transport.port, rt.ROUTES[id][0])

            async def call(self, op, kwargs=None):
                test.receivers.add((threading.get_ident(), id(asyncio.get_running_loop())))
                test.events.append((op, self.id, kwargs))
                test.in_flight += 1
                test.peak = max(test.peak, test.in_flight)
                try:
                    fault = test.fail.get((op, self.id))
                    if fault == "timeout":
                        await asyncio.Event().wait()
                    if fault == "error":
                        raise OSError("injected error")
                    await asyncio.sleep(0.001)
                    return SimpleNamespace(values={
                        rt.moteus.Register.POSITION: float("nan") if fault == "bad position" else 10 + self.id,
                        rt.moteus.Register.TORQUE: 20 + self.id,
                    })
                finally:
                    test.in_flight -= 1

            def query(self):
                return self.call("query")

            def set_stop(self):
                return self.call("stop")

            def set_position(self, **kwargs):
                return self.call("drive", kwargs)

            def set_output_exact(self):
                return self.call("zero")

        class Stream:
            def __init__(self, motor):
                self.motor = motor

            def write_message(self, data):
                return self.motor.call("stream write", data)

            def flush_read(self):
                return self.motor.call("stream flush")

            def command(self, data):
                return self.motor.call("stream command", data)

        for mocked in [patch.object(rt, "rig", self.rig), patch.object(rt, "IO_TIMEOUT", 0.20),
                       patch.object(rt.list_ports, "comports", return_value=self.ports),
                       patch.object(rt.moteus, "Fdcanusb", Adapter), patch.object(rt.moteus, "Controller", Controller),
                       patch.object(rt.moteus, "Stream", Stream)]:
            mocked.start()
            self.addCleanup(mocked.stop)
        self.addCleanup(self.rig.shutdown)

    def events_of(self, op):
        return [row[1] for row in self.events if row[0] == op]

    def test_absolute_filename_import_without_sibling_on_sys_path(self):
        script = """
import importlib.util, pathlib, sys, types
sys.modules['moteus'] = types.ModuleType('moteus')
from serial.tools import list_ports
def forbidden(): raise AssertionError("unexpected port enumeration")
list_ports.comports = forbidden
path = pathlib.Path(sys.argv[1])
assert str(path.parent) not in sys.path
spec = importlib.util.spec_from_file_location('ni_loaded_by_filename', path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert pathlib.Path(mod.runtime.__file__).parent == path.parent
assert mod.runtime.rig._loop is None
"""
        for name in ("moteus_multi.py", "setup_funcs.py", "labview_moteus_funcs.py"):
            path = Path(rt.__file__).resolve().with_name(name)
            subprocess.run([sys.executable, "-I", "-B", "-c", script, str(path)], check=True)

    def test_read_only_and_partial_open(self):
        self.assertEqual(rt.read_only_snapshot(), [[11, 12], [21, 22]])
        self.assertEqual([r[0] for r in self.events], ["open", "open", "query", "query", "close", "close"])
        self.events.clear()
        self.fail["open", "COM6"] = True
        with self.assertRaisesRegex(RuntimeError, "COM6"):
            rt.read_only_snapshot()
        self.assertEqual(self.events, [("open", "COM5"), ("open", "COM6"), ("close", "COM5")])

    def test_swapped_serial_and_missing_peer(self):
        original = self.ports[1].serial_number
        self.ports[1].serial_number = self.ports[0].serial_number
        with self.assertRaisesRegex(RuntimeError, "expected adapter"):
            multi.start_multi(2)
        self.assertFalse(self.events)
        self.ports[1].serial_number = original
        self.fail["query", 2] = "bad position"
        with self.assertRaisesRegex(RuntimeError, "startup position.*COM6"):
            multi.start_multi(2)
        self.assertEqual(self.events_of("close"), ["COM6", "COM5"])
        with self.assertRaisesRegex(RuntimeError, "Start multi"):
            multi.move([0, 0])
        self.assertFalse(self.events_of("drive"))

    def test_modes_parameters_shape_and_leave_drive(self):
        multi.start_multi(2)
        self.events.clear()
        self.assertEqual(multi.modes(2, [0, 1], [100, 0.125], [], [], []), [[11, 12], [21, 22]])
        self.assertEqual(self.events_of("stop"), [])
        self.assertEqual(self.events[-1], ("drive", 2, dict(
            query=True, position=0.125, accel_limit=0.5, velocity_limit=0.1, maximum_torque=0.15)))
        self.events.clear()
        multi.modes(2, [0, 0], [], [], [], [])
        self.assertEqual([(r[0], r[1]) for r in self.events], [("query", 1), ("stop", 2), ("query", 2)])
        multi.modes(2, [2, 3], [], [0.07], [1.25], [0, -0.09])
        self.assertEqual(self.events[-2][2]["maximum_torque"], 0.07)
        self.assertEqual(self.events[-2][2]["velocity"], 1.25)
        self.assertEqual(self.events[-1][2]["feedforward_torque"], -0.09)
        self.assertEqual(self.events[-1][2]["kp_scale"], 0)
        self.assertEqual(self.events[-1][2]["kd_scale"], 0)
        self.assertEqual(multi.just_tel(2), [11, 12])
        self.assertEqual(multi.torque(0, 0.4), [11, 21])
        self.assertEqual(multi.vel_trq(1, 1.3, 0.8), [12, 22])
        self.assertEqual(multi.move([0, 0]), [[11, 12], [21, 22]])
        self.assertEqual(self.events[-1][2], dict(query=True, position=0, accel_limit=50, velocity_limit=100))
        multi.stop_multi()

    def test_timeout_never_retries_drive_and_stops_both_despite_error(self):
        multi.start_multi(2)
        self.events.clear()
        self.fail["drive", 1] = "timeout"
        self.fail["stop", 1] = "error"
        with self.assertRaisesRegex(RuntimeError, "Timeout.*COM5.*cleanup also failed"):
            multi.modes(2, [1, 1], [0.1, 0.2], [], [], [])
        self.assertEqual(self.events_of("drive"), [1])
        self.assertEqual(self.events_of("stop"), [1, 2])
        self.assertEqual(self.events_of("close"), ["COM6", "COM5"])
        self.assertIsNone(self.rig.owner)

    def test_single_loop_serializes_concurrent_callers(self):
        multi.start_multi(2)
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows = list(pool.map(multi.just_tel, [2] * 8))
        self.assertEqual(rows, [[11, 12]] * 8)
        self.assertEqual(len(self.receivers), 1)
        self.assertEqual(self.peak, 1)

    def test_setup_and_single_preserve_outputs_and_do_not_take_another_owner(self):
        setup.start(2)
        with self.assertRaisesRegex(RuntimeError, "setup owns"):
            single.start()
        with self.assertRaisesRegex(RuntimeError, "Close setup"):
            rt.read_only_snapshot()
        self.assertEqual(setup.just_tel(), 12)
        self.assertEqual(setup.rezero(), 12)
        self.assertEqual(self.events_of("zero"), [2])
        setup.pos_lims(-1.5, 2.5)
        self.assertEqual([e[2] for e in self.events if e[0] == "stream command"],
                         [b"conf set servopos.position_min -1.5", b"conf set servopos.position_max 2.5"])
        setup.close()
        single.start()
        self.assertEqual(single.get_tel(), [11, 21])
        self.assertEqual(single.move(0.25), [11, 21])
        self.assertEqual(self.events[-1], ("drive", 1, dict(query=True, position=0.25, accel_limit=8)))
        self.events.clear()
        self.assertEqual(single.get_tel(), [11, 21])
        self.assertEqual([(e[0], e[1]) for e in self.events], [("stop", 1), ("query", 1)])
        single.stop()


if __name__ == "__main__":
    unittest.main()
