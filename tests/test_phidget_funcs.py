"""Hardware-free tests; run with: python -m unittest discover -s tests."""

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "labview"))
import phidget_funcs as loads


def channel(min_ms=8, max_ms=1000):
    result = Mock(spec=loads.VoltageRatioInput)
    result.getMinDataInterval.return_value = min_ms
    result.getMaxDataInterval.return_value = max_ms
    result.getVoltageRatio.return_value = 0.00015
    return result


def sdk_error(code):
    error = loads.PhidgetException.__new__(loads.PhidgetException)
    error.code, error.description, error.details = code, "mock error", ""
    return error


class LoadCellTests(unittest.TestCase):
    def tearDown(self):
        loads.phidget_stop()

    def test_both_channels_are_attached_before_rate_selection_and_keep_calibration(self):
        first, second = channel(), channel()
        attached = []
        for number, ch in ((1, first), (2, second)):
            ch.openWaitForAttachment.side_effect = lambda ms, n=number: attached.append(n)
            ch.setDataInterval.side_effect = lambda ms: self.assertEqual(attached, [1, 2])
        first.getVoltageRatio.return_value = 0.00025446
        second.getVoltageRatio.return_value = 0.00037916
        with patch.object(loads, "VoltageRatioInput", side_effect=[first, second]):
            loads.phidget_start()
        for number, ch in ((1, first), (2, second)):
            ch.setChannel.assert_called_once_with(number)
            ch.openWaitForAttachment.assert_called_once_with(5000)
            ch.setDataInterval.assert_called_once_with(32)
        force1, force2 = loads.phidget_data()
        self.assertAlmostEqual(force1, -1717.3 * 0.009806650028639)
        self.assertAlmostEqual(force2, 3275.8 * 0.009806650028639)
        second.getVoltageRatio.side_effect = RuntimeError("unavailable")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            loads.phidget_data()

    def test_slower_device_limits_and_restart(self):
        first, second, third, fourth = channel(), channel(64), channel(), channel()
        with patch.object(loads, "VoltageRatioInput", side_effect=[first, second, third, fourth]):
            loads.phidget_start()
            loads.phidget_start()
        for ch in (first, second):
            ch.setDataInterval.assert_called_once_with(64)
            ch.close.assert_called_once()
        loads.phidget_stop()
        loads.phidget_stop()
        for ch in (third, fourth):
            ch.close.assert_called_once()

    def test_second_attachment_failure_closes_both_and_allows_retry(self):
        first, second, retry1, retry2 = channel(), channel(), channel(), channel()
        second.openWaitForAttachment.side_effect = TimeoutError("no sensor")
        with patch.object(loads, "VoltageRatioInput", side_effect=[first, second, retry1, retry2]):
            with self.assertRaisesRegex(RuntimeError, "channel 2: no sensor"):
                loads.phidget_start()
            with self.assertRaisesRegex(RuntimeError, "not initialized"):
                loads.phidget_data()
            for ch in (first, second):
                ch.close.assert_called_once()
                ch.setDataInterval.assert_not_called()
            loads.phidget_start()

    def test_impossible_interval_or_sdk_rejection_closes_both(self):
        for second in (channel(64, 100), channel()):
            first = channel(8, 40)
            second.setDataInterval.side_effect = RuntimeError("SDK rejected interval")
            with self.subTest(second_min=second.getMinDataInterval.return_value):
                with patch.object(loads, "VoltageRatioInput", side_effect=[first, second]):
                    with self.assertRaisesRegex(RuntimeError, "No common|SDK rejected"):
                        loads.phidget_start()
                for ch in (first, second):
                    ch.close.assert_called_once()
                with self.assertRaisesRegex(RuntimeError, "not initialized"):
                    loads.phidget_data()

    def test_stop_attempts_both_closes_if_one_fails(self):
        first, second = channel(), channel()
        with patch.object(loads, "VoltageRatioInput", side_effect=[first, second]):
            loads.phidget_start()
        second.close.side_effect = RuntimeError("close failed")
        with self.assertRaisesRegex(RuntimeError, "close failed"):
            loads.phidget_stop()
        first.close.assert_called_once()
        second.close.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, "not initialized"):
            loads.phidget_data()

    def test_unknown_first_sample_is_retried_only_for_unready_channel(self):
        first, second = channel(), channel()
        second.getVoltageRatio.side_effect = [sdk_error(loads.ErrorCode.EPHIDGET_UNKNOWNVAL), 0.0001]
        with patch.object(loads, "VoltageRatioInput", side_effect=[first, second]), \
             patch.object(loads, "sleep") as sleep:
            loads.phidget_start()
        first.getVoltageRatio.assert_called_once()
        self.assertEqual(second.getVoltageRatio.call_count, 2)
        sleep.assert_called_once()

    def test_unknown_value_timeout_names_missing_channel_and_closes_both(self):
        first, second = channel(), channel()
        second.getVoltageRatio.side_effect = sdk_error(loads.ErrorCode.EPHIDGET_UNKNOWNVAL)
        with patch.object(loads, "VoltageRatioInput", side_effect=[first, second]), \
             patch.object(loads, "monotonic", side_effect=[0.0, 5.0]):
            with self.assertRaisesRegex(TimeoutError, r"channel\(s\) 2 \(EPHIDGET_UNKNOWNVAL\)"):
                loads.phidget_start()
        first.close.assert_called_once()
        second.close.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, "not initialized"):
            loads.phidget_data()

    def test_nonrecoverable_read_error_is_not_retried(self):
        for value in (sdk_error(loads.ErrorCode.EPHIDGET_NOTATTACHED), float("nan")):
            with self.subTest(value=value):
                first, second = channel(), channel()
                first.getVoltageRatio.side_effect = [value]
                with patch.object(loads, "VoltageRatioInput", side_effect=[first, second]), \
                     patch.object(loads, "sleep") as sleep:
                    if isinstance(value, Exception):
                        with self.assertRaises(loads.PhidgetException) as caught:
                            loads.phidget_start()
                        self.assertIs(caught.exception, value)
                    else:
                        with self.assertRaisesRegex(ValueError, "non-finite"):
                            loads.phidget_start()
                sleep.assert_not_called()
                first.close.assert_called_once()
                second.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
