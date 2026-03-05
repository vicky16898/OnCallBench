# Re-export K8s clients from k8s_service (single source of truth)
from k8s_service import v1, apps_v1, networking_v1, K8S_MODE, _init_k8s_clients

def get_k8s_clients():
    _init_k8s_clients()  # ensure clients are loaded
    from k8s_service import v1, apps_v1, networking_v1, K8S_MODE
    return v1, apps_v1, networking_v1, K8S_MODE
