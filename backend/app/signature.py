"""Signature images: accept a photo or scan, return a clean transparent PNG.

A signature is usually photographed or scanned on white paper. Printed as is,
the paper shows as a grey or off-white box over the invoice. So on upload:

  1. decode the data URI and open it with Pillow (PNG, JPEG or WebP only);
  2. if it has no transparency of its own, turn the paper transparent: pixels
     lighter than the threshold vanish and the ink keeps its darkness;
  3. trim to the ink, with a small margin;
  4. scale down to at most 900 x 300 px and store as PNG.

The result is stored as a data URI so it travels with the tenant's data and
needs no file storage.
"""
import base64
import binascii
import io
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD = 3 * 1024 * 1024
MAX_W, MAX_H = 900, 300
PAPER = 200          # 0-255: anything lighter than this counts as paper


class SignatureError(ValueError):
    pass


def _decode(data_uri: str) -> bytes:
    if not data_uri or not data_uri.startswith("data:image/") or "base64," not in data_uri:
        raise SignatureError("Send the signature as an image (PNG, JPEG or WebP)")
    try:
        raw = base64.b64decode(data_uri.split("base64,", 1)[1], validate=True)
    except (binascii.Error, ValueError):
        raise SignatureError("That image could not be read")
    if len(raw) > MAX_UPLOAD:
        raise SignatureError("That image is over 3 MB. A photo or scan of the signature "
                             "alone is plenty.")
    return raw


def clean(data_uri: str) -> str:
    raw = _decode(data_uri)
    try:
        im = Image.open(io.BytesIO(raw))
        if im.format not in ("PNG", "JPEG", "WEBP", "MPO"):
            raise SignatureError("Use a PNG, JPEG or WebP image")
        im.load()
    except (UnidentifiedImageError, OSError):
        raise SignatureError("That file is not an image that can be read")
    im = ImageOps.exif_transpose(im)        # phone photos carry their rotation in EXIF
    im = im.convert("RGBA")

    alpha = im.getchannel("A")
    has_own_transparency = alpha.getextrema()[0] < 250
    if not has_own_transparency:
        # darkness of each pixel becomes its opacity; paper goes fully clear
        grey = ImageOps.grayscale(im.convert("RGB"))
        lut = [0 if v >= PAPER else min(255, int((PAPER - v) * 255 / (PAPER - 40)))
               for v in range(256)]
        im.putalpha(grey.point(lut))

    box = im.getchannel("A").point(lambda a: 255 if a > 24 else 0).getbbox()
    if not box:
        raise SignatureError("No signature could be found in that image. Use a dark pen "
                             "on white paper, photographed in good light.")
    pad = 6
    box = (max(0, box[0] - pad), max(0, box[1] - pad),
           min(im.width, box[2] + pad), min(im.height, box[3] + pad))
    im = im.crop(box)
    im.thumbnail((MAX_W, MAX_H), Image.LANCZOS)

    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()
