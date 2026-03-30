from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import logging
import uuid

logger = logging.getLogger(__name__)

DRIVER_PROFILE: dict[str, Any] = {
    "driver_id": "DRV-4821",
    "name": "Jordan Miles",
    "truck_number": "TX-214",
    "fleet": "Linehaul",
    "hours_left_today": 6.75,
}

SIMULATION_STATE: dict[str, Any] = {
    "last_tick_iso": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
}

ROUTE_STATE: dict[str, Any] = {
    "load_id": "LD-99017",
    "origin": "Memphis, TN",
    "destination": "Dallas, TX",
    "current_location": "Little Rock, AR",
    "next_stop": "Texarkana Fuel Stop",
    "appointment_window": "2026-03-29 07:00-09:00 local",
    "remaining_miles": 312,
    "remaining_drive_time_hours": 5.9,
    "eta_iso": "2026-03-28T20:15:00",
    "last_check_call": "Rolling westbound I-30, on schedule.",
    "status": "in_transit",
}

PAY_STATE: dict[str, Any] = {
    "week": "current",
    "miles_paid": 1840,
    "dispatched_miles": 1980,
    "rate_per_mile_usd": 0.68,
    "detention_usd": 85.00,
    "layover_usd": 40.00,
    "stop_pay_usd": 20.00,
    "accessorials_usd": 145.00,
    "deductions_usd": 42.50,
    "last_settlement_id": "SET-2026-12",
    "last_settlement_status": "processing",
    "next_settlement_date": "2026-04-01",
    "exceptions": [],
}

HOURS_STATE: dict[str, Any] = {
    "drive_hours_left": 6.75,
    "on_duty_window_left": 8.25,
    "cycle_hours_left": 34.5,
    "next_break_due_minutes": 105,
}

HOMETIME_REQUESTS: list[dict[str, Any]] = []

LOAD_UPDATES: list[dict[str, Any]] = []
CHANGE_LOG: list[dict[str, Any]] = []

FUEL_STOPS: list[dict[str, Any]] = [
    {"name": "Love's - Texarkana", "distance_miles": 88, "parking": "high"},
    {"name": "Pilot - Mount Pleasant", "distance_miles": 126, "parking": "medium"},
    {"name": "TA - Terrell", "distance_miles": 205, "parking": "medium"},
    {"name": "Flying J - Dallas East", "distance_miles": 278, "parking": "low"},
]


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _validate_iso_timestamp(value: str) -> None:
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", ""))


def _apply_simulation_tick() -> None:
    now = datetime.utcnow().replace(microsecond=0)
    last = _parse_iso(SIMULATION_STATE["last_tick_iso"])
    elapsed_minutes = max(0, int((now - last).total_seconds() // 60))
    if elapsed_minutes == 0:
        return

    # Route simulation
    mph = 52
    miles_delta = round((mph / 60) * elapsed_minutes, 1)
    ROUTE_STATE["remaining_miles"] = max(0, round(ROUTE_STATE["remaining_miles"] - miles_delta, 1))
    ROUTE_STATE["remaining_drive_time_hours"] = max(
        0, round(ROUTE_STATE["remaining_drive_time_hours"] - (elapsed_minutes / 60), 2)
    )
    eta = _parse_iso(ROUTE_STATE["eta_iso"])
    ROUTE_STATE["eta_iso"] = (eta - timedelta(minutes=elapsed_minutes)).replace(tzinfo=None).isoformat()

    # Hours simulation
    HOURS_STATE["drive_hours_left"] = max(0, round(HOURS_STATE["drive_hours_left"] - (elapsed_minutes / 60), 2))
    HOURS_STATE["on_duty_window_left"] = max(
        0, round(HOURS_STATE["on_duty_window_left"] - (elapsed_minutes / 60), 2)
    )
    HOURS_STATE["cycle_hours_left"] = max(0, round(HOURS_STATE["cycle_hours_left"] - (elapsed_minutes / 60), 2))
    HOURS_STATE["next_break_due_minutes"] = max(0, HOURS_STATE["next_break_due_minutes"] - elapsed_minutes)

    # Pay simulation
    PAY_STATE["miles_paid"] = round(PAY_STATE["miles_paid"] + miles_delta, 1)
    if PAY_STATE["miles_paid"] > PAY_STATE["dispatched_miles"]:
        PAY_STATE["exceptions"] = ["Miles paid exceeded dispatched miles; verify dispatch feed."]
    else:
        PAY_STATE["exceptions"] = []

    SIMULATION_STATE["last_tick_iso"] = now.isoformat() + "Z"


def _record_change(tool_call: str, changes: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "log_id": f"LOG-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": _now_iso(),
        "tool_call": tool_call,
        "changes": changes,
        "metadata": metadata or {},
    }
    CHANGE_LOG.append(entry)
    logger.info("Driver data change logged: %s", entry)
    return entry


def get_driver_snapshot() -> dict[str, Any]:
    _apply_simulation_tick()
    return {
        "success": True,
        "action": "get_driver_snapshot",
        "driver": DRIVER_PROFILE,
        "route": ROUTE_STATE,
        "message": "Driver snapshot retrieved.",
    }


def get_route_info() -> dict[str, Any]:
    _apply_simulation_tick()
    return {
        "success": True,
        "action": "get_route_info",
        "load_id": ROUTE_STATE["load_id"],
        "origin": ROUTE_STATE["origin"],
        "destination": ROUTE_STATE["destination"],
        "current_location": ROUTE_STATE["current_location"],
        "next_stop": ROUTE_STATE["next_stop"],
        "appointment_window": ROUTE_STATE["appointment_window"],
        "remaining_miles": ROUTE_STATE["remaining_miles"],
        "remaining_drive_time_hours": ROUTE_STATE["remaining_drive_time_hours"],
        "eta_iso": ROUTE_STATE["eta_iso"],
        "status": ROUTE_STATE["status"],
        "message": "Current route information retrieved.",
    }


def update_eta(new_eta_iso: str, reason: str = "", stop_name: str = "") -> dict[str, Any]:
    _apply_simulation_tick()
    _validate_iso_timestamp(new_eta_iso)
    previous_eta = ROUTE_STATE["eta_iso"]
    previous_stop = ROUTE_STATE["next_stop"]
    previous_check_call = ROUTE_STATE["last_check_call"]
    ROUTE_STATE["eta_iso"] = new_eta_iso
    if stop_name:
        ROUTE_STATE["next_stop"] = stop_name
    update_note = reason.strip() or "No reason provided"
    ROUTE_STATE["last_check_call"] = f"ETA updated: {update_note}"
    log_entry = _record_change(
        tool_call="update_eta",
        changes={
            "route.eta_iso": {"before": previous_eta, "after": ROUTE_STATE["eta_iso"]},
            "route.next_stop": {"before": previous_stop, "after": ROUTE_STATE["next_stop"]},
            "route.last_check_call": {
                "before": previous_check_call,
                "after": ROUTE_STATE["last_check_call"],
            },
        },
        metadata={"load_id": ROUTE_STATE["load_id"], "reason": update_note},
    )
    return {
        "success": True,
        "action": "update_eta",
        "load_id": ROUTE_STATE["load_id"],
        "updated_eta_iso": ROUTE_STATE["eta_iso"],
        "next_stop": ROUTE_STATE["next_stop"],
        "update_reason": update_note,
        "updated_at": _now_iso(),
        "change_log": log_entry,
        "message": "ETA update submitted.",
    }


def update_load_status(status: str, location: str = "", note: str = "") -> dict[str, Any]:
    _apply_simulation_tick()
    allowed = {"arrived", "loaded", "in_transit", "at_receiver", "delivered", "delayed"}
    normalized = status.strip().lower()
    if normalized not in allowed:
        raise ValueError(f"Invalid status. Allowed: {', '.join(sorted(allowed))}")
    previous_status = ROUTE_STATE["status"]
    previous_location = ROUTE_STATE["current_location"]
    previous_check_call = ROUTE_STATE["last_check_call"]
    ROUTE_STATE["status"] = normalized
    if location:
        ROUTE_STATE["current_location"] = location
    if note:
        ROUTE_STATE["last_check_call"] = note
    entry = {
        "id": f"CHK-{uuid.uuid4().hex[:8]}",
        "status": normalized,
        "location": ROUTE_STATE["current_location"],
        "note": ROUTE_STATE["last_check_call"],
        "timestamp": _now_iso(),
    }
    LOAD_UPDATES.append(entry)
    log_entry = _record_change(
        tool_call="update_load_status",
        changes={
            "route.status": {"before": previous_status, "after": ROUTE_STATE["status"]},
            "route.current_location": {
                "before": previous_location,
                "after": ROUTE_STATE["current_location"],
            },
            "route.last_check_call": {
                "before": previous_check_call,
                "after": ROUTE_STATE["last_check_call"],
            },
            "load_updates.count": {"before": len(LOAD_UPDATES) - 1, "after": len(LOAD_UPDATES)},
        },
        metadata={"load_id": ROUTE_STATE["load_id"], "check_call_id": entry["id"]},
    )
    return {
        "success": True,
        "action": "update_load_status",
        "load_id": ROUTE_STATE["load_id"],
        "check_call": entry,
        "change_log": log_entry,
        "message": "Load status updated.",
    }


def get_pay_info(week: str = "current") -> dict[str, Any]:
    _apply_simulation_tick()
    miles = PAY_STATE["miles_paid"]
    base_pay = round(miles * PAY_STATE["rate_per_mile_usd"], 2)
    gross = round(base_pay + PAY_STATE["accessorials_usd"], 2)
    net_estimate = round(gross - PAY_STATE["deductions_usd"], 2)
    return {
        "success": True,
        "action": "get_pay_info",
        "week": week,
        "miles_paid": miles,
        "rate_per_mile_usd": PAY_STATE["rate_per_mile_usd"],
        "base_pay_usd": base_pay,
        "accessorials_usd": PAY_STATE["accessorials_usd"],
        "deductions_usd": PAY_STATE["deductions_usd"],
        "estimated_net_usd": net_estimate,
        "last_settlement_id": PAY_STATE["last_settlement_id"],
        "message": "Pay summary retrieved.",
    }


def submit_hometime_request(
    start_date: str, end_date: str, location: str, notes: str = ""
) -> dict[str, Any]:
    _apply_simulation_tick()
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    request_id = f"HT-{uuid.uuid4().hex[:8].upper()}"
    request = {
        "request_id": request_id,
        "driver_id": DRIVER_PROFILE["driver_id"],
        "start_date": start_date,
        "end_date": end_date,
        "location": location,
        "notes": notes,
        "status": "submitted",
        "submitted_at": _now_iso(),
    }
    previous_count = len(HOMETIME_REQUESTS)
    HOMETIME_REQUESTS.append(request)
    log_entry = _record_change(
        tool_call="submit_hometime_request",
        changes={
            "hometime_requests.count": {"before": previous_count, "after": len(HOMETIME_REQUESTS)},
            "hometime_requests.latest": {"before": None, "after": request},
        },
        metadata={"driver_id": DRIVER_PROFILE["driver_id"], "request_id": request_id},
    )
    return {
        "success": True,
        "action": "submit_hometime_request",
        "request": request,
        "change_log": log_entry,
        "message": "Hometime request submitted.",
    }


def get_hometime_status(request_id: str = "") -> dict[str, Any]:
    _apply_simulation_tick()
    if request_id:
        for req in HOMETIME_REQUESTS:
            if req["request_id"] == request_id:
                return {
                    "success": True,
                    "action": "get_hometime_status",
                    "request": req,
                    "message": "Hometime request found.",
                }
        return {
            "success": False,
            "action": "get_hometime_status",
            "message": f"No hometime request found for id {request_id}.",
        }
    latest = HOMETIME_REQUESTS[-1] if HOMETIME_REQUESTS else None
    if latest:
        return {
            "success": True,
            "action": "get_hometime_status",
            "request": latest,
            "message": "Latest hometime request returned.",
        }
    return {
        "success": False,
        "action": "get_hometime_status",
        "message": "No hometime requests on file.",
    }


def get_fuel_stops(limit: int = 3) -> dict[str, Any]:
    _apply_simulation_tick()
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return {
        "success": True,
        "action": "get_fuel_stops",
        "current_location": ROUTE_STATE["current_location"],
        "suggested_stops": FUEL_STOPS[:limit],
        "message": "Fuel stop options retrieved.",
    }


def get_change_log(limit: int = 20) -> dict[str, Any]:
    _apply_simulation_tick()
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return {
        "success": True,
        "action": "get_change_log",
        "entries": CHANGE_LOG[-limit:],
        "total_entries": len(CHANGE_LOG),
        "message": "Driver data change log retrieved.",
    }


def get_hours_compliance_summary() -> dict[str, Any]:
    _apply_simulation_tick()
    drive_left = HOURS_STATE["drive_hours_left"]
    appointment_risk = "high" if drive_left < ROUTE_STATE["remaining_drive_time_hours"] else "low"
    violation_risk = "at_risk" if HOURS_STATE["next_break_due_minutes"] <= 30 else "ok"
    return {
        "success": True,
        "action": "get_hours_compliance_summary",
        "drive_hours_left": drive_left,
        "on_duty_window_left": HOURS_STATE["on_duty_window_left"],
        "cycle_hours_left": HOURS_STATE["cycle_hours_left"],
        "next_break_due_minutes": HOURS_STATE["next_break_due_minutes"],
        "violation_risk": violation_risk,
        "estimated_legal_stop": ROUTE_STATE["next_stop"],
        "appointment_risk": appointment_risk,
        "message": "Hours and compliance summary retrieved.",
    }


def can_make_appointment(appointment_time_iso: str = "") -> dict[str, Any]:
    _apply_simulation_tick()
    eta = _parse_iso(ROUTE_STATE["eta_iso"])
    appointment_time = _parse_iso(appointment_time_iso) if appointment_time_iso else eta + timedelta(hours=1)
    can_make = eta <= appointment_time and HOURS_STATE["drive_hours_left"] >= ROUTE_STATE["remaining_drive_time_hours"]
    risk = "on_time" if can_make else "at_risk"
    return {
        "success": True,
        "action": "can_make_appointment",
        "eta_iso": ROUTE_STATE["eta_iso"],
        "appointment_time_iso": appointment_time.replace(tzinfo=None).isoformat(),
        "can_make_appointment": can_make,
        "risk": risk,
        "message": "Appointment feasibility evaluated.",
    }


def get_settlement_breakdown() -> dict[str, Any]:
    _apply_simulation_tick()
    miles_variance = round(PAY_STATE["dispatched_miles"] - PAY_STATE["miles_paid"], 1)
    accessorials = {
        "detention_usd": PAY_STATE["detention_usd"],
        "layover_usd": PAY_STATE["layover_usd"],
        "stop_pay_usd": PAY_STATE["stop_pay_usd"],
        "total_accessorials_usd": PAY_STATE["accessorials_usd"],
    }
    return {
        "success": True,
        "action": "get_settlement_breakdown",
        "miles_paid": PAY_STATE["miles_paid"],
        "dispatched_miles": PAY_STATE["dispatched_miles"],
        "miles_variance": miles_variance,
        "accessorials": accessorials,
        "deductions_usd": PAY_STATE["deductions_usd"],
        "last_settlement_status": PAY_STATE["last_settlement_status"],
        "next_settlement_date": PAY_STATE["next_settlement_date"],
        "exceptions": PAY_STATE["exceptions"],
        "message": "Settlement breakdown retrieved.",
    }


def get_trip_execution_status() -> dict[str, Any]:
    _apply_simulation_tick()
    eta_confidence_minutes = 20 if ROUTE_STATE["status"] == "in_transit" else 10
    appointment_risk = "late" if ROUTE_STATE["remaining_drive_time_hours"] > HOURS_STATE["drive_hours_left"] else "on_time"
    return {
        "success": True,
        "action": "get_trip_execution_status",
        "eta_iso": ROUTE_STATE["eta_iso"],
        "eta_confidence_minutes": eta_confidence_minutes,
        "remaining_miles": ROUTE_STATE["remaining_miles"],
        "remaining_drive_time_hours": ROUTE_STATE["remaining_drive_time_hours"],
        "appointment_risk": appointment_risk,
        "delay_history": [ROUTE_STATE["last_check_call"]],
        "route_event_timeline": LOAD_UPDATES[-5:],
        "check_call_status": "current" if LOAD_UPDATES else "update_needed",
        "message": "Trip execution status retrieved.",
    }
