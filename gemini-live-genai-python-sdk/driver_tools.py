from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid


DRIVER_PROFILE: dict[str, Any] = {
    "driver_id": "DRV-4821",
    "name": "Jordan Miles",
    "truck_number": "TX-214",
    "fleet": "Linehaul",
    "hours_left_today": 6.75,
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
    "rate_per_mile_usd": 0.68,
    "accessorials_usd": 145.00,
    "deductions_usd": 42.50,
    "last_settlement_id": "SET-2026-12",
}

HOMETIME_REQUESTS: list[dict[str, Any]] = []

LOAD_UPDATES: list[dict[str, Any]] = []

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


def get_driver_snapshot() -> dict[str, Any]:
    return {
        "driver": DRIVER_PROFILE,
        "route": ROUTE_STATE,
        "message": "Driver snapshot retrieved.",
    }


def get_route_info() -> dict[str, Any]:
    return {
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
    _validate_iso_timestamp(new_eta_iso)
    ROUTE_STATE["eta_iso"] = new_eta_iso
    if stop_name:
        ROUTE_STATE["next_stop"] = stop_name
    update_note = reason.strip() or "No reason provided"
    ROUTE_STATE["last_check_call"] = f"ETA updated: {update_note}"
    return {
        "load_id": ROUTE_STATE["load_id"],
        "updated_eta_iso": ROUTE_STATE["eta_iso"],
        "next_stop": ROUTE_STATE["next_stop"],
        "update_reason": update_note,
        "updated_at": _now_iso(),
        "message": "ETA update submitted.",
    }


def update_load_status(status: str, location: str = "", note: str = "") -> dict[str, Any]:
    allowed = {"arrived", "loaded", "in_transit", "at_receiver", "delivered", "delayed"}
    normalized = status.strip().lower()
    if normalized not in allowed:
        raise ValueError(f"Invalid status. Allowed: {', '.join(sorted(allowed))}")
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
    return {
        "load_id": ROUTE_STATE["load_id"],
        "check_call": entry,
        "message": "Load status updated.",
    }


def get_pay_info(week: str = "current") -> dict[str, Any]:
    miles = PAY_STATE["miles_paid"]
    base_pay = round(miles * PAY_STATE["rate_per_mile_usd"], 2)
    gross = round(base_pay + PAY_STATE["accessorials_usd"], 2)
    net_estimate = round(gross - PAY_STATE["deductions_usd"], 2)
    return {
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
    HOMETIME_REQUESTS.append(request)
    return {
        "request": request,
        "message": "Hometime request submitted.",
    }


def get_hometime_status(request_id: str = "") -> dict[str, Any]:
    if request_id:
        for req in HOMETIME_REQUESTS:
            if req["request_id"] == request_id:
                return {"request": req, "message": "Hometime request found."}
        return {"message": f"No hometime request found for id {request_id}."}
    latest = HOMETIME_REQUESTS[-1] if HOMETIME_REQUESTS else None
    if latest:
        return {"request": latest, "message": "Latest hometime request returned."}
    return {"message": "No hometime requests on file."}


def get_fuel_stops(limit: int = 3) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return {
        "current_location": ROUTE_STATE["current_location"],
        "suggested_stops": FUEL_STOPS[:limit],
        "message": "Fuel stop options retrieved.",
    }
