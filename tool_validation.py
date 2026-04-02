"""Normalize and validate Gemini Live tool arguments before driver_tools invocation."""

from __future__ import annotations

from typing import Any


def _tool_error(error_code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "error_code": error_code, "message": message, **extra}


def _as_str(v: Any, key: str) -> tuple[str | None, dict[str, Any] | None]:
    if v is None:
        return None, _tool_error("INVALID_ARGUMENTS", f"Missing or null field: {key}")
    s = str(v).strip()
    if not s:
        return None, _tool_error("INVALID_ARGUMENTS", f"Empty string for field: {key}")
    return s, None


def _as_optional_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _as_int(v: Any, key: str, minimum: int | None = 1) -> tuple[int | None, dict[str, Any] | None]:
    if v is None:
        return None, _tool_error("INVALID_ARGUMENTS", f"Missing or null field: {key}")
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None, _tool_error("INVALID_ARGUMENTS", f"Field {key} must be an integer")
    if minimum is not None and n < minimum:
        return None, _tool_error("INVALID_ARGUMENTS", f"Field {key} must be >= {minimum}")
    return n, None


def _as_optional_int(v: Any, default: int, minimum: int = 1) -> tuple[int, dict[str, Any] | None]:
    if v is None or v == "":
        return default, None
    n, err = _as_int(v, "limit", minimum=minimum)
    if err:
        return default, err
    return n or default, None


def _as_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def validate_trucking_tool_args(name: str, args: Any) -> tuple[bool, dict[str, Any], dict[str, Any] | None]:
    """
    Returns (ok, normalized_args, error_payload).
    If not ok, error_payload is safe to send to the model as tool result.
    """
    if args is None:
        raw: dict[str, Any] = {}
    elif isinstance(args, dict):
        raw = dict(args)
    else:
        return False, {}, _tool_error("INVALID_ARGUMENTS", "Tool arguments must be an object")

    if name == "get_driver_snapshot":
        iso = raw.get("appointment_time_iso")
        if iso is None or str(iso).strip() == "":
            appointment_time_iso = ""
        else:
            s, err = _as_str(iso, "appointment_time_iso")
            if err:
                return False, {}, err
            appointment_time_iso = s
        fuel_limit, err = _as_optional_int(raw.get("fuel_stops_limit"), 3, minimum=1)
        if err:
            return False, {}, err
        week = _as_optional_str(raw.get("week")) or "current"
        hid = raw.get("hometime_request_id")
        if hid is None or str(hid).strip() == "":
            hometime_request_id = ""
        else:
            hs, herr = _as_str(hid, "hometime_request_id")
            if herr:
                return False, {}, herr
            hometime_request_id = hs
        dispatch_unread = _as_bool(raw.get("dispatch_unread_only"), False)
        dispatch_limit, derr = _as_optional_int(raw.get("dispatch_limit"), 10, minimum=1)
        if derr:
            return False, {}, derr
        return True, {
            "appointment_time_iso": appointment_time_iso,
            "fuel_stops_limit": fuel_limit,
            "week": week,
            "hometime_request_id": hometime_request_id,
            "dispatch_unread_only": dispatch_unread,
            "dispatch_limit": dispatch_limit,
        }, None

    if name == "update_eta":
        eta, err = _as_str(raw.get("new_eta_iso"), "new_eta_iso")
        if err:
            return False, {}, err
        return True, {
            "new_eta_iso": eta,
            "reason": _as_optional_str(raw.get("reason")),
            "stop_name": _as_optional_str(raw.get("stop_name")),
        }, None

    if name == "update_load_status":
        st, err = _as_str(raw.get("status"), "status")
        if err:
            return False, {}, err
        return True, {
            "status": st,
            "location": _as_optional_str(raw.get("location")),
            "note": _as_optional_str(raw.get("note")),
        }, None

    if name == "submit_hometime_request":
        sd, e1 = _as_str(raw.get("start_date"), "start_date")
        if e1:
            return False, {}, e1
        ed, e2 = _as_str(raw.get("end_date"), "end_date")
        if e2:
            return False, {}, e2
        loc, e3 = _as_str(raw.get("location"), "location")
        if e3:
            return False, {}, e3
        return True, {
            "start_date": sd,
            "end_date": ed,
            "location": loc,
            "notes": _as_optional_str(raw.get("notes")),
        }, None

    if name in ("send_message_to_driver_leader", "send_message_to_csr"):
        nd, err = _as_str(raw.get("notes_dictation"), "notes_dictation")
        if err:
            return False, {}, err
        return True, {
            "notes_dictation": nd,
            "driver_id": _as_optional_str(raw.get("driver_id")),
            "load_id": _as_optional_str(raw.get("load_id")),
            "subject": _as_optional_str(raw.get("subject")),
        }, None

    # Unknown tool names should be rejected before validation (see gemini_live).
    return False, {}, _tool_error("INTERNAL_ERROR", f"No argument schema for tool: {name}")
