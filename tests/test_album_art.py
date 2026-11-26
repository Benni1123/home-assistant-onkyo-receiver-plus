"""The receiver CGI returns header-like text as part of the JPEG body."""

import unittest
from custom_components.onkyo_receiver_plus.album_art import decode_artwork


class AlbumArtTest(unittest.TestCase):
    def test_legacy_preamble(self):
        jpeg = b"\xff\xd8\xff\xe0fake"
        data, mime = decode_artwork(
            b"Content-size: 8\nContent-type: image/jpeg\n\n" + jpeg
        )
        self.assertEqual(data, jpeg)
        self.assertEqual(mime, "image/jpeg")

    def test_normal_image_and_no_image(self):
        jpeg = b"\xff\xd8\xff\xe0fake"
        self.assertEqual(decode_artwork(jpeg), (jpeg, "image/jpeg"))
        self.assertEqual(decode_artwork(b"<html>No image</html>"), (None, None))
