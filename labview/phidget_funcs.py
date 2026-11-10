"""LabVIEW entry points for the two calibrated Phidget load-cell channels."""

from contextlib import ExitStack
from math import isfinite
from threading import Lock
from time import monotonic, sleep

from Phidget22.Devices.VoltageRatioInput import VoltageRatioInput
from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException


_REQUESTED_INTERVAL_MS = 32
_ATTACH_TIMEOUT_MS = 5000
_FIRST_SAMPLE_TIMEOUT_S = 5.0
_lock = Lock()
_session = None


def _close_session():
    """Called under the lock. Forget the session even if an SDK close fails."""
    global _session
    previous, _session = _session, None
    if previous is not None:
        cleanup, _ = previous
        cleanup.close()


def _ratio(number, channel):
    value = channel.getVoltageRatio()
    if not isfinite(value):
        raise ValueError(f"Phidget channel {number} returned a non-finite voltage ratio")
    return value


def _wait_for_first_samples(channels):
    """A newly attached bridge can report UNKNOWNVAL during initial calibration."""
    pending = dict(enumerate(channels, start=1))
    deadline = monotonic() + _FIRST_SAMPLE_TIMEOUT_S
    while pending:
        for number, channel in list(pending.items()):
            try:
                _ratio(number, channel)
            except PhidgetException as exc:
                if exc.code != ErrorCode.EPHIDGET_UNKNOWNVAL:
                    raise
            else:
                del pending[number]
        if pending:
            remaining = deadline - monotonic()
            if remaining <= 0:
                missing = ", ".join(str(n) for n in pending)
                raise TimeoutError(
                    f"No valid Phidget voltage ratio after {_FIRST_SAMPLE_TIMEOUT_S:g} s "
                    f"on channel(s) {missing} (EPHIDGET_UNKNOWNVAL)"
                )
            sleep(min(0.05, remaining))


def phidget_start():
    """Open channels 1 and 2. On failure, leave no session available for reads."""
    global _session
    with _lock:
        _close_session()
        with ExitStack() as cleanup:
            channels = []
            for number in (1, 2):
                channel = VoltageRatioInput()
                cleanup.callback(channel.close)
                channel.setChannel(number)
                try:
                    channel.openWaitForAttachment(_ATTACH_TIMEOUT_MS)
                except Exception as exc:
                    raise RuntimeError(
                        f"Could not attach Phidget load-cell channel {number}: {exc}"
                    ) from exc
                channels.append(channel)

            interval_ms = max(_REQUESTED_INTERVAL_MS,
                              *(ch.getMinDataInterval() for ch in channels))
            maximum_ms = min(ch.getMaxDataInterval() for ch in channels)
            if interval_ms > maximum_ms:
                raise RuntimeError(
                    f"No common load-cell interval at or above {interval_ms} ms "
                    f"(maximum supported by both: {maximum_ms} ms)"
                )
            for ch in channels:
                ch.setDataInterval(interval_ms)

            _wait_for_first_samples(channels)
            _session = (cleanup.pop_all(), channels)


def phidget_data():
    """Return [force1, force2] in newtons, or raise if a sample is unavailable."""
    with _lock:
        if _session is None:
            raise RuntimeError("Load cells are not initialized; call phidget_start() first")
        _, (in1, in2) = _session
        in1_value = _ratio(1, in1)
        in2_value = _ratio(2, in2)

    offset1, offset2 = -0.00015446, -0.00017916
    gain1, gain2 = -17173000, 16379000
    g_to_N = 0.009806650028639
    force1 = gain1 * (in1_value + offset1) * g_to_N
    force2 = gain2 * (in2_value + offset2) * g_to_N
    return [force1, force2]


def phidget_stop():
    """Close both channels. Safe before start, after failed start, and on repeat."""
    with _lock:
        _close_session()
