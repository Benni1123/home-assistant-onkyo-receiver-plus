"""Unit tests for the temporary subwoofer level codec."""

import unittest

from custom_components.onkyo_receiver_plus.subwoofer import decode_level, encode_level


class SubwooferTest(unittest.TestCase):
    def test_known_device_replies(self):
        self.assertEqual(decode_level(b"+06"), 3)
        self.assertEqual(decode_level(b"+05"), 2.5)
        self.assertEqual(encode_level(2.5), b"+05")

    def test_protocol_limits_and_signs(self):
        for level in (-15, -0.5, 0, 0.5, 12):
            with self.subTest(level=level):
                self.assertEqual(decode_level(encode_level(level)), level)
        self.assertEqual(encode_level(-15), b"-1E")
        self.assertEqual(decode_level(b"00"), 0)
        self.assertEqual(decode_level(b"000"), 0)

    def test_reject_bad_values(self):
        for value in (b"N/A", b"QSTN", b"+FF", b"+5"):
            self.assertIsNone(decode_level(value))
        for value in (-15.5, 12.5, 0.25, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                encode_level(value)
