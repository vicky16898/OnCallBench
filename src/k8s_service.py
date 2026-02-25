import json
from kubernetes import client, config
from typing import List, Optional, Dict, Any
from schemas import PodStatus

# Initialize K8s clients (moved from api.py)
K8S_MODE = "kubeconfig"
try:
    config.load_kube_config()
except Exception:
    try:
        config.load_incluster_config()
        K8S_MODE = "in-cluster"
    except Exception:
        K8S_MODE = "error"
        print("Warning: Could not load K8s config. Ensure you are in a K8s context.")

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
networking_v1 = client.NetworkingV1Api()

def get_namespaces_logic():
    ns_list = v1.list_namespace()
    return [ns.metadata.name for ns in ns_list.items]

def get_pods_logic(namespace: str):
    pods = v1.list_namespaced_pod(namespace)
    pod_list = []
    for p in pods.items:
        # Check health
        is_healthy = True
        if p.status.phase != "Running":
            is_healthy = False
        for container_status in p.status.container_statuses or []:
            if not container_status.ready:
                is_healthy = False
        
        pod_list.append(PodStatus(
            name=p.metadata.name,
            status=p.status.phase,
            restarts=sum([cs.restart_count for cs in (p.status.container_statuses or [])]),
            age=str(p.metadata.creation_timestamp),
            is_healthy=is_healthy
        ))
    return pod_list

def get_deployments_logic(namespace: str):
    print(f"DEBUG: get_deployments_logic called for namespace: {namespace}")
    deps = apps_v1.list_namespaced_deployment(namespace)
    print(f"DEBUG: Found {len(deps.items)} deployments")
    result = []
    for d in deps.items:
        conditions = []
        for c in (d.status.conditions or []):
            conditions.append({
                "type": c.type, "status": c.status,
                "reason": c.reason or "", "message": c.message or ""
            })

        # Determine rollout status
        desired = d.spec.replicas or 0
        ready = d.status.ready_replicas or 0
        updated = d.status.updated_replicas or 0
        available = d.status.available_replicas or 0
        unavailable = d.status.unavailable_replicas or 0

        if unavailable > 0:
            rollout_status = "Degraded"
        elif updated < desired:
            rollout_status = "Progressing"
        elif ready >= desired:
            rollout_status = "Healthy"
        else:
            rollout_status = "Waiting"

        containers = d.spec.template.spec.containers or []
        images = [c.image for c in containers]

        result.append({
            "name": d.metadata.name,
            "namespace": d.metadata.namespace,
            "replicas": desired,
            "ready_replicas": ready,
            "updated_replicas": updated,
            "available_replicas": available,
            "unavailable_replicas": unavailable,
            "images": images,
            "strategy": d.spec.strategy.type if d.spec.strategy else "RollingUpdate",
            "rollout_status": rollout_status,
            "conditions": conditions,
            "labels": dict(d.metadata.labels or {}),
            "selector": dict(d.spec.selector.match_labels or {}) if d.spec.selector else {},
            "age": str(d.metadata.creation_timestamp),
        })
    return result

def get_statefulsets_logic(namespace: str):
    sts_list = apps_v1.list_namespaced_stateful_set(namespace)
    result = []
    for s in sts_list.items:
        desired = s.spec.replicas or 0
        ready = s.status.ready_replicas or 0
        current = s.status.current_replicas or 0
        containers = s.spec.template.spec.containers or []
        images = [c.image for c in containers]

        if ready >= desired:
            status = "Healthy"
        elif ready > 0:
            status = "Degraded"
        else:
            status = "Unhealthy"

        result.append({
            "name": s.metadata.name,
            "namespace": s.metadata.namespace,
            "replicas": desired,
            "ready_replicas": ready,
            "current_replicas": current,
            "images": images,
            "status": status,
            "service_name": s.spec.service_name or "",
            "labels": dict(s.metadata.labels or {}),
            "selector": dict(s.spec.selector.match_labels or {}) if s.spec.selector else {},
            "age": str(s.metadata.creation_timestamp),
        })
    return result

def get_daemonsets_logic(namespace: str):
    ds_list = apps_v1.list_namespaced_daemon_set(namespace)
    result = []
    for d in ds_list.items:
        desired = d.status.desired_number_scheduled or 0
        ready = d.status.number_ready or 0
        current = d.status.current_number_scheduled or 0
        updated = d.status.updated_number_scheduled or 0
        available = d.status.number_available or 0
        containers = d.spec.template.spec.containers or []
        images = [c.image for c in containers]

        if ready >= desired and desired > 0:
            status = "Healthy"
        elif ready > 0:
            status = "Degraded"
        else:
            status = "Unhealthy"

        result.append({
            "name": d.metadata.name,
            "namespace": d.metadata.namespace,
            "desired": desired,
            "current": current,
            "ready": ready,
            "updated": updated,
            "available": available,
            "images": images,
            "status": status,
            "labels": dict(d.metadata.labels or {}),
            "selector": dict(d.spec.selector.match_labels or {}) if d.spec.selector else {},
            "age": str(d.metadata.creation_timestamp),
        })
    return result

def get_events_logic(namespace: str):
    events = v1.list_namespaced_event(namespace)
    result = []
    for e in events.items:
        result.append({
            "type": e.type or "Normal",
            "reason": e.reason or "",
            "message": e.message or "",
            "object_kind": e.involved_object.kind or "",
            "object_name": e.involved_object.name or "",
            "source": e.source.component if e.source else "",
            "first_seen": str(e.first_timestamp or e.metadata.creation_timestamp),
            "last_seen": str(e.last_timestamp or e.metadata.creation_timestamp),
            "count": e.count or 1,
        })
    result.sort(key=lambda x: x["last_seen"], reverse=True)
    return result

def get_services_logic(namespace: str):
    svc_list = v1.list_namespaced_service(namespace)
    result = []
    for s in svc_list.items:
        # Get endpoint count
        endpoint_count = 0
        try:
            ep = v1.read_namespaced_endpoints(s.metadata.name, namespace)
            for subset in (ep.subsets or []):
                endpoint_count += len(subset.addresses or [])
        except Exception:
            pass

        ports = []
        for p in (s.spec.ports or []):
            ports.append({
                "name": p.name or "",
                "port": p.port,
                "target_port": str(p.target_port),
                "protocol": p.protocol or "TCP",
                "node_port": p.node_port,
            })

        result.append({
            "name": s.metadata.name,
            "namespace": s.metadata.namespace,
            "type": s.spec.type or "ClusterIP",
            "cluster_ip": s.spec.cluster_ip or "",
            "external_ips": s.spec.external_i_ps or [],
            "ports": ports,
            "selector": dict(s.spec.selector or {}),
            "endpoint_count": endpoint_count,
            "labels": dict(s.metadata.labels or {}),
            "age": str(s.metadata.creation_timestamp),
        })
    return result

def get_ingresses_logic(namespace: str):
    ing_list = networking_v1.list_namespaced_ingress(namespace)
    result = []
    for i in ing_list.items:
        rules = []
        for r in (i.spec.rules or []):
            paths = []
            if r.http:
                for p in (r.http.paths or []):
                    paths.append({
                        "path": p.path or "/",
                        "path_type": p.path_type or "Prefix",
                        "backend_service": p.backend.service.name if p.backend and p.backend.service else "",
                        "backend_port": p.backend.service.port.number if p.backend and p.backend.service and p.backend.service.port else 0,
                    })
            rules.append({
                "host": r.host or "*",
                "paths": paths,
            })

        lb_ips = []
        if i.status and i.status.load_balancer and i.status.load_balancer.ingress:
            for lb in i.status.load_balancer.ingress:
                lb_ips.append(lb.ip or lb.hostname or "")

        result.append({
            "name": i.metadata.name,
            "namespace": i.metadata.namespace,
            "class_name": i.spec.ingress_class_name or "",
            "rules": rules,
            "load_balancer_ips": lb_ips,
            "tls": [{"hosts": t.hosts or [], "secret": t.secret_name or ""} for t in (i.spec.tls or [])],
            "labels": dict(i.metadata.labels or {}),
            "age": str(i.metadata.creation_timestamp),
        })
    return result

def get_network_policies_logic(namespace: str):
    np_list = networking_v1.list_namespaced_network_policy(namespace)
    result = []
    for n in np_list.items:
        ingress_rules = len(n.spec.ingress or []) if n.spec.ingress is not None else 0
        egress_rules = len(n.spec.egress or []) if n.spec.egress is not None else 0
        policy_types = n.spec.policy_types or []

        result.append({
            "name": n.metadata.name,
            "namespace": n.metadata.namespace,
            "pod_selector": dict(n.spec.pod_selector.match_labels or {}) if n.spec.pod_selector else {},
            "policy_types": policy_types,
            "ingress_rules_count": ingress_rules,
            "egress_rules_count": egress_rules,
            "labels": dict(n.metadata.labels or {}),
            "age": str(n.metadata.creation_timestamp),
        })
    return result

def get_topology_logic(namespace: str):
    deps = apps_v1.list_namespaced_deployment(namespace)
    sts = apps_v1.list_namespaced_stateful_set(namespace)
    ds = apps_v1.list_namespaced_daemon_set(namespace)
    pods = v1.list_namespaced_pod(namespace)
    svcs = v1.list_namespaced_service(namespace)

    nodes = []
    edges = []

    # Add workload nodes
    workload_selectors = {}  # name -> selector labels for service matching
    for d in deps.items:
        node_id = f"deploy/{d.metadata.name}"
        ready = d.status.ready_replicas or 0
        desired = d.spec.replicas or 0
        nodes.append({
            "id": node_id, "label": d.metadata.name, "kind": "Deployment",
            "status": "healthy" if ready >= desired else "degraded" if ready > 0 else "unhealthy",
            "detail": f"{ready}/{desired} ready",
        })
        if d.spec.selector and d.spec.selector.match_labels:
            workload_selectors[node_id] = dict(d.spec.selector.match_labels)

    for s in sts.items:
        node_id = f"sts/{s.metadata.name}"
        ready = s.status.ready_replicas or 0
        desired = s.spec.replicas or 0
        nodes.append({
            "id": node_id, "label": s.metadata.name, "kind": "StatefulSet",
            "status": "healthy" if ready >= desired else "degraded" if ready > 0 else "unhealthy",
            "detail": f"{ready}/{desired} ready",
        })
        if s.spec.selector and s.spec.selector.match_labels:
            workload_selectors[node_id] = dict(s.spec.selector.match_labels)

    for d in ds.items:
        node_id = f"ds/{d.metadata.name}"
        ready = d.status.number_ready or 0
        desired = d.status.desired_number_scheduled or 0
        nodes.append({
            "id": node_id, "label": d.metadata.name, "kind": "DaemonSet",
            "status": "healthy" if ready >= desired and desired > 0 else "degraded" if ready > 0 else "unhealthy",
            "detail": f"{ready}/{desired} ready",
        })
        if d.spec.selector and d.spec.selector.match_labels:
            workload_selectors[node_id] = dict(d.spec.selector.match_labels)

    # Add pod nodes and connect to owners
    for p in pods.items:
        is_healthy = p.status.phase == "Running"
        for cs in (p.status.container_statuses or []):
            if not cs.ready:
                is_healthy = False

        pod_id = f"pod/{p.metadata.name}"
        nodes.append({
            "id": pod_id, "label": p.metadata.name, "kind": "Pod",
            "status": "healthy" if is_healthy else "unhealthy",
            "detail": p.status.phase,
        })

        # Trace owner chain: Pod → ReplicaSet → Deployment
        if p.metadata.owner_references:
            owner = p.metadata.owner_references[0]
            if owner.kind == "ReplicaSet":
                try:
                    rs = apps_v1.read_namespaced_replica_set(owner.name, namespace)
                    if rs.metadata.owner_references:
                        parent = rs.metadata.owner_references[0]
                        edges.append({"from": f"deploy/{parent.name}", "to": pod_id})
                    else:
                        edges.append({"from": f"rs/{owner.name}", "to": pod_id})
                except Exception:
                    pass
            elif owner.kind == "StatefulSet":
                edges.append({"from": f"sts/{owner.name}", "to": pod_id})
            elif owner.kind == "DaemonSet":
                edges.append({"from": f"ds/{owner.name}", "to": pod_id})

    # Add service nodes and connect to workloads via selector matching
    for svc in svcs.items:
        svc_id = f"svc/{svc.metadata.name}"
        svc_selector = dict(svc.spec.selector or {})

        # Count endpoints
        ep_count = 0
        try:
            ep = v1.read_namespaced_endpoints(svc.metadata.name, namespace)
            for subset in (ep.subsets or []):
                ep_count += len(subset.addresses or [])
        except Exception:
            pass

        nodes.append({
            "id": svc_id, "label": svc.metadata.name, "kind": "Service",
            "status": "healthy" if ep_count > 0 else "warning",
            "detail": f"{svc.spec.type} · {ep_count} endpoints",
        })

        # Match service selector to workload selectors
        if svc_selector:
            for wl_id, wl_labels in workload_selectors.items():
                if all(svc_selector.get(k) == v for k, v in wl_labels.items()) or \
                   all(wl_labels.get(k) == v for k, v in svc_selector.items()):
                    edges.append({"from": svc_id, "to": wl_id})

    return {"nodes": nodes, "edges": edges}

def get_stats_logic(namespace: Optional[str] = None):
    total = 0
    unhealthy = 0
    running = 0
    ns_count = 0
    
    try:
        # Get total namespace count regardless of current filter
        ns_count = len(v1.list_namespace().items)

        if namespace and namespace != "all":
            pods = v1.list_namespaced_pod(namespace)
        else:
            pods = v1.list_pod_for_all_namespaces()
        
        total = len(pods.items)
        for p in pods.items:
# ...
            is_p_healthy = True
            if p.status.phase != "Running":
                is_p_healthy = False
            
            for cs in (p.status.container_statuses or []):
                if not cs.ready:
                    is_p_healthy = False
            
            if is_p_healthy:
                running += 1
            else:
                unhealthy += 1
    except Exception as k8s_err:
        print(f"K8s Data Fetch Error: {k8s_err}")
            
    return {
        "total_pods": total,
        "running_pods": running,
        "unhealthy_pods": unhealthy,
        "namespaces": ns_count,
        "health_score": int(((total - unhealthy) / total * 100)) if total > 0 else 100,
        "cluster_connected": True
    }

def gather_pod_data_for_diagnosis(namespace: str, pod_name: str):
    # 1. Collect enhanced live data
    pod = v1.read_namespaced_pod(pod_name, namespace)
    events = v1.list_namespaced_event(namespace, field_selector=f"involvedObject.name={pod_name}")
    
    # Get related resources (Deployment/ReplicaSet)
    owner_info = "Standalone Pod"
    parent_spec = None
    if pod.metadata.owner_references:
        owner = pod.metadata.owner_references[0]
        owner_info = f"{owner.kind}/{owner.name}"
        try:
            if owner.kind == "ReplicaSet":
                rs = apps_v1.read_namespaced_replica_set(owner.name, namespace)
                if rs.metadata.owner_references:
                    parent = rs.metadata.owner_references[0]
                    owner_info = f"{parent.kind}/{parent.name}"
                    if parent.kind == "Deployment":
                        parent_spec = apps_v1.read_namespaced_deployment(parent.name, namespace).to_dict()
            elif owner.kind == "StatefulSet":
                parent_spec = apps_v1.read_namespaced_stateful_set(owner.name, namespace).to_dict()
        except Exception:
            pass

    logs = ""
    try:
        logs = v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=150)
    except Exception:
        try:
            # Try previous logs if it's crashlooping
            logs = v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=150, previous=True)
            logs = f"PREVIOUS LOGS:\n{logs}"
        except Exception:
            logs = "No logs available."

    # Determine current health
    is_healthy = pod.status.phase == "Running"
    container_statuses_summary = []
    for cs in (pod.status.container_statuses or []):
        if not cs.ready:
            is_healthy = False
        container_statuses_summary.append({
            "name": cs.name,
            "ready": cs.ready,
            "restart_count": cs.restart_count,
            "state": str(cs.state)
        })

    return {
        "pod": pod,
        "events": events,
        "logs": logs,
        "is_healthy": is_healthy,
        "owner_info": owner_info,
        "parent_spec": parent_spec,
        "container_statuses_summary": container_statuses_summary
    }

def search_resources_logic(query: str):
    """Searches for resources by name across all namespaces."""
    if not query or len(query) < 2:
        return []
        
    query = query.lower()
    results = []
    
    # Search Pods
    try:
        pods = v1.list_pod_for_all_namespaces()
        for p in pods.items:
            if query in p.metadata.name.lower():
                results.append({
                    "kind": "Pod",
                    "name": p.metadata.name,
                    "namespace": p.metadata.namespace,
                    "status": p.status.phase,
                    "is_healthy": p.status.phase == "Running" and all(cs.ready for cs in (p.status.container_statuses or []))
                })
                if len(results) >= 50: return results
    except Exception: pass

    # Search Deployments
    try:
        deps = apps_v1.list_deployment_for_all_namespaces()
        for d in deps.items:
            if query in d.metadata.name.lower():
                results.append({
                    "kind": "Deployment",
                    "name": d.metadata.name,
                    "namespace": d.metadata.namespace,
                    "status": "Healthy" if (d.status.ready_replicas or 0) >= (d.spec.replicas or 0) else "Degraded",
                    "is_healthy": (d.status.ready_replicas or 0) >= (d.spec.replicas or 0)
                })
                if len(results) >= 50: return results
    except Exception: pass

    # Search Services
    try:
        svcs = v1.list_service_for_all_namespaces()
        for s in svcs.items:
            if query in s.metadata.name.lower():
                results.append({
                    "kind": "Service",
                    "name": s.metadata.name,
                    "namespace": s.metadata.namespace,
                    "status": s.spec.type,
                    "is_healthy": True
                })
                if len(results) >= 50: return results
    except Exception: pass

    # Search Ingresses
    try:
        ings = networking_v1.list_ingress_for_all_namespaces()
        for i in ings.items:
            if query in i.metadata.name.lower():
                results.append({
                    "kind": "Ingress",
                    "name": i.metadata.name,
                    "namespace": i.metadata.namespace,
                    "status": "Active",
                    "is_healthy": True
                })
                if len(results) >= 50: return results
    except Exception: pass

    return results

def get_pod_logs_logic(namespace: str, pod_name: str, tail: int = 200):
    """Fetches logs for a pod, with fallback to previous logs."""
    try:
        return v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=tail)
    except Exception:
        try:
            prev_logs = v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=tail, previous=True)
            return f"PREVIOUS LOGS (CRASHED):\n{prev_logs}"
        except Exception:
            return "No logs available."
