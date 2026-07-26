from __future__ import absolute_import


class ApiError(Exception):
    def __init__(self, code, message, status_code=400, details=None):
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class PaginationParams(object):
    def __init__(self, limit, offset):
        self.limit = limit
        self.offset = offset


def parse_json_body(request, allow_empty=True):
    if not request.data:
        if allow_empty:
            return {}
        raise ApiError("invalid_json", "请求体不能为空", status_code=400)

    try:
        payload = request.get_json(force=False, silent=False)
    except Exception:
        raise ApiError("invalid_json", "请求体必须是合法 JSON", status_code=400)

    if payload is None:
        if allow_empty:
            return {}
        raise ApiError("invalid_json", "请求体不能为空", status_code=400)

    if not isinstance(payload, dict):
        raise ApiError("invalid_json", "请求体必须是 JSON 对象", status_code=400)

    return payload


def parse_pagination(request, default_limit=100, max_limit=200):
    raw_limit = request.args.get("limit", default_limit)
    raw_offset = request.args.get("offset", 0)

    try:
        limit = int(raw_limit)
    except Exception:
        raise ApiError("invalid_limit", "limit 必须是整数", status_code=400)

    try:
        offset = int(raw_offset)
    except Exception:
        raise ApiError("invalid_offset", "offset 必须是整数", status_code=400)

    if limit < 1:
        raise ApiError("invalid_limit", "limit 必须大于 0", status_code=400)
    if limit > max_limit:
        raise ApiError(
            "invalid_limit",
            "limit 不能超过 {0}".format(max_limit),
            status_code=400,
            details={"max_limit": max_limit},
        )
    if offset < 0:
        raise ApiError("invalid_offset", "offset 不能小于 0", status_code=400)

    return PaginationParams(limit=limit, offset=offset)


def require_fields(payload, field_names):
    missing = []
    for field_name in field_names:
        value = payload.get(field_name)
        if value is None:
            missing.append(field_name)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field_name)

    if missing:
        raise ApiError(
            "missing_required_fields",
            "缺少必填字段: {0}".format(", ".join(missing)),
            status_code=400,
            details={"fields": missing},
        )


def api_success(data=None, message=None, status_code=200, details=None):
    response = {
        "success": True,
        "data": data,
        "error": None,
        "message": message,
        "details": details,
    }
    return response, status_code


def api_error(code, message, status_code=400, details=None):
    response = {
        "success": False,
        "data": None,
        "error": code,
        "message": message,
        "details": details,
    }
    return response, status_code
