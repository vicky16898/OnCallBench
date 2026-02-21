# OnCallBench AI: Premium K8s Debugger

OnCallBench has evolved from a simple scenario simulator into a **Premium AI-Powered Debugging Dashboard**. It connects directly to your live Kubernetes cluster, discovers issues automatically, and uses Gemini 2.0 to provide root-cause analysis and fix steps.

## Features

- **Gemini 2.0 Integration**: High-fidelity AI diagnosis optimized for Google Gemini.
- **Auto-Discovery**: No more manually specifying scenarios. Select any namespace or pod directly from the UI.
- **Zero-Input Debugging**: Click a pod, get a fix. The agent gathers logs and events automatically.
- **Premium GUI**: A glassmorphic, modern dashboard built with React, Tailwind, and Framer Motion.

## Installation

1. **Clone and Enter**:
   ```powershell
   cd OnCallBench
   ```

2. **Setup Python Backend**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Setup GUI**:
   ```powershell
   cd gui
   npm install
   ```

4. **Environment**:
   Update your `.env` file with your `GOOGLE_API_KEY`.

## Running the App

### 1. Start the Backend API
In your first terminal (with venv active):
```powershell
python src/api.py
```

### 2. Start the Premium GUI
In a second terminal:
```powershell
cd gui
npm run dev
```
Open **[http://localhost:3000](http://localhost:3000)** to start debugging.

## Chaos Injection (Optional)
If you want to test the debugger with controlled failures, you can still use the CLI:
```powershell
python k8s-chaos.py inject --scenario oomkill
```
