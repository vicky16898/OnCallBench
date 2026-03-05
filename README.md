<p align="center">
  <h1 align="center">⚡ OnCallBench</h1>
  <p align="center">
    <strong>AI-powered Kubernetes troubleshooting that finds, diagnoses, and fixes cluster issues before you even open the terminal.</strong>
  </p>
  <p align="center">
    <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" /></a>
    <a href="https://kubernetes.io"><img src="https://img.shields.io/badge/Kubernetes-Powered-326CE5?style=for-the-badge&logo=kubernetes&logoColor=white" alt="Kubernetes" /></a>
    <a href="https://ai.google.dev"><img src="https://img.shields.io/badge/Gemini_2.0-AI_Engine-8E75B2?style=for-the-badge&logo=google&logoColor=white" alt="Gemini" /></a>
    <a href="https://react.dev"><img src="https://img.shields.io/badge/React_18-Frontend-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React" /></a>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License" /></a>
  </p>
</p>

<br />

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="OnCallBench Dashboard" width="100%" />
</p>

---

## The Problem

When a Kubernetes pod crashes at 3 AM, the SRE workflow looks like this:

```
PagerDuty fires  →  SSH into cluster  →  kubectl describe pod  →  copy logs
→  paste into ChatGPT  →  read response  →  manually craft kubectl commands
→  hope it works  →  repeat if it doesn't
```

Every step is manual. Every incident starts from scratch. The AI has no cluster access, no context, and no ability to verify its own fix.

## The Solution

**OnCallBench connects AI directly to your cluster.** It watches for anomalies in real-time, diagnoses issues using multi-turn investigation with 6 specialized tools, suggests one-click fixes, and self-corrects when a fix fails — all from a single dashboard.

```
Anomaly detected  →  AI investigates (logs, events, topology)  →  Root cause identified
→  Fix command generated  →  One-click apply  →  Auto-verified  →  Done.
```

No copy-pasting. No context switching. No guesswork.

---

## ✨ Key Features

### 🔍 Proactive Event Watcher
A background watcher monitors your entire cluster in real-time — detecting CrashLoops, OOMKills, failed scheduling, and probe failures **before you notice them**. Alerts auto-resolve when pods recover.

<p align="center">
  <img src="docs/screenshots/alerts.png" alt="Proactive Alerts" width="100%" />
</p>

### 🧠 AI-Powered Diagnosis
Click any unhealthy pod → Gemini 2.0 Flash launches a multi-turn investigation using 6 tools: `kubectl` commands, log search, resource inspection, health checks, metrics, and namespace listing. It traces owner chains (Pod → ReplicaSet → Deployment), checks related Services and NetworkPolicies, and produces a structured diagnosis with root cause, symptoms, fix steps, and confidence score.

### 🔧 One-Click Fixes with Self-Correction
The AI generates ready-to-run `kubectl` commands. Click **"Apply Fix"** and it executes. If the fix fails, the error is automatically sent back to the AI for a corrected command — no manual intervention needed.

### ⚙️ Workloads & Resource Management
Full visibility into Deployments, StatefulSets, and DaemonSets with replica gauges, health status, container images, and expandable pod views.

<p align="center">
  <img src="docs/screenshots/workloads.png" alt="Workloads View" width="100%" />
</p>

### 🗺️ Topology Visualization
Interactive dependency graph showing Service → Deployment → Pod relationships with health indicators at every level.

<p align="center">
  <img src="docs/screenshots/topology.png" alt="Topology Graph" width="100%" />
</p>

### 📊 AI Performance Benchmarks
Inject pre-built failure scenarios (CrashLoopBackOff, OOMKill, ImagePullBackOff, etc.) and score the AI's diagnostic accuracy using an **LLM-as-a-Judge** evaluation pipeline. Track root cause match, fix correctness, and confidence across all scenarios.

<p align="center">
  <img src="docs/screenshots/benchmarks.png" alt="Performance Benchmarks" width="100%" />
</p>

---

## 🔬 How the AI Agent Works

OnCallBench doesn't just read logs and guess. It runs a **multi-turn investigation loop**:

```
1. OBSERVE    →  Gather pod status, events, logs, container states
2. TRACE      →  Follow owner chain (Pod → ReplicaSet → Deployment)
3. CORRELATE  →  Check related Services, NetworkPolicies, ConfigMaps
4. HYPOTHESIZE →  Form root cause hypothesis
5. VERIFY     →  Run targeted kubectl commands to confirm
6. FIX        →  Generate idempotent, owner-aware kubectl patch
7. VALIDATE   →  Verify fix with label selectors (not stale pod names)
```

**Safety built in:**
- Commands restricted to a safe allowlist (no `delete namespace`, no `drain node`)
- Fixes target parent controllers (Deployment), not individual Pods
- All commands are non-interactive and idempotent
- Destructive commands are automatically blocked

---

## 🎯 Built-in Failure Scenarios

| Scenario | Difficulty | Category | What Breaks |
|----------|-----------|----------|-------------|
| **CrashLoopBackOff** | Easy | Container | Bad command causes immediate exit |
| **OOMKilled** | Medium | Resources | Container exceeds memory limit |
| **ImagePullBackOff** | Easy | Container | Invalid image tag |
| **Missing ConfigMap** | Easy | Configuration | Referenced ConfigMap doesn't exist |
| **Missing Secret** | Easy | Configuration | Referenced Secret doesn't exist |
| **Readiness Probe Failure** | Medium | Health | Wrong probe path returns 404 |
| **Liveness Probe Failure** | Medium | Health | Probe misconfigured, pod keeps restarting |
| **Pod Stuck Pending** | Medium | Scheduling | Resource requests exceed node capacity |
| **Port Mismatch** | Hard | Networking | Service targetPort doesn't match container port |

Each scenario includes ground truth for automated scoring.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      React Frontend                             │
│            Vite · Tailwind CSS · Framer Motion                  │
│                                                                 │
│  Dashboard · Workloads · Pods · Events · Networking · Topology  │
│  Scenarios · Benchmarks · Proactive Alerts · Global Search      │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP / REST
┌───────────────────────────┴─────────────────────────────────────┐
│                      FastAPI Backend                             │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ K8s Service  │  │ Event Watcher│  │   AI Agent (Gemini)    │ │
│  │              │  │  (Proactive  │  │  Multi-turn diagnosis  │ │
│  │ Pods, Events │  │   anomaly    │  │  6 investigation tools │ │
│  │ Deployments  │  │  detection)  │  │  Self-correcting fixes │ │
│  │ Services ... │  │              │  │  JSON structured output│ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────────┘ │
│         │                 │                      │               │
└─────────┼─────────────────┼──────────────────────┼───────────────┘
          ▼                 ▼                      ▼
    K8s Cluster        K8s Watch API        Google Gemini 2.0
```

---

## 🚀 Getting Started

### Prerequisites

- A running Kubernetes cluster (Minikube, EKS, GKE, AKS, or any)
- Google Gemini API key — [get one free](https://aistudio.google.com/apikey)
- Python 3.10+ and Node.js 18+

### Option 1: In-Cluster Deployment

Run OnCallBench inside your cluster for direct control plane access.

```bash
# Build & load images (Minikube example)
docker build -t oncall-backend:latest .
docker build -t oncall-frontend:latest ./gui
minikube image load oncall-backend:latest
minikube image load oncall-frontend:latest

# Set your API key
kubectl create secret generic oncall-secrets \
  --from-literal=GOOGLE_API_KEY="your-key-here" \
  -n oncall-bench --dry-run=client -o yaml | kubectl apply -f -

# Deploy
kubectl apply -f k8s/deploy.yaml

# Access the dashboard
minikube service oncall-frontend -n oncall-bench
```

### Option 2: Local Development

Run on your machine while connecting to any cluster via kubeconfig.

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/OnCallBench.git
cd OnCallBench

# Backend
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # Add your GOOGLE_API_KEY
python src/api.py

# Frontend (new terminal)
cd gui && npm install && npm run dev
```

Open **http://localhost:5173** → Select a namespace → Start diagnosing.

---

## 📁 Project Structure

```
OnCallBench/
├── src/
│   ├── api.py              # FastAPI backend — REST API + startup hooks
│   ├── agent.py            # AI agent — multi-turn Gemini tool-calling
│   ├── event_watcher.py    # Proactive anomaly detection (Watch API)
│   ├── k8s_service.py      # Kubernetes client — pods, events, topology
│   ├── evaluator.py        # LLM-as-a-Judge scoring pipeline
│   ├── injector.py         # Chaos injection engine
│   ├── utils.py            # JSON repair, kubectl command preparation
│   └── prompt_templates/
│       └── k8s_system_prompt.txt  # AI agent persona & safety rules
├── gui/
│   └── src/
│       ├── App.jsx         # Main React application (1900+ lines)
│       └── components/
│           ├── AlertPanel.jsx     # Proactive alert notifications
│           ├── WorkloadsTab.jsx   # Deployment/StatefulSet/DaemonSet view
│           ├── EventsTab.jsx      # Event timeline with filtering
│           ├── NetworkingTab.jsx  # Services, Ingresses, NetworkPolicies
│           ├── TopologyTab.jsx    # Interactive dependency graph
│           └── ChatPanel.jsx      # AI chat interface (v2)
├── scenarios/              # 9 failure scenarios with ground truth
├── k8s/
│   └── deploy.yaml         # Full K8s deployment manifest
├── requirements.txt        # Pinned Python dependencies
└── docs/screenshots/       # Product screenshots
```

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, Vite, Tailwind CSS, Framer Motion, Lucide React |
| **Backend** | FastAPI, Python 3.10+, Kubernetes Python Client |
| **AI Engine** | Google Gemini 2.0 Flash (multi-turn tool calling) |
| **Scoring** | LLM-as-a-Judge automated evaluation |
| **Monitoring** | K8s Watch API, background health checker |
| **Deployment** | Docker, Kubernetes, Nginx |

---

## 🗺️ Roadmap

- [x] Multi-turn AI agent with 6 investigation tools
- [x] 9 failure scenarios with automated scoring
- [x] Proactive event watcher with auto-resolve
- [x] Topology visualization
- [x] Self-correcting fix loop
- [ ] Slack / PagerDuty integration
- [ ] Incident history database
- [ ] Multi-cluster support
- [ ] AI chat interface (built, not yet exposed)
- [ ] Predictive warnings (trend analysis)

---

## 📝 License

MIT License — see [LICENSE](./LICENSE) for details.

---

<p align="center">
  <strong>Built for SREs who'd rather fix problems than fight tools.</strong>
  <br />
  <sub>Star ⭐ if this saves you from a 3 AM kubectl session.</sub>
</p>
