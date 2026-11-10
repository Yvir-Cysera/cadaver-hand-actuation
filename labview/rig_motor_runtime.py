"""Motor I/O for the Towles rig. Importing this module opens no hardware."""
import asyncio
import atexit
import concurrent.futures
from contextlib import ExitStack
import math
import threading

import moteus
from serial.tools import list_ports


ROUTES = {1: ("COM5", "1A34E4DF"), 2: ("COM6", "99877172")}
IO_TIMEOUT = 2.0
CALL_TIMEOUT = 20.0


def position_torque(reply):
    return [reply.values[moteus.Register.POSITION], reply.values[moteus.Register.TORQUE]]


class Rig:
    """One LabVIEW Python session; every adapter operation lives on one loop."""
    def __init__(self):
        self._gate = threading.RLock()
        self._loop = None
        self._thread = None
        self._blocked = False
        self.owner = None
        self.motors = []
        self._stack = None
        self._driving = set()

    def _run(self, operation, *args):
        if not self._gate.acquire(timeout=CALL_TIMEOUT):
            raise RuntimeError("Motor runtime busy; no new command was submitted")
        try:
            if self._blocked:
                raise RuntimeError("Motor worker unresponsive; close the Python session before reuse")
            if self._loop is None:
                ready = concurrent.futures.Future()
                def run_loop():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    except Exception as exc:
                        ready.set_exception(exc)
                        return
                    ready.set_result(loop)
                    try:
                        loop.run_forever()
                    finally:
                        loop.close()
                self._thread = threading.Thread(target=run_loop, name="Towles motor I/O", daemon=True)
                self._thread.start()
                try:
                    self._loop = ready.result(timeout=CALL_TIMEOUT)
                except concurrent.futures.TimeoutError as exc:
                    self._blocked = True
                    raise RuntimeError("Motor worker did not start; close the Python session") from exc
            future = asyncio.run_coroutine_threadsafe(operation(*args), self._loop)
            try:
                return future.result(timeout=CALL_TIMEOUT)
            except concurrent.futures.TimeoutError:
                if future.done():
                    return future.result()
                self._blocked = True
                future.cancel()
                raise RuntimeError("Motor worker timed out; command outcome unknown; close the Python session")
        finally:
            self._gate.release()

    def _open(self, owner, ids):
        if not ids or len(set(ids)) != len(ids) or any(i not in ROUTES for i in ids):
            raise ValueError("Use the rig's configured motor IDs 1 and/or 2")
        ports = {p.device.upper(): (p.serial_number or "").upper() for p in list_ports.comports()}
        for motor_id in ids:
            port, serial = ROUTES[motor_id]
            if ports.get(port) != serial:
                raise RuntimeError(f"Motor {motor_id}: expected adapter {serial} on {port}; "
                                   f"found {ports.get(port) or 'no matching USB serial'}")
        with ExitStack() as opening:
            motors = []
            for motor_id in ids:
                port = ROUTES[motor_id][0]
                try:
                    adapter = opening.enter_context(moteus.Fdcanusb(path=port))
                    motors.append(moteus.Controller(id=motor_id, transport=adapter))
                except Exception as exc:
                    raise RuntimeError(f"Opening {port} for motor {motor_id}: {exc}") from exc
            self._stack = opening.pop_all()
        self.motors, self.owner = motors, owner

    async def io(self, motor, name, operation):
        label = f"{name} on {ROUTES[motor.id][0]} / motor {motor.id}"
        try:
            return await asyncio.wait_for(operation, timeout=IO_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise RuntimeError(f"Timeout during {label}") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed {label}: {exc}") from exc

    async def stop(self, motor):
        await self.io(motor, "stop", motor.set_stop())
        self._driving.discard(motor.id)

    async def query(self, motor, leave_drive=False):
        if leave_drive and motor.id in self._driving:
            await self.stop(motor)
        reply = await self.io(motor, "query", motor.query())
        if reply is None:
            raise RuntimeError(f"No reply from {ROUTES[motor.id][0]} / motor {motor.id}")
        return reply

    async def position(self, motor, **kwargs):
        self._driving.add(motor.id)
        reply = await self.io(motor, "position command", motor.set_position(query=True, **kwargs))
        if reply is None:
            raise RuntimeError(f"No command reply from {ROUTES[motor.id][0]} / motor {motor.id}")
        return reply

    async def _stop_all(self):
        errors = []
        for motor in self.motors:
            try:
                await self.stop(motor)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError("; ".join(errors))

    def _release(self):
        try:
            if self._stack is not None:
                self._stack.close()
        finally:
            self._stack, self.owner, self.motors = None, None, []
            self._driving.clear()

    async def _finish(self):
        try:
            await self._stop_all()
        finally:
            self._release()

    async def _begin(self, owner, ids):
        if self.owner is not None:
            if self.owner != owner:
                raise RuntimeError(f"{self.owner} owns the motor ports; close that session first")
            await self._finish()
        self._open(owner, ids)
        try:
            await self._stop_all()
            for motor in self.motors:
                reply = await self.query(motor)
                position = reply.values.get(moteus.Register.POSITION)
                if position is None or not math.isfinite(position):
                    raise RuntimeError(f"No finite startup position on {ROUTES[motor.id][0]} / motor {motor.id}")
        except BaseException:
            self._release()
            raise

    def begin(self, owner, ids):
        return self._run(self._begin, owner, ids)

    async def _perform(self, owner, operation):
        if self.owner != owner:
            raise RuntimeError(f"Start {owner} first; current motor owner: {self.owner}")
        try:
            return await operation(self)
        except BaseException as original:
            try:
                await self._finish()
            except Exception as cleanup:
                raise RuntimeError(f"{original}; stop/cleanup also failed: {cleanup}") from original
            raise

    def perform(self, owner, operation):
        return self._run(self._perform, owner, operation)

    async def _end(self, owner):
        if self.owner is None:
            return
        if self.owner != owner:
            raise RuntimeError(f"{self.owner} owns the motor ports; cannot close as {owner}")
        await self._finish()

    def end(self, owner):
        return self._run(self._end, owner)

    async def _snapshot(self):
        if self.owner is not None:
            raise RuntimeError(f"Close {self.owner} before running the read-only check")
        self._open("read-only check", (1, 2))
        try:
            rows = [position_torque(await self.query(m)) for m in self.motors]
            return [list(column) for column in zip(*rows)]
        finally:
            self._release()

    def snapshot(self):
        return self._run(self._snapshot)

    def shutdown(self):
        """Best effort at interpreter exit; VIs should call their explicit stop/close."""
        if not self._gate.acquire(timeout=CALL_TIMEOUT):
            raise RuntimeError("Motor session still busy during shutdown")
        try:
            if self._loop is not None and not self._blocked:
                try:
                    self._run(self._end, self.owner)
                finally:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                    self._thread.join(timeout=2.0)
                    self._loop = self._thread = None
        finally:
            self._gate.release()


rig = Rig()
atexit.register(rig.shutdown)


def read_only_snapshot():
    """One-shot bench test; returns [[p1,p2],[t1,t2]], with no motor state changes."""
    return rig.snapshot()
