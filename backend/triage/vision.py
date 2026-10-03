"""Citizen photo handling: GDPR/RODO anonymization + Claude vision triage.

`anonymize` must run before a photo is stored anywhere: it applies the EXIF
orientation, drops every metadata block (EXIF/GPS, ICC, comments) by re-encoding
pixels only, and blurs faces and licence plates found by OpenCV Haar cascades.
`check_photo` asks Claude whether the photo shows the claimed problem; it never raises.
"""
from __future__ import annotations

import base64
import io
import logging
from functools import lru_cache
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from backend.models import IssueType
from backend.triage.structure import call_claude, llm_available

log = logging.getLogger(__name__)

DETECT_MAX_SIDE = 1280   # Haar detection runs on a downscaled copy (speed); boxes are scaled back
VISION_MAX_SIDE = 1568   # long side sent to Claude (keeps base64 well under the 5 MB image limit)
JPEG_QUALITY = 88


@lru_cache(maxsize=1)
def _cascades() -> list[Any]:
    """Face + plate Haar cascades shipped with opencv-python(-headless) 4.x.

    OpenCV 5 moved CascadeClassifier (and the XML files) to contrib: then this returns []
    and photos are only metadata-stripped, with a loud warning. Pin opencv-python-headless<5.
    """
    import cv2

    if not hasattr(cv2, "CascadeClassifier"):
        log.warning("OpenCV %s has no Haar cascades: faces/plates will NOT be blurred "
                    "(install opencv-python-headless<5)", cv2.__version__)
        return []
    out = []
    for name in ("haarcascade_frontalface_default.xml", "haarcascade_russian_plate_number.xml"):
        clf = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        if clf.empty():
            log.warning("Haar cascade %s not found", name)
        else:
            out.append(clf)
    return out


def blur_available() -> bool:
    """True when face/plate detection works (the API may refuse photos otherwise)."""
    try:
        return bool(_cascades())
    except Exception:
        return False


def _detect_regions(rgb: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Face/plate boxes (x, y, w, h) in full-resolution pixel coordinates."""
    import cv2

    cascades = _cascades()
    if not cascades:
        return []
    h, w = rgb.shape[:2]
    scale = min(1.0, DETECT_MAX_SIDE / max(h, w))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if scale < 1.0:
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.equalizeHist(gray)
    boxes = []
    for clf in cascades:
        for x, y, bw, bh in clf.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(20, 20)):
            boxes.append(tuple(int(round(v / scale)) for v in (x, y, bw, bh)))
    return boxes


def _blur(rgb: np.ndarray, boxes: list[tuple[int, int, int, int]]) -> np.ndarray:
    """Strong Gaussian blur over each box, padded by 15 %."""
    import cv2

    h, w = rgb.shape[:2]
    for x, y, bw, bh in boxes:
        px, py = int(bw * 0.15), int(bh * 0.15)
        x0, y0, x1, y1 = max(0, x - px), max(0, y - py), min(w, x + bw + px), min(h, y + bh + py)
        if x1 <= x0 or y1 <= y0:
            continue
        k = max(15, (max(x1 - x0, y1 - y0) // 2) | 1)  # odd kernel, scales with the region
        rgb[y0:y1, x0:x1] = cv2.GaussianBlur(rgb[y0:y1, x0:x1], (k, k), 0)
    return rgb


def _open_upright(image_bytes: bytes) -> Image.Image:
    """Decode, apply EXIF orientation, convert to plain RGB. Raises ValueError on non-images."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as exc:
        raise ValueError(f"not a readable image: {exc}") from exc
    return ImageOps.exif_transpose(img).convert("RGB")


def anonymize(image_bytes: bytes) -> bytes:
    """EXIF-free JPEG with faces and licence plates blurred.

    Raises ValueError if the bytes are not an image (the caller must then drop the photo).
    Detection problems only log a warning: metadata is still stripped.
    """
    img = _open_upright(image_bytes)
    rgb = np.array(img)  # pixels only: no EXIF/GPS/ICC/XMP survives
    try:
        boxes = _detect_regions(rgb)
        if boxes:
            rgb = _blur(rgb, boxes)
            log.info("anonymize: blurred %d face/plate region(s)", len(boxes))
    except Exception as exc:
        log.warning("anonymize: face/plate detection failed (%s); metadata stripped only", exc)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()


class _PhotoOut(BaseModel):
    category: IssueType
    severity: float = Field(ge=0.0, le=1.0)
    notes: str


VISION_PROMPT = """You check photos attached to citizen complaints for the Warsaw 19115 city hotline.
Classify what the photo shows: road_damage (pothole, broken asphalt or sidewalk), tram_track (damaged \
tram rails, switches or track bed), streetlight (broken or dark street lamp), flooding (water on the \
street, blocked drain, sewer or manhole problem), waste (rubbish, overflowing bins, illegal dumping), \
other (no city infrastructure problem visible, or something else).
severity: 0.0 = no visible problem, 0.5 = clear defect that needs a repair, 1.0 = severe and dangerous \
(deep hole on a road, missing manhole cover, large flooded area).
notes: one short English sentence about what is visible. Faces and plates may be blurred on purpose.
Return ONLY the JSON object."""


def _fallback(claimed: IssueType | None, notes: str = "vision unavailable") -> dict:
    return {"category": claimed or IssueType.OTHER, "severity": 0.5, "matches_claim": None, "notes": notes}


def _for_vision(image_bytes: bytes) -> str:
    """Upright, resized, EXIF-free JPEG as base64."""
    img = _open_upright(image_bytes)
    img.thumbnail((VISION_MAX_SIDE, VISION_MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def check_photo(image_bytes: bytes, claimed: IssueType | None = None) -> dict:
    """{"category", "severity" 0–1, "matches_claim" (None without a claim), "notes"}. Never raises."""
    try:
        claimed = IssueType(claimed) if claimed else None
    except ValueError:
        claimed = None
    if not llm_available():
        return _fallback(claimed)
    try:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": _for_vision(image_bytes)}},
            {"type": "text", "text": f"The citizen says the problem is: {claimed.value}." if claimed
             else "The citizen did not say what the problem is."},
        ]
        out = call_claude(VISION_PROMPT, content, schema=_PhotoOut, max_tokens=4096)
        return {
            "category": out.category,
            "severity": round(float(out.severity), 3),
            "matches_claim": (out.category == claimed) if claimed else None,
            "notes": out.notes,
        }
    except Exception as exc:
        log.warning("check_photo failed: %s", exc)
        return _fallback(claimed)
