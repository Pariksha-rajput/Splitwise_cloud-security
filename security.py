import logging
import json
import os
from datetime import datetime
from collections import defaultdict
from threading import Lock
from time import time

# ── Structured Security Logger ────────────────────────────────────────────────
# Logs flow to stdout → AKS container logs → Log Analytics → Azure Monitor alerts
security_logger = logging.getLogger("fairsplit.security")
security_logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
if not security_logger.handlers:
    security_logger.addHandler(handler)

# ── Config ────────────────────────────────────────────────────────────────────
FAILED_LOGIN_THRESHOLD = 3      # block after 3 failures
FAILED_LOGIN_WINDOW    = 300    # within 5 minutes
SCANNING_THRESHOLD     = 10     # unauthorized hits before flagging
SCANNING_WINDOW        = 60     # within 1 minute
SUSPICIOUS_AMOUNT      = 5000   # flag payments above $5000

# Azure: alerts are triggered by Azure Monitor querying Log Analytics
# No SDK needed — structured JSON to stdout is picked up by the OMS agent

# ── In-memory trackers (thread-safe) ─────────────────────────────────────────
failed_logins = defaultdict(list)
route_scans   = defaultdict(list)
_lock         = Lock()

# ── Core logging function ─────────────────────────────────────────────────────

def log_security_event(event_type, details, severity="WARNING", notify=False):
    """Log structured JSON security event. Flows to Azure Log Analytics via OMS agent."""
    event = {
        "timestamp":  datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "service":    "fairsplit",
        "event_type": event_type,
        "severity":   severity,
        "details":    details,
    }
    msg = json.dumps(event)

    if severity == "CRITICAL":
        security_logger.critical(msg)
    else:
        security_logger.warning(msg)
    # Azure Monitor scheduled query alerts pick up CRITICAL events from Log Analytics
    # No explicit notify call needed — alerts are wired in Terraform (main.tf)


# ── Scenario 1: Brute Force Detection ────────────────────────────────────────

def record_failed_login(ip, email):
    """Track failed logins per IP. Returns True if brute force threshold hit."""
    now = time()
    with _lock:
        failed_logins[ip] = [t for t in failed_logins[ip] if now - t < FAILED_LOGIN_WINDOW]
        failed_logins[ip].append(now)
        count = len(failed_logins[ip])

    log_security_event("FAILED_LOGIN", {
        "ip":            ip,
        "email":         email,
        "attempt_count": count,
        "threshold":     FAILED_LOGIN_THRESHOLD,
    }, severity="WARNING")

    if count >= FAILED_LOGIN_THRESHOLD:
        log_security_event("BRUTE_FORCE_DETECTED", {
            "ip":                 ip,
            "email":              email,
            "attempts_in_window": count,
            "action":             "IP blocked from further login attempts",
        }, severity="CRITICAL", notify=True)
        return True
    return False


def is_ip_blocked(ip):
    """Returns True if IP has exceeded failed login threshold."""
    now = time()
    with _lock:
        attempts = [t for t in failed_logins[ip] if now - t < FAILED_LOGIN_WINDOW]
        return len(attempts) >= FAILED_LOGIN_THRESHOLD


def clear_failed_logins(ip):
    """Reset failed login count on successful login."""
    with _lock:
        failed_logins[ip] = []


# ── Scenario 2: Unauthorized Route Scanning ───────────────────────────────────

def record_unauthorized_access(ip, route, method):
    """Log unauthorized access. Flags scanning if too many hits in short window."""
    now = time()
    with _lock:
        route_scans[ip] = [t for t in route_scans[ip] if now - t < SCANNING_WINDOW]
        route_scans[ip].append(now)
        count = len(route_scans[ip])

    log_security_event("UNAUTHORIZED_ACCESS", {
        "ip":             ip,
        "route":          route,
        "method":         method,
        "hits_in_window": count,
    }, severity="WARNING")

    if count >= SCANNING_THRESHOLD:
        log_security_event("SCANNING_DETECTED", {
            "ip":             ip,
            "hits_in_window": count,
            "action":         "Possible automated route scanning detected",
        }, severity="CRITICAL", notify=True)


# ── Scenario 2b: IDOR — Unauthorized Expense Settlement ───────────────────────

def log_idor_attempt(user_id, email, expense_id, ip):
    """Log an IDOR attempt where a user tries to settle an expense they are not party to."""
    log_security_event("IDOR_ATTEMPT_DETECTED", {
        "user_id":    user_id,
        "email":      email,
        "expense_id": expense_id,
        "ip":         ip,
        "action":     "Blocked — user is not a member of this expense",
    }, severity="CRITICAL")


# ── Scenario 3: Suspicious Transaction ───────────────────────────────────────

def check_suspicious_payment(user_id, amount, to_user):
    """Flag and block payments exceeding $5000."""
    if amount >= SUSPICIOUS_AMOUNT:
        log_security_event("SUSPICIOUS_TRANSACTION", {
            "user_id":   user_id,
            "to_user":   to_user,
            "amount":    amount,
            "threshold": SUSPICIOUS_AMOUNT,
            "action":    "Transaction blocked — exceeds limit",
        }, severity="CRITICAL", notify=True)
        return True
    return False
