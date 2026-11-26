"""Test receiver label import and preservation of HA overrides."""

import unittest

from custom_components.onkyo_receiver_plus.const import InputSource
from custom_components.onkyo_receiver_plus.source_names import (
    add_hdmi_prefixes,
    apply_input_names,
    parse_hdmi_assignments,
    parse_input_names,
    parse_presets,
)
from custom_components.onkyo_receiver_plus.util import get_meaning


class SourceNamesTest(unittest.TestCase):
    def test_parse_enabled_reported_names(self):
        self.assertEqual(
            parse_input_names(
                b'<response status="ok"><device><selectorlist>'
                b'<selector id="10" value="1" name="Google TV" />'
                b'<selector id="2b" value="1" name="NET &amp; Radio" />'
                b'<selector id="02" value="0" name="Hidden Game" />'
                b'<selector id="ff" value="1" name="Unknown" />'
                b'</selectorlist></device></response>'
            ),
            {InputSource("10"): "Google TV", InputSource("2B"): "NET & Radio"},
        )

    def test_parse_preset_table(self):
        presets = parse_presets(
            b'<response status="ok"><device><presetlist>'
            b'<preset id="1" band="0" freq="9830" name="hr3" />'
            b'<preset id="2" band="2" freq="0" name="DAB Plus Rock" />'
            b'<preset id="3" band="0" freq="0" name="" />'
            b'<preset id="0e" band="2" freq="0" name="SPUTNIK   " />'
            b'<preset id="14" band="0" freq="9000" name="Slot 20" />'
            b'<preset id="28" band="2" freq="0" name="Slot 40" />'
            b'<preset id="41" band="0" freq="1" name="Too high" />'
            b'<preset id="x" band="0" freq="1" name="Bad" />'
            b'</presetlist></device></response>'
        )
        self.assertEqual(presets[1], {"band": "0", "freq": 9830, "name": "hr3"})
        self.assertEqual(presets[2]["name"], "DAB Plus Rock")
        self.assertEqual(presets[3]["name"], "")
        self.assertEqual(presets[14]["name"], "SPUTNIK")
        self.assertEqual(presets[20]["name"], "Slot 20")
        self.assertEqual(presets[40]["name"], "Slot 40")
        self.assertNotIn(41, presets)
        self.assertNotIn("x", presets)

    def test_manual_name_and_selection_are_preserved(self):
        disc, game, aux = map(InputSource, ("10", "02", "03"))
        self.assertEqual(
            apply_input_names(
                {disc: get_meaning(disc), game: "Konsole"},
                {disc: "Google TV", game: "GAME", aux: "AUX"},
            ),
            {disc: "Google TV", game: "Konsole"},
        )
        self.assertEqual(
            apply_input_names(
                {disc: get_meaning(disc), game: "Google TV"}, {disc: "google tv"}
            ),
            {disc: get_meaning(disc), game: "Google TV"},
        )

    def test_invalid_xml_is_ignored(self):
        for payload in (b"garbage", b"<!DOCTYPE response><response />"):
            self.assertEqual(parse_input_names(payload), {})

    def test_tx_nr6050_hdmi_assignments_and_names(self):
        assignments = parse_hdmi_assignments(
            b"CBDHI1CBHI3GMHI2STHI4PCHI5CDNONTVNONAXHI6PHNON"
        )
        self.assertEqual(
            assignments,
            {InputSource(code): port for code, port in {
                "10": 1, "01": 3, "02": 2, "11": 4, "05": 5, "03": 6,
            }.items()},
        )
        self.assertEqual(
            add_hdmi_prefixes(
                dict(zip(map(InputSource, ("10", "02", "23")), ("Google TV", "HDMI 2 / Konsole", "CD"))),
                assignments,
            ),
            dict(zip(map(InputSource, ("10", "02", "23")), ("HDMI 1 / Google TV", "HDMI 2 / Konsole", "CD"))),
        )
        self.assertIsNone(parse_hdmi_assignments(b"CBDHI"))
        self.assertEqual(parse_hdmi_assignments(b"CBDNON"), {})
