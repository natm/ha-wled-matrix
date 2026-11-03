"""Camera screens: a Home Assistant camera's still image, scaled to the matrix.

The still comes from Home Assistant's camera proxy (`/api/camera_proxy/<camera entity>`), which serves the current
snapshot as a JPEG. It is decoded and scaled with Pillow, which is only needed for camera screens: add `Pillow` to the
AppDaemon app's `python_packages`.
"""

import io
import os
import time
import urllib.request

try:
    from PIL import Image, ImageEnhance, ImageOps
except ImportError:  # only camera screens need Pillow
    Image = None


def default_connection():
    """Home Assistant's URL and token as seen from the AppDaemon app on Home Assistant OS (Supervisor proxy)."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    return ("http://supervisor/core", token) if token else (None, None)


class CameraSource:
    """Fetches and scales camera stills, at most once per `min_interval` seconds per camera."""

    def __init__(self, url=None, token=None, log=print, min_interval=0.9):
        default_url, default_token = default_connection()
        self.url = (url or default_url or "").rstrip("/")
        self.token = token or default_token
        self.log = log
        self.min_interval = min_interval
        self.cache = {}  # (camera, w, h, fit) -> (time, pixels)
        self.warned = set()

    def warn_once(self, key, message):
        if key not in self.warned:
            self.warned.add(key)
            self.log(message, level="WARNING")

    def pixels(self, screen, width, height):
        """The screen's camera as a list of (r, g, b) rows-first, or None if it can't be fetched."""
        camera = screen["camera"]
        fit = screen.get("fit", "crop")
        key = (camera, width, height, fit)
        now = time.monotonic()
        cached = self.cache.get(key)
        if cached and now - cached[0] < self.min_interval:
            return cached[1]  # several matrices showing the same camera share one fetch
        if Image is None:
            self.warn_once("pillow", "Camera screens need Pillow: add it to AppDaemon's python_packages")
            return None
        if not self.url or not self.token:
            self.warn_once("auth", "Camera screens need Home Assistant's URL and a token (ha_url / ha_token)")
            return None
        # Ask Home Assistant for a smaller image (it scales on its side), a few times the matrix size.
        request = urllib.request.Request(
            f"{self.url}/api/camera_proxy/{camera}?width={width * 4}&height={height * 4}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=float(screen.get("timeout", 3))) as r:
                data = r.read()
            pixels = render_image(data, width, height, fit, screen)
        except Exception as err:  # network, HTTP or decode errors: show the last good frame
            self.warn_once(f"fetch:{camera}", f"{camera}: can't fetch the camera image: {err}")
            return cached[1] if cached else None
        self.warned.discard(f"fetch:{camera}")
        self.cache[key] = (now, pixels)
        return pixels


def render_image(data, width, height, fit="crop", options=None):
    """Decode image bytes and scale them to width x height pixels, rows-first (r, g, b) tuples.

    fit: `crop` fills the matrix and cuts the sides off a wide picture; `letterbox` shows it all with black bars.
    Options: `autocontrast` (default true: stretch the levels so the darkest part is black and the brightest is
    full brightness; makes dim or night-time infrared pictures readable), `brightness` and `contrast` (1.0 =
    unchanged) and `gamma` (above 1 darkens the mid-tones; default 1.0).
    """
    options = options or {}
    img = Image.open(io.BytesIO(data))
    img.draft("RGB", (width * 2, height * 2))  # fast JPEG downscale while decoding
    img = img.convert("RGB")
    if fit == "letterbox":
        img = ImageOps.pad(img, (width, height), method=Image.LANCZOS, color=(0, 0, 0))
    else:
        img = ImageOps.fit(img, (width, height), method=Image.LANCZOS)
    if options.get("autocontrast", True):
        img = ImageOps.autocontrast(img, cutoff=1)
    if options.get("contrast", 1.0) != 1.0:
        img = ImageEnhance.Contrast(img).enhance(float(options["contrast"]))
    if options.get("brightness", 1.0) != 1.0:
        img = ImageEnhance.Brightness(img).enhance(float(options["brightness"]))
    gamma = float(options.get("gamma", 1.0))
    if gamma != 1.0:
        lut = [round(255 * (i / 255) ** gamma) for i in range(256)]
        img = img.point(lut * 3)
    return list(img.getdata())
