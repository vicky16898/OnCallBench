# ⚡ OnCallBench

> **Benchmark AI agents on real Kubernetes incidents — chaos injection, Gemini-powered diagnostics, and automated scoring.**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-Powered-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io)
[![Gemini](https://img.shields.io/badge/Gemini_2.0-AI_Diagnostics-8E75B2?logo=google&logoColor=white)](https://ai.google.dev)
[![React](https://img.shields.io/badge/React_18-Frontend-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

---

## 🎯 What is OnCallBench?

OnCallBench is an open-source benchmarking platform that tests how well AI agents handle real Kubernetes on-call incidents.

**The workflow:**
1. 🔥 **Inject** — Deploy pre-built failure scenarios (CrashLoop, OOMKill, DNS, ImagePull, etc.) into a live K8s cluster
2. 🧠 **Diagnose** — AI (Gemini 2.0 Flash) analyzes pod logs, events, and container states to identify root cause
3. 📊 **Score** — LLM-as-a-Judge evaluates the AI's diagnosis accuracy, fix correctness, and confidence

Think of it as **"LeetCode for SRE AI agents."**

---

## ✨ Features

| Feature | Description |
|---|---|
| 🎯 **6 Failure Scenarios** | CrashLoopBackOff, OOMKilled, ImagePullBackOff, DNS failures, Network Policies, Readiness probe failures |
| 🧠 **AI Diagnostics** | Gemini 2.0 Flash analyzes logs, events, and container states with structured JSON output |
| 📊 **Automated Scoring** | LLM-as-a-Judge evaluates root cause match, fix correctness, and confidence score |
| 🖥️ **Real-time Dashboard** | Health score, pod status, namespace overview with animated stats cards |
| 🔍 **SRE Inspector** | Click any pod → AI diagnosis with root cause, symptoms, fix steps, and kubectl commands |
| 🌙 **Dark/Light Mode** | Premium UI with full theme support |
| ♻️ **Auto-Refresh** | Dashboard updates every 30 seconds |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────┐
│                 React Frontend               │
│         (Vite + Tailwind + Framer Motion)    │
└──────────────────┬───────────────────────────┘
                   │ HTTP (axios)
                   ▼
┌──────────────────────────────────────────────┐
│              FastAPI Backend                  │
│         (Python + Kubernetes Client)         │
├──────────────┬───────────────────────────────┤
│  K8s Client  │     Gemini 2.0 Flash API      │
│  (kubectl)   │     (AI Diagnostics)          │
└──────┬───────┴───────────────┬───────────────┘
       ▼                       ▼
  K8s Cluster            Google AI Studio
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- A running Kubernetes cluster (minikube, kind, EKS, GKE, etc.)
- `kubectl` configured and pointing to your cluster
- Google AI API key ([get one here](https://aistudio.google.com/apikey))

### 1. Clone & Setup

```bash
git clone https://github.com/YOUR_USERNAME/OnCallBench.git
cd OnCallBench
```

### 2. Backend

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# Start the API server
python src/api.py
```

### 3. Frontend

```bash
cd gui
npm install
npm run dev
```

### 4. Open the Dashboard

Navigate to `http://localhost:5173` — the dashboard will auto-connect to your cluster.

---

## 📁 Project Structure

```
OnCallBench/
├── src/
│   ├── api.py          # FastAPI backend (main API server)
│   ├── agent.py        # AI agent logic
│   ├── collector.py    # K8s data collection
│   ├── evaluator.py    # LLM-as-a-Judge scoring
│   ├── injector.py     # Chaos injection logic
│   └── main.py         # CLI entry point
├── gui/
│   ├── src/
│   │   ├── App.jsx     # Main React application
│   │   ├── index.css   # Design system & theme
│   │   └── main.jsx    # React entry point
│   └── index.html      # HTML template
├── scenarios/
│   ├── crashloop/      # CrashLoopBackOff scenario
│   ├── oomkill/        # OOMKilled scenario
│   ├── imagepull/      # ImagePullBackOff scenario
│   ├── dns/            # DNS resolution failure
│   ├── netpolicy/      # Network policy blocking
│   └── readiness/      # Readiness probe failure
├── data/               # Generated reports & predictions
├── .env                # API keys (not committed)
├── requirements.txt    # Python dependencies
└── README.md
```

---

## 🔧 Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18, Vite, Tailwind CSS, Framer Motion, Lucide Icons |
| **Backend** | FastAPI, Python, Kubernetes Python Client |
| **AI Engine** | Google Gemini 2.0 Flash |
| **Scoring** | LLM-as-a-Judge evaluation pipeline |
| **Infrastructure** | Kubernetes, kubectl |

---

## 📝 License

MIT License — see [LICENSE](./LICENSE) for details.

---

**Built with ☕ and too many on-call pages.**
