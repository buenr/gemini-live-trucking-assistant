"""Mock driver, route, hours, pay, and dispatch state with tool-callable helpers.

These functions back Gemini function-calling for the demo: snapshots, ETA/load updates,
hometime requests, fuel stops, compliance summaries, dispatch messages, outbound
notes to Driver Leader / CSR, and operations contact numbers for human escalation—all
against in-memory data, not a live fleet system.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import logging
import os
import re
import uuid

logger = logging.getLogger(__name__)

DRIVER_PROFILE: dict[str, Any] = {
    "driver_id": "482211",
    "name": "Jordan Biles",
    "truck_number": "123214",
    "fleet": "Linehaul",
}


ROUTE_STATE: dict[str, Any] = {
    "load_id": "ABC9017",
    "shipper": "Acme Linehaul — Memphis, TN",
    "receiver": "Southwest Foods DC — Dallas, TX",
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

# Assigned DL / CSR for outbound tools (mock — would come from fleet/TMS per driver).
# Optional env overrides: DRIVER_LEADER_PHONE, CSR_PHONE (digits or formatted).
DRIVER_LEADER_CONTACT: dict[str, str] = {
    "name": "Taylor Nguyen",
    "code": "388421",
    "phone": "1-800-555-0101",
}
CSR_CONTACT: dict[str, str] = {
    "name": "Sam Okonkwo",
    "code": "451092",
    "phone": "1-800-555-0102",
}

# Company / department phones for human escalation when the assistant cannot answer (mock — replace per fleet).
_DEPARTMENT_ESCALATION: list[dict[str, str]] = [
    {
        "department": "Shop / Maintenance",
        "phone": "1-800-555-0110",
        "for": "Truck/trailer repairs, breakdowns, PMI scheduling, shop coordination.",
    },
    {
        "department": "Payroll",
        "phone": "1-800-555-0120",
        "for": "Paychecks, settlements, deductions, direct deposit, tax forms.",
    },
    {
        "department": "Driver Licensing & Qualifications",
        "phone": "1-800-555-0130",
        "for": "CDL/med card renewals, Clearinghouse, MVR, onboarding paperwork.",
    },
    {
        "department": "Safety",
        "phone": "1-800-555-0140",
        "for": "Safety policies, accidents/incidents (non-emergency), compliance questions.",
    },
    {
        "department": "Roadside / After-hours",
        "phone": "1-800-555-0150",
        "for": "Urgent roadside, lockouts, towing coordination when shop line is closed.",
    },
]


def _driver_leader_contact_resolved() -> dict[str, str]:
    d = dict(DRIVER_LEADER_CONTACT)
    override = (os.getenv("DRIVER_LEADER_PHONE") or "").strip()
    if override:
        d["phone"] = override
    return d


def _csr_contact_resolved() -> dict[str, str]:
    d = dict(CSR_CONTACT)
    override = (os.getenv("CSR_PHONE") or "").strip()
    if override:
        d["phone"] = override
    return d


def get_operations_contacts() -> dict[str, Any]:
    """Assigned DL/CSR (with phones) plus department numbers for escalation."""
    return {
        "driver_leader": _driver_leader_contact_resolved(),
        "csr": _csr_contact_resolved(),
        "departments": [dict(row) for row in _DEPARTMENT_ESCALATION],
        "usage": (
            "When the driver asks for a phone number, read it from this contacts object: "
            "driver_leader.phone, csr.phone, or departments[].phone as appropriate. "
            "Offer to repeat slowly. For load execution and dispatch questions, you may also offer "
            "to message Driver Leader or CSR via tools when appropriate."
        ),
    }


# Mock dispatch / fleet messages for the in-cab voice assistant
# Outbound notes to operations (mock queue — replace with TMS/Comms integration)
OUTBOUND_TO_DRIVER_LEADER: list[dict[str, Any]] = []
OUTBOUND_TO_CSR: list[dict[str, Any]] = []

DISPATCH_MESSAGES: list[dict[str, Any]] = [
    {
        "message_id": "MSG-001",
        "sent_at": "2026-03-28T14:30:00Z",
        "from": "Dispatch",
        "subject": "Appointment change",
        "body": "Load LD-99017 receiver moved appointment to 2026-03-29 08:00-10:00 local. Confirm when checked in.",
        "read": False,
        "priority": "high",
    },
    {
        "message_id": "MSG-002",
        "sent_at": "2026-03-28T11:00:00Z",
        "from": "Safety",
        "subject": "Pre-trip reminder",
        "body": "Reminder: complete DVIR before rolling. Reply if you need roadside assistance.",
        "read": False,
        "priority": "normal",
    },
    {
        "message_id": "MSG-003",
        "sent_at": "2026-03-27T18:45:00Z",
        "from": "Payroll",
        "subject": "Settlement note",
        "body": "Week ending 2026-03-23 settlement posted. Contact payroll for accessorial questions.",
        "read": True,
        "priority": "low",
    },
]


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _validate_iso_timestamp(value: str) -> None:
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", ""))


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


def _trip_execution_block() -> dict[str, Any]:
    eta_confidence_minutes = 20 if ROUTE_STATE["status"] == "in_transit" else 10
    return {
        "eta_confidence_minutes": eta_confidence_minutes,
        "delay_history": [ROUTE_STATE["last_check_call"]],
        "route_event_timeline": LOAD_UPDATES[-5:],
        "check_call_status": "current" if LOAD_UPDATES else "update_needed",
    }


def _deadline_from_appointment_window() -> datetime:
    """Parse end of delivery window from ROUTE_STATE so feasibility matches the displayed window."""
    raw = (ROUTE_STATE.get("appointment_window") or "").strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2})-(\d{2}):(\d{2})", raw)
    if m:
        ymd, eh, em = m.group(1), m.group(4), m.group(5)
        return datetime.fromisoformat(f"{ymd}T{int(eh):02d}:{int(em):02d}:00")
    m2 = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    if m2:
        return datetime.fromisoformat(f"{m2.group(1)}T23:59:00")
    eta = _parse_iso(ROUTE_STATE["eta_iso"])
    return eta + timedelta(hours=1)


def _appointment_feasibility(appointment_time_iso: str = "") -> dict[str, Any]:
    eta = _parse_iso(ROUTE_STATE["eta_iso"])
    if appointment_time_iso:
        appointment_time = _parse_iso(appointment_time_iso)
    else:
        appointment_time = _deadline_from_appointment_window()
    can_make = eta <= appointment_time and HOURS_STATE["drive_hours_left"] >= ROUTE_STATE["remaining_drive_time_hours"]
    return {
        "appointment_time_iso": appointment_time.replace(tzinfo=None).isoformat(),
        "can_make_appointment": can_make,
    }


def get_status(appointment_time_iso: str = "") -> dict[str, Any]:
    """Driver profile, route, trip execution extras (non-duplicative of route), and appointment feasibility."""
    return {
        "success": True,
        "driver": dict(DRIVER_PROFILE),
        "route": dict(ROUTE_STATE),
        "trip": _trip_execution_block(),
        "appointment": _appointment_feasibility(appointment_time_iso),
    }


def get_stop_plan(limit: int = 3) -> dict[str, Any]:
    """Hours/compliance summary plus suggested fuel stops along the route."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    drive_left = HOURS_STATE["drive_hours_left"]
    violation_risk = "at_risk" if HOURS_STATE["next_break_due_minutes"] <= 30 else "ok"
    hours = {
        "drive_hours_left": drive_left,
        "on_duty_window_left": HOURS_STATE["on_duty_window_left"],
        "cycle_hours_left": HOURS_STATE["cycle_hours_left"],
        "next_break_due_minutes": HOURS_STATE["next_break_due_minutes"],
        "violation_risk": violation_risk,
        "estimated_legal_stop": ROUTE_STATE["next_stop"],
        "appointment_risk": "high" if drive_left < ROUTE_STATE["remaining_drive_time_hours"] else "low",
    }
    return {
        "success": True,
        "hours": hours,
        "suggested_stops": FUEL_STOPS[:limit],
    }


def get_pay_and_settlement(week: str = "current") -> dict[str, Any]:
    """Weekly pay summary plus settlement breakdown (miles variance, accessorials, deductions)."""
    miles = PAY_STATE["miles_paid"]
    base_pay = round(miles * PAY_STATE["rate_per_mile_usd"], 2)
    gross = round(base_pay + PAY_STATE["accessorials_usd"], 2)
    net_estimate = round(gross - PAY_STATE["deductions_usd"], 2)
    miles_variance = round(PAY_STATE["dispatched_miles"] - PAY_STATE["miles_paid"], 1)
    accessorials = {
        "detention_usd": PAY_STATE["detention_usd"],
        "layover_usd": PAY_STATE["layover_usd"],
        "stop_pay_usd": PAY_STATE["stop_pay_usd"],
        "total_accessorials_usd": PAY_STATE["accessorials_usd"],
    }
    return {
        "success": True,
        "week": week,
        "miles_paid": miles,
        "dispatched_miles": PAY_STATE["dispatched_miles"],
        "miles_variance": miles_variance,
        "rate_per_mile_usd": PAY_STATE["rate_per_mile_usd"],
        "base_pay_usd": base_pay,
        "accessorials": accessorials,
        "accessorials_usd": PAY_STATE["accessorials_usd"],
        "deductions_usd": PAY_STATE["deductions_usd"],
        "estimated_net_usd": net_estimate,
        "last_settlement_id": PAY_STATE["last_settlement_id"],
        "last_settlement_status": PAY_STATE["last_settlement_status"],
        "next_settlement_date": PAY_STATE["next_settlement_date"],
        "exceptions": PAY_STATE["exceptions"],
    }


def update_eta(new_eta_iso: str, reason: str = "", stop_name: str = "") -> dict[str, Any]:
    _validate_iso_timestamp(new_eta_iso)
    previous_eta = ROUTE_STATE["eta_iso"]
    previous_stop = ROUTE_STATE["next_stop"]
    previous_check_call = ROUTE_STATE["last_check_call"]
    ROUTE_STATE["eta_iso"] = new_eta_iso
    if stop_name:
        ROUTE_STATE["next_stop"] = stop_name
    update_note = reason.strip() or "No reason provided"
    ROUTE_STATE["last_check_call"] = f"ETA updated: {update_note}"
    _record_change(
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
        "load_id": ROUTE_STATE["load_id"],
        "updated_eta_iso": ROUTE_STATE["eta_iso"],
        "next_stop": ROUTE_STATE["next_stop"],
        "update_reason": update_note,
        "last_check_call": ROUTE_STATE["last_check_call"],
        "updated_at": _now_iso(),
    }


def update_load_status(status: str, location: str = "", note: str = "") -> dict[str, Any]:
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
    _record_change(
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
        "load_id": ROUTE_STATE["load_id"],
        "check_call": entry,
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
    previous_count = len(HOMETIME_REQUESTS)
    HOMETIME_REQUESTS.append(request)
    _record_change(
        tool_call="submit_hometime_request",
        changes={
            "hometime_requests.count": {"before": previous_count, "after": len(HOMETIME_REQUESTS)},
            "hometime_requests.latest": {"before": None, "after": request},
        },
        metadata={"driver_id": DRIVER_PROFILE["driver_id"], "request_id": request_id},
    )
    return {
        "success": True,
        "request": request,
    }


def get_hometime_status(request_id: str = "") -> dict[str, Any]:
    if request_id:
        for req in HOMETIME_REQUESTS:
            if req["request_id"] == request_id:
                return {"success": True, "request": req}
        return {"success": False, "error_code": "NOT_FOUND", "request_id": request_id}
    latest = HOMETIME_REQUESTS[-1] if HOMETIME_REQUESTS else None
    if latest:
        return {"success": True, "request": latest}
    return {"success": False, "error_code": "NONE_ON_FILE"}


def _queue_team_message(
    recipient: str,
    notes_dictation: str,
    driver_id: str = "",
    load_id: str = "",
    subject: str = "",
) -> dict[str, Any]:
    if recipient not in ("driver_leader", "csr"):
        raise ValueError("Invalid recipient")
    body = (notes_dictation or "").strip()
    if not body:
        raise ValueError("notes_dictation is required")
    did = (driver_id or "").strip() or str(DRIVER_PROFILE["driver_id"])
    lid = (load_id or "").strip() or str(ROUTE_STATE.get("load_id") or "")
    subj = (subject or "").strip()
    prefix = "DL" if recipient == "driver_leader" else "CSR"
    message_id = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
    ts = _now_iso()
    contact = DRIVER_LEADER_CONTACT if recipient == "driver_leader" else CSR_CONTACT
    entry: dict[str, Any] = {
        "message_id": message_id,
        "recipient": recipient,
        "contact_name": contact["name"],
        "contact_code": contact["code"],
        "notes_dictation": body,
        "timestamp": ts,
        "driver_id": did,
        "load_id": lid,
        "subject": subj,
        "truck_number": str(DRIVER_PROFILE.get("truck_number") or ""),
        "current_location": str(ROUTE_STATE.get("current_location") or ""),
        "source": "voice_copilot",
        "status": "queued",
    }
    bucket = OUTBOUND_TO_DRIVER_LEADER if recipient == "driver_leader" else OUTBOUND_TO_CSR
    prev_count = len(bucket)
    bucket.append(entry)
    tool_name = (
        "send_message_to_driver_leader"
        if recipient == "driver_leader"
        else "send_message_to_csr"
    )
    _record_change(
        tool_call=tool_name,
        changes={
            f"outbound_{recipient}.count": {"before": prev_count, "after": len(bucket)},
            f"outbound_{recipient}.latest": {"before": None, "after": entry},
        },
        metadata={"message_id": message_id, "driver_id": did, "load_id": lid},
    )
    return {"success": True, "queued_message": entry}


def send_message_to_driver_leader(
    notes_dictation: str,
    driver_id: str = "",
    load_id: str = "",
    subject: str = "",
) -> dict[str, Any]:
    """Queue a note or dictated message to the driver's Driver Leader (mock)."""
    return _queue_team_message(
        "driver_leader", notes_dictation, driver_id, load_id, subject
    )


def send_message_to_csr(
    notes_dictation: str,
    driver_id: str = "",
    load_id: str = "",
    subject: str = "",
) -> dict[str, Any]:
    """Queue a note or dictated message to CSR / customer service (mock)."""
    return _queue_team_message("csr", notes_dictation, driver_id, load_id, subject)


def get_dispatch_messages(unread_only: bool | None = False, limit: int | None = 10) -> dict[str, Any]:
    """Return fleet/dispatch messages for the driver (mock data)."""
    unread_only = bool(unread_only) if unread_only is not None else False
    if limit is None or limit < 1:
        limit = 10
    msgs = list(DISPATCH_MESSAGES)
    if unread_only:
        msgs = [m for m in msgs if not m.get("read")]
    msgs = msgs[:limit]
    unread_count = sum(1 for m in DISPATCH_MESSAGES if not m.get("read"))
    return {
        "success": True,
        "messages": msgs,
        "unread_count": unread_count,
    }


def get_outbound_team_messages() -> dict[str, Any]:
    """Copies of queued outbound notes to Driver Leader and CSR (newest last in each list)."""
    return {
        "driver_leader": [dict(m) for m in OUTBOUND_TO_DRIVER_LEADER],
        "csr": [dict(m) for m in OUTBOUND_TO_CSR],
    }


def get_assigned_team_contacts() -> dict[str, Any]:
    """Assigned DL and CSR name, code, and phone (same resolution as snapshot contacts)."""
    return {
        "driver_leader": _driver_leader_contact_resolved(),
        "csr": _csr_contact_resolved(),
    }


def get_driver_snapshot(
    appointment_time_iso: str = "",
    fuel_stops_limit: int = 3,
    week: str = "current",
    hometime_request_id: str = "",
    dispatch_unread_only: bool = False,
    dispatch_limit: int = 10,
) -> dict[str, Any]:
    """Single call returning driver, route, trip, appointment, HOS/stops, pay, hometime, and dispatch."""
    status = get_status(appointment_time_iso)
    plan = get_stop_plan(fuel_stops_limit)
    pay_full = get_pay_and_settlement(week)
    hometime = get_hometime_status(hometime_request_id)
    dispatch = get_dispatch_messages(dispatch_unread_only, dispatch_limit)
    pay_body = {k: v for k, v in pay_full.items() if k != "success"}
    dispatch_body = {k: v for k, v in dispatch.items() if k != "success"}
    return {
        "success": True,
        "driver": status["driver"],
        "route": status["route"],
        "trip": status["trip"],
        "appointment": status["appointment"],
        "stop_plan": {
            "hours": plan["hours"],
            "suggested_stops": plan["suggested_stops"],
        },
        "pay": pay_body,
        "hometime": hometime,
        "dispatch": dispatch_body,
        "contacts": get_operations_contacts(),
    }
