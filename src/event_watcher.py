"""
Proactive Event Watcher — Background thread that monitors the K8s cluster
for anomalies and creates alerts for the frontend.

Key features:
  - Watches K8s Warning events via the Watch API
  - Tracks pod restart spikes and state transitions
  - Deduplicates alerts by resource + reason
  - Auto-resolves alerts when pods become healthy
"""

import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import List, Optional, Dict

from kubernetes import watch


# ── Severity Classification ─────────────────────────────────────

CRITICAL_REASONS = {
    "OOMKilling", "OOMKilled", "BackOff", "CrashLoopBackOff",
    "FailedScheduling", "Evicted", "Preempting",
    "NodeNotReady", "NodeOutOfDisk",
}

WARNING_REASONS = {
    "Unhealthy", "FailedMount", "FailedAttachVolume",
    "Failed", "ImagePullBackOff", "ErrImagePull",
    "CreateContainerConfigError", "InvalidImageName",
    "FailedCreate", "FailedKillPod",
    "ProbeWarning", "ReadinessGateFailed",
}

# Reasons we don't alert on (too noisy)
IGNORED_REASONS = {
    "Scheduled", "Pulling", "Pulled", "Created", "Started",
    "SuccessfulCreate", "ScalingReplicaSet",
    "SuccessfulDelete", "Killing",
}


class Alert:
    """A single alert representing a detected anomaly."""

    def __init__(
        self,
        severity: str,
        title: str,
        message: str,
        resource_kind: str,
        resource_name: str,
        namespace: str,
        event_reason: str = "",
    ):
        self.id = uuid.uuid4().hex[:10]
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.severity = severity          # "critical" | "warning" | "info"
        self.title = title
        self.message = message
        self.resource_kind = resource_kind
        self.resource_name = resource_name
        self.namespace = namespace
        self.event_reason = event_reason
        self.count = 1                    # how many times this recurred
        self.dismissed = False
        self.resolved = False
        self.resolved_at: Optional[str] = None

    @property
    def dedup_key(self) -> str:
        """Key used to group recurring alerts about the same issue."""
        return f"{self.namespace}/{self.resource_kind}/{self.resource_name}/{self.event_reason}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "resource_kind": self.resource_kind,
            "resource_name": self.resource_name,
            "namespace": self.namespace,
            "event_reason": self.event_reason,
            "count": self.count,
            "dismissed": self.dismissed,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
        }


class EventWatcher:
    """
    Background watcher that monitors K8s events and produces alerts.

    Usage:
        watcher = EventWatcher(core_v1_api)
        watcher.start()
        ...
        alerts = watcher.get_alerts()
    """

    def __init__(self, core_v1_api, apps_v1_api=None, max_alerts: int = 200):
        self.v1 = core_v1_api
        self.apps_v1 = apps_v1_api
        self._alerts: deque = deque(maxlen=max_alerts)
        self._alert_index: Dict[str, Alert] = {}   # dedup_key → Alert
        self._lock = threading.Lock()
        self._running = False
        self._watch_thread: Optional[threading.Thread] = None
        self._health_thread: Optional[threading.Thread] = None
        self._seen_uids: deque = deque(maxlen=5000)  # event dedup

    # ── Public API ───────────────────────────────────────────────

    def start(self):
        """Start the watcher threads."""
        if self._running:
            return
        self._running = True

        # Thread 1: Watch K8s events in real-time
        self._watch_thread = threading.Thread(
            target=self._event_watch_loop, daemon=True, name="event-watcher"
        )
        self._watch_thread.start()

        # Thread 2: Periodic pod health check for auto-resolve + restart spikes
        self._health_thread = threading.Thread(
            target=self._health_check_loop, daemon=True, name="health-checker"
        )
        self._health_thread.start()

        print("[EventWatcher] Started — watching for cluster anomalies")

    def stop(self):
        """Stop the watcher threads."""
        self._running = False
        print("[EventWatcher] Stopped")

    def get_alerts(self, include_dismissed: bool = False) -> List[dict]:
        """Return current alerts as dicts, newest first."""
        with self._lock:
            alerts = list(self._alerts)
        if not include_dismissed:
            alerts = [a for a in alerts if not a.dismissed]
        return [a.to_dict() for a in alerts]

    def get_active_count(self) -> int:
        """Return count of non-dismissed, non-resolved alerts."""
        with self._lock:
            return sum(
                1 for a in self._alerts
                if not a.dismissed and not a.resolved
            )

    def dismiss_alert(self, alert_id: str) -> bool:
        """Dismiss a single alert by ID."""
        with self._lock:
            for a in self._alerts:
                if a.id == alert_id:
                    a.dismissed = True
                    return True
        return False

    def dismiss_all(self):
        """Dismiss all alerts."""
        with self._lock:
            for a in self._alerts:
                a.dismissed = True

    # ── Background: Event Watch Loop ─────────────────────────────

    def _event_watch_loop(self):
        """Stream K8s events and create alerts for anomalies."""
        while self._running:
            try:
                w = watch.Watch()
                stream = w.stream(
                    self.v1.list_event_for_all_namespaces,
                    timeout_seconds=300,
                )
                for event in stream:
                    if not self._running:
                        break
                    try:
                        self._process_event(event)
                    except Exception as e:
                        print(f"[EventWatcher] Error processing event: {e}")
            except Exception as e:
                if self._running:
                    print(f"[EventWatcher] Watch connection lost: {e}")
                    time.sleep(5)  # backoff before reconnect

    def _process_event(self, event: dict):
        """Evaluate a single K8s event and create/update alerts as needed."""
        obj = event.get("object")
        if not obj:
            return

        # Only care about Warning events
        if getattr(obj, "type", "Normal") != "Warning":
            return

        reason = getattr(obj, "reason", "") or ""
        message = getattr(obj, "message", "") or ""

        # Skip noisy/routine events
        if reason in IGNORED_REASONS:
            return

        # Dedup by event UID + resourceVersion
        uid = getattr(obj.metadata, "uid", "")
        rv = getattr(obj.metadata, "resource_version", "")
        event_key = f"{uid}-{rv}"
        if event_key in self._seen_uids:
            return
        self._seen_uids.append(event_key)

        # Extract involved resource info
        involved = getattr(obj, "involved_object", None)
        if not involved:
            return

        resource_kind = getattr(involved, "kind", "Unknown")
        resource_name = getattr(involved, "name", "unknown")
        namespace = getattr(involved, "namespace", "") or "cluster"

        # Classify severity
        if reason in CRITICAL_REASONS:
            severity = "critical"
        elif reason in WARNING_REASONS:
            severity = "warning"
        else:
            severity = "info"

        title = f"{reason}: {resource_name}"
        self._add_or_update_alert(
            severity=severity,
            title=title,
            message=message[:500],
            resource_kind=resource_kind,
            resource_name=resource_name,
            namespace=namespace,
            event_reason=reason,
        )

    # ── Background: Health Check Loop ────────────────────────────

    def _health_check_loop(self):
        """
        Periodically check pod health to:
         1. Auto-resolve alerts when pods recover
         2. Detect restart spikes that events might miss
        """
        # Wait for initial cluster data before starting checks
        time.sleep(15)

        previous_restarts: Dict[str, int] = {}

        while self._running:
            try:
                pods = self.v1.list_pod_for_all_namespaces()
                healthy_pods = set()

                for pod in pods.items:
                    pod_name = pod.metadata.name
                    namespace = pod.metadata.namespace
                    pod_key = f"{namespace}/{pod_name}"

                    # Check if pod is healthy
                    is_healthy = pod.status.phase == "Running"
                    for cs in (pod.status.container_statuses or []):
                        if not cs.ready:
                            is_healthy = False

                    if is_healthy:
                        healthy_pods.add(pod_key)

                    # Detect restart spikes
                    total_restarts = sum(
                        cs.restart_count
                        for cs in (pod.status.container_statuses or [])
                    )
                    prev = previous_restarts.get(pod_key, total_restarts)
                    restart_delta = total_restarts - prev
                    previous_restarts[pod_key] = total_restarts

                    if restart_delta >= 3:
                        self._add_or_update_alert(
                            severity="critical",
                            title=f"Restart Spike: {pod_name}",
                            message=f"Pod restarted {restart_delta} times in the last check interval (total: {total_restarts}).",
                            resource_kind="Pod",
                            resource_name=pod_name,
                            namespace=namespace,
                            event_reason="RestartSpike",
                        )

                # Auto-resolve alerts for pods that are now healthy OR no longer exist
                # (pods get replaced with new names when a Deployment is patched)
                active_pod_keys = {
                    f"{p.metadata.namespace}/{p.metadata.name}"
                    for p in pods.items
                }
                self._auto_resolve(healthy_pods, active_pod_keys)

                # Prune restart tracking for pods that no longer exist
                for key in list(previous_restarts.keys()):
                    if key not in active_pod_keys:
                        del previous_restarts[key]

            except Exception as e:
                print(f"[EventWatcher] Health check error: {e}")

            # Check every 15 seconds
            for _ in range(15):
                if not self._running:
                    return
                time.sleep(1)

    # ── Alert Management ─────────────────────────────────────────

    def _add_or_update_alert(
        self,
        severity: str,
        title: str,
        message: str,
        resource_kind: str,
        resource_name: str,
        namespace: str,
        event_reason: str,
    ):
        """
        Add a new alert or update an existing one (dedup by resource+reason).
        If the same resource+reason fires again, increment the count.
        """
        temp = Alert(
            severity=severity,
            title=title,
            message=message,
            resource_kind=resource_kind,
            resource_name=resource_name,
            namespace=namespace,
            event_reason=event_reason,
        )
        dedup_key = temp.dedup_key

        with self._lock:
            existing = self._alert_index.get(dedup_key)

            if existing and not existing.dismissed:
                # Update existing alert
                existing.count += 1
                existing.updated_at = datetime.now(timezone.utc).isoformat()
                existing.message = message  # latest message
                existing.severity = severity  # could escalate
                if existing.resolved:
                    # Issue recurred after resolution
                    existing.resolved = False
                    existing.resolved_at = None
            else:
                # New alert
                self._alerts.appendleft(temp)
                self._alert_index[dedup_key] = temp

                # Clean up stale index entries
                if len(self._alert_index) > 300:
                    active_keys = {a.dedup_key for a in self._alerts}
                    for k in list(self._alert_index.keys()):
                        if k not in active_keys:
                            del self._alert_index[k]

    def _auto_resolve(self, healthy_pod_keys: set, active_pod_keys: set):
        """
        Mark alerts as resolved if their associated pod is now healthy
        OR if the pod no longer exists (was replaced after a fix).
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            for alert in self._alerts:
                if alert.dismissed or alert.resolved:
                    continue
                if alert.resource_kind != "Pod":
                    continue

                pod_key = f"{alert.namespace}/{alert.resource_name}"

                # Resolve if: pod is healthy OR pod was replaced (no longer exists)
                if pod_key in healthy_pod_keys or pod_key not in active_pod_keys:
                    alert.resolved = True
                    alert.resolved_at = now
