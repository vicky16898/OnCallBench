import os
import sys
import asyncio
from kubernetes import client, config

# Initialize K8s client
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

def get_k8s_clients():
    return v1, apps_v1, networking_v1, K8S_MODE
