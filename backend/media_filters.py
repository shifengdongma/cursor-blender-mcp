# -*- coding: utf-8 -*-
"""Whitelisted, range-checked video filter parameters for FFmpeg."""
from __future__ import absolute_import

import math

from .http_utils import ApiError

ALLOWED_FILTERS = {
    "brightness", "contrast", "saturation", "gamma", "exposure",
    "sharpen", "blur", "hue", "crop", "scale", "fps", "denoise",
}
DENOISE_MODES = {"weak", "medium", "strong"}


def _number(filters, key, minimum, maximum):
    if key not in filters or filters[key] is None:
        return None
    try:
        value = float(filters[key])
    except (TypeError, ValueError):
        raise ApiError("invalid_filters", "{0} 必须是数字".format(key), status_code=400)
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ApiError(
            "invalid_filters",
            "{0} 需在 {1}–{2} 之间".format(key, minimum, maximum),
            status_code=400,
        )
    return value


def _pair(filters, key, width_max=4096, allow_zero=True):
    value = filters.get(key)
    if value is None:
        return None
    if isinstance(value, dict):
        if key == "crop":
            raw = (value.get("w"), value.get("h"), value.get("x", 0), value.get("y", 0))
        else:
            raw = (value.get("width"), value.get("height"))
    elif isinstance(value, (list, tuple)):
        raw = tuple(value)
    else:
        raise ApiError("invalid_filters", "{0} 格式错误".format(key), status_code=400)
    try:
        numbers = tuple(int(item) for item in raw)
    except (TypeError, ValueError):
        raise ApiError("invalid_filters", "{0} 必须是整数".format(key), status_code=400)
    expected = 4 if key == "crop" else 2
    if len(numbers) != expected:
        raise ApiError("invalid_filters", "{0} 参数数量错误".format(key), status_code=400)
    minimum = 0 if allow_zero else 1
    for number in numbers:
        if number < minimum or number > width_max:
            raise ApiError(
                "invalid_filters",
                "{0} 参数超出范围".format(key),
                status_code=400,
            )
    if key == "crop":
        width, height, x, y = numbers
        if width <= 0 or height <= 0 or x < 0 or y < 0:
            raise ApiError("invalid_filters", "裁切参数无效", status_code=400)
    else:
        width, height = numbers
        if width <= 0 or height <= 0:
            raise ApiError("invalid_filters", "缩放参数无效", status_code=400)
    return numbers


def validate_filters(filters):
    """Return a normalised filter dict or raise an ApiError."""
    if not isinstance(filters, dict) or not filters:
        raise ApiError("empty_filters", "请至少选择一个画面参数", status_code=400)
    unknown = [key for key in filters if key not in ALLOWED_FILTERS]
    if unknown:
        raise ApiError(
            "unsupported_filter",
            "不支持的滤镜参数：{0}".format(", ".join(sorted(unknown))),
            status_code=400,
            details={"supported": sorted(ALLOWED_FILTERS)},
        )
    result = {}
    for key, bounds in (
        ("brightness", (-1.0, 1.0)),
        ("contrast", (0.0, 3.0)),
        ("saturation", (0.0, 3.0)),
        ("gamma", (0.1, 10.0)),
        ("exposure", (-2.0, 2.0)),
        ("sharpen", (0.0, 5.0)),
        ("blur", (0.0, 10.0)),
        ("hue", (-180.0, 180.0)),
    ):
        value = _number(filters, key, bounds[0], bounds[1])
        if value is not None:
            result[key] = value
    if filters.get("crop") is not None:
        result["crop"] = _pair(filters, "crop")
    if filters.get("scale") is not None:
        result["scale"] = _pair(filters, "scale", width_max=8192)
    if filters.get("fps") is not None:
        try:
            fps = int(filters["fps"])
        except (TypeError, ValueError):
            raise ApiError("invalid_filters", "fps 必须是整数", status_code=400)
        if fps < 1 or fps > 60:
            raise ApiError("invalid_filters", "fps 需在 1–60 之间", status_code=400)
        result["fps"] = fps
    if filters.get("denoise") is not None:
        if filters["denoise"] not in DENOISE_MODES:
            raise ApiError("invalid_filters", "降噪等级无效", status_code=400)
        result["denoise"] = filters["denoise"]
    if not result:
        raise ApiError("empty_filters", "请至少选择一个画面参数", status_code=400)
    return result


def build_filter_parts(filters):
    """Build deterministic FFmpeg filter expressions from validated values."""
    filters = validate_filters(filters)
    parts = []
    if filters.get("crop"):
        width, height, x, y = filters["crop"]
        parts.append("crop={0}:{1}:{2}:{3}".format(width, height, x, y))
    if filters.get("scale"):
        width, height = filters["scale"]
        parts.append("scale={0}:{1}".format(width, height))
    eq_parts = []
    if filters.get("brightness") is not None or filters.get("exposure") is not None:
        # FFmpeg's eq brightness is the stable mapping for both controls.
        brightness = float(filters.get("brightness") or 0.0)
        brightness += float(filters.get("exposure") or 0.0) * 0.1
        eq_parts.append("brightness={0:.5f}".format(max(-1.0, min(1.0, brightness))))
    if filters.get("contrast") is not None:
        eq_parts.append("contrast={0:.5f}".format(filters["contrast"]))
    if filters.get("saturation") is not None:
        eq_parts.append("saturation={0:.5f}".format(filters["saturation"]))
    if filters.get("gamma") is not None:
        eq_parts.append("gamma={0:.5f}".format(filters["gamma"]))
    if eq_parts:
        parts.append("eq={0}".format(":".join(eq_parts)))
    if filters.get("hue") is not None and abs(filters["hue"]) > 1e-9:
        parts.append("hue=h={0:.4f}".format(filters["hue"]))
    if filters.get("blur") is not None and filters["blur"] > 0:
        parts.append("gblur=sigma={0:.4f}".format(filters["blur"]))
    if filters.get("sharpen") is not None and filters["sharpen"] > 0:
        parts.append("unsharp=5:5:{0:.4f}:5:5:0".format(filters["sharpen"]))
    if filters.get("denoise"):
        denoise_map = {
            "weak": "hqdn3d=2:2:3:3",
            "medium": "hqdn3d=4:4:5:5",
            "strong": "hqdn3d=6:6:7:7",
        }
        parts.append(denoise_map[filters["denoise"]])
    if filters.get("fps"):
        parts.append("fps={0}".format(filters["fps"]))
    return parts
