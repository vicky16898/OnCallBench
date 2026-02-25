import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import {
    LayoutDashboard,
    Activity,
    Zap,
    History,
    RefreshCw,
    ChevronRight,
    Shield,
    AlertCircle,
    CheckCircle2,
    Command,
    Terminal,
    Moon,
    Sun,
    Layers,
    Cpu,
    Server,
    Clock,
    ArrowUpRight,
    Play,
    LayoutGrid,
    Box,
    Globe,
    Network,
    GitBranch
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import WorkloadsTab from './components/WorkloadsTab';
import EventsTab from './components/EventsTab';
import NetworkingTab from './components/NetworkingTab';
import TopologyTab from './components/TopologyTab';

const API_BASE = import.meta.env.PROD ? '/api' : 'http://localhost:8000';
const api = axios.create({ baseURL: API_BASE, timeout: 15000 });

function App() {
    const [activeTab, setActiveTab] = useState('dashboard');
    const [theme, setTheme] = useState('light');
    const [namespaces, setNamespaces] = useState([]);
    const [selectedNS, setSelectedNS] = useState(null);
    const [pods, setPods] = useState([]);
    const [scenarios, setScenarios] = useState([]);
    const [stats, setStats] = useState(null);
    const [statsLoading, setStatsLoading] = useState(true);
    const [statsError, setStatsError] = useState(null);
    const [selectedPod, setSelectedPod] = useState(null);
    const [diagnosis, setDiagnosis] = useState(null);
    const [diagnosisError, setDiagnosisError] = useState(null);
    const [loading, setLoading] = useState(false);
    const [injecting, setInjecting] = useState(null);
    const [injectResult, setInjectResult] = useState(null);
    const [benchmarks, setBenchmarks] = useState([]);
    const [refreshing, setRefreshing] = useState(false);
    const [statsDetail, setStatsDetail] = useState(null);
    const [lastRefreshed, setLastRefreshed] = useState(null);
    const [copiedCmd, setCopiedCmd] = useState(null);
    const [appInfo, setAppInfo] = useState(null);
    const [executingCmd, setExecutingCmd] = useState(null);
    const [executionResults, setExecutionResults] = useState({});
    const pollGeneration = useRef(0);

    // Dashboard overview data for new tabs
    const [dashDeployments, setDashDeployments] = useState([]);
    const [dashStatefulsets, setDashStatefulsets] = useState([]);
    const [dashDaemonsets, setDashDaemonsets] = useState([]);
    const [dashEvents, setDashEvents] = useState([]);
    const [dashServices, setDashServices] = useState([]);
    const [dashIngresses, setDashIngresses] = useState([]);
    const [dashNetpolicies, setDashNetpolicies] = useState([]);
    const [dashOverviewLoading, setDashOverviewLoading] = useState(false);

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
    }, [theme]);

    useEffect(() => {
        fetchInitialData();
    }, []);

    useEffect(() => {
        if (selectedNS) {
            fetchPods(selectedNS);
            handleRefreshStats(selectedNS);
            fetchDashboardOverview(selectedNS);
        }
    }, [selectedNS]);

    // Keyboard shortcut: Escape closes overlays (stats detail first, then drawer)
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                if (statsDetail) setStatsDetail(null);
                else if (selectedPod) closeInspector();
            }
        };
        const handleClickOutside = (e) => {
            if (statsDetail && !e.target.closest('[data-stats-grid]')) {
                setStatsDetail(null);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        document.addEventListener('mousedown', handleClickOutside);
        return () => { window.removeEventListener('keydown', handleKeyDown); document.removeEventListener('mousedown', handleClickOutside); };
    }, [selectedPod, statsDetail]);

    // Fetch dashboard overview data for new tabs
    const fetchDashboardOverview = useCallback(async (ns) => {
        const namespace = ns || selectedNS;
        if (!namespace) return;
        setDashOverviewLoading(true);
        try {
            const [depRes, ssRes, dsRes, evtRes, svcRes, ingRes, npRes] = await Promise.allSettled([
                api.get(`/namespaces/${namespace}/deployments`),
                api.get(`/namespaces/${namespace}/statefulsets`),
                api.get(`/namespaces/${namespace}/daemonsets`),
                api.get(`/namespaces/${namespace}/events`),
                api.get(`/namespaces/${namespace}/services`),
                api.get(`/namespaces/${namespace}/ingresses`),
                api.get(`/namespaces/${namespace}/networkpolicies`),
            ]);
            if (depRes.status === 'fulfilled') setDashDeployments(depRes.value.data || []);
            if (ssRes.status === 'fulfilled') setDashStatefulsets(ssRes.value.data || []);
            if (dsRes.status === 'fulfilled') setDashDaemonsets(dsRes.value.data || []);
            if (evtRes.status === 'fulfilled') setDashEvents(evtRes.value.data || []);
            if (svcRes.status === 'fulfilled') setDashServices(svcRes.value.data || []);
            if (ingRes.status === 'fulfilled') setDashIngresses(ingRes.value.data || []);
            if (npRes.status === 'fulfilled') setDashNetpolicies(npRes.value.data || []);
        } catch (err) {
            console.error('Dashboard overview fetch error', err);
        } finally {
            setDashOverviewLoading(false);
        }
    }, [api, selectedNS]);

    // Auto-refresh dashboard every 30s
    const autoRefreshRef = useRef(null);
    useEffect(() => {
        if (activeTab === 'dashboard' && selectedNS) {
            autoRefreshRef.current = setInterval(() => {
                setStatsDetail(null); // close stale popover before refresh
                fetchPods(selectedNS);
                handleRefreshStats(selectedNS);
                fetchDashboardOverview(selectedNS);
            }, 30000);
        }
        return () => { if (autoRefreshRef.current) clearInterval(autoRefreshRef.current); };
    }, [activeTab, selectedNS, fetchDashboardOverview]);

    const fetchInitialData = async () => {
        // 1. Fetch Namespaces
        try {
            const nsRes = await api.get('/namespaces');
            const nsData = nsRes.data || [];
            setNamespaces(nsData);

            // Smart namespace selection – always set on initial load
            if (nsData.includes('oncall-bench')) {
                setSelectedNS('oncall-bench');
            } else if (nsData.length > 0) {
                setSelectedNS(nsData[0]);
            } else {
                setSelectedNS('default');
            }
        } catch (err) {
            console.error("Namespaces fetch failed");
            setSelectedNS('default');
        }

        // 2. Fetch Scenarios
        try {
            const scRes = await api.get('/scenarios');
            setScenarios(scRes.data || []);
        } catch (err) {
            console.error("Scenarios fetch failed");
        }

        // 3. Fetch Benchmarks
        try {
            const benchRes = await api.get('/benchmarks');
            setBenchmarks(benchRes.data || []);
        } catch (err) {
            console.error("Benchmarks fetch failed");
        }

        // 4. Fetch App Info
        try {
            const infoRes = await api.get('/info');
            setAppInfo(infoRes.data);
        } catch (err) {
            console.error("App info fetch failed");
        }

        // 4. Stats is handled by the useEffect on selectedNS
    };

    const fetchPods = async (ns) => {
        try {
            console.log(`Fetching pods for namespace: ${ns}`);
            const res = await api.get(`/namespaces/${ns}/pods`);
            const podData = res.data || [];
            setPods(podData);
            return podData;
        } catch (err) {
            console.error("Pods fetch failed", err);
            setPods([]);
            return [];
        }
    };

    const handleRefreshStats = async (ns = selectedNS) => {
        setStatsLoading(true);
        setStatsError(null);
        try {
            const res = await api.get('/stats', { params: { namespace: ns } });
            setStats(res.data);
            setLastRefreshed(new Date());
        } catch (err) {
            console.error("Stats fetch failed", err);
            setStatsError(err.message);
        } finally {
            setStatsLoading(false);
        }
    };

    const injectScenario = async (id) => {
        setInjecting(id);
        setInjectResult(null);
        try {
            const res = await api.post(`/inject/${id}`);
            setInjectResult({ type: 'success', message: res.data?.message || `Scenario ${id} injected successfully` });
            // Poll multiple times to allow K8s to reconcile pod state
            // (a single delayed fetch often misses transitional states like ImagePull)
            const pollIntervals = [2000, 5000, 10000];
            pollIntervals.forEach((delay) => {
                setTimeout(() => {
                    fetchPods(selectedNS);
                    handleRefreshStats();
                }, delay);
            });
        } catch (err) {
            console.error(err);
            setInjectResult({ type: 'error', message: err.response?.data?.detail || err.message || 'Injection failed' });
        }
        finally { setInjecting(null); }
    };

    const runDiagnosis = async (podName) => {
        setLoading(true);
        setDiagnosis(null);
        setDiagnosisError(null);
        try {
            const res = await api.post('/diagnose', { namespace: selectedNS, pod_name: podName });
            setDiagnosis(res.data);
        } catch (err) {
            console.error(err);
            setDiagnosisError(err.response?.data?.detail || err.message || 'Diagnosis failed');
        }
        finally { setLoading(false); }
    };

    // Close the AI Inspector drawer and invalidate any in-flight poll callbacks
    const closeInspector = useCallback(() => {
        pollGeneration.current += 1;
        setSelectedPod(null);
        setDiagnosis(null);
        setDiagnosisError(null);
        setExecutionResults({});
    }, []);

    const handleExecuteCommand = async (command, idx) => {
        setExecutingCmd(idx);
        const oldPodName = selectedPod?.name;
        // Keep track of the prefix (e.g., 'crashloop-app-') to find the replacement pod
        const podPrefix = oldPodName?.split('-').slice(0, -2).join('-');

        // Bump generation so any previous poll callbacks skip drawer-specific logic
        const currentGen = ++pollGeneration.current;

        try {
            const res = await api.post('/execute', { command });
            setExecutionResults(prev => ({ ...prev, [idx]: res.data }));

            // Poll multiple times to let K8s fully reconcile after the fix.
            // Pods & stats are ALWAYS refreshed (never cancelled), but
            // drawer-specific updates (selecting the new pod, re-diagnosing)
            // only run if the generation is still current (drawer wasn't closed).
            const pollDelays = [3000, 6000, 10000, 15000];
            pollDelays.forEach((delay, pollIdx) => {
                setTimeout(async () => {
                    // Always refresh pods & stats so the table stays current
                    const refreshedPods = await fetchPods(selectedNS);
                    await handleRefreshStats();

                    // Skip drawer-specific logic if the drawer was closed
                    // or a newer command started (generation mismatch)
                    if (pollGeneration.current !== currentGen) return;

                    const newPod = refreshedPods?.find(p => p.name.startsWith(podPrefix || '')) || refreshedPods?.[0];

                    if (newPod) {
                        setSelectedPod(newPod);
                        if (pollIdx === pollDelays.length - 1) {
                            runDiagnosis(newPod.name);
                        }
                    } else {
                        setSelectedPod(null);
                    }
                }, delay);
            });
        } catch (err) {
            setExecutionResults(prev => ({
                ...prev,
                [idx]: { success: false, stderr: err.response?.data?.detail || err.message }
            }));
        } finally {
            setExecutingCmd(null);
        }
    };

    const toggleTheme = () => setTheme(theme === 'light' ? 'dark' : 'light');

    return (
        <div className="flex h-screen bg-background transition-colors duration-300 overflow-hidden font-inter">
            {/* Sidebar */}
            <aside className="w-20 lg:w-64 bg-sidebar border-r border-border flex flex-col transition-all duration-300 flex-shrink-0 z-20">
                <div className="h-16 flex items-center gap-3 px-6 mb-4 border-b border-border">
                    <div className="min-w-[32px] h-8 rounded-lg bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
                        <Shield size={20} className="text-white" />
                    </div>
                    <span className="hidden lg:inline font-bold font-outfit text-xl tracking-tight text-foreground">OnCallBench</span>
                </div>

                <nav className="flex-1 px-3 space-y-1 py-4 overflow-y-auto custom-scrollbar min-h-0">
                    <NavItem icon={<LayoutDashboard size={20} />} label="Dashboard" active={activeTab === 'dashboard'} onClick={() => setActiveTab('dashboard')} />
                    <NavItem icon={<Box size={20} />} label="Workloads" active={activeTab === 'workloads'} onClick={() => setActiveTab('workloads')} />
                    <NavItem icon={<Activity size={20} />} label="Pods" active={activeTab === 'pods'} onClick={() => setActiveTab('pods')} badge={pods.length > 0 ? pods.length : null} />
                    <NavItem icon={<Clock size={20} />} label="Events" active={activeTab === 'events'} onClick={() => setActiveTab('events')} />
                    <NavItem icon={<Globe size={20} />} label="Networking" active={activeTab === 'networking'} onClick={() => setActiveTab('networking')} />
                    <NavItem icon={<GitBranch size={20} />} label="Topology" active={activeTab === 'topology'} onClick={() => setActiveTab('topology')} />
                    <NavItem icon={<Zap size={20} />} label="Scenarios" active={activeTab === 'scenarios'} onClick={() => setActiveTab('scenarios')} badge={scenarios.length > 0 ? scenarios.length : null} />
                    <NavItem icon={<History size={20} />} label="Benchmarks" active={activeTab === 'benchmarks'} onClick={() => setActiveTab('benchmarks')} badge={benchmarks.length > 0 ? benchmarks.length : null} />
                </nav>

                <div className="p-4 border-t border-border bg-muted/30">
                    <h4 className="hidden lg:block text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-3 px-2">Context</h4>
                    <div className="flex flex-col gap-3">
                        <div className="lg:flex hidden flex-col gap-1">
                            <label className="text-[10px] text-muted-foreground px-2">NAMESPACE</label>
                            <select
                                className="w-full bg-card text-xs border border-border rounded-lg p-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                                value={selectedNS}
                                onChange={(e) => setSelectedNS(e.target.value)}
                            >
                                {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
                            </select>
                        </div>
                        <button
                            onClick={toggleTheme}
                            className="flex items-center justify-center lg:justify-start gap-3 w-full p-2.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
                        >
                            {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
                            <span className="hidden lg:inline text-sm font-medium">{theme === 'light' ? 'Dark Mode' : 'Light Mode'}</span>
                        </button>
                    </div>
                </div>

                {appInfo && (
                    <div className="p-4 border-t border-border mt-auto">
                        <div className="bg-muted/50 rounded-xl p-3 border border-border/50">
                            <div className="flex items-center justify-between mb-2">
                                <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-tighter">Connection</span>
                                <div className={`w-1.5 h-1.5 rounded-full ${appInfo.mode === 'in-cluster' ? 'bg-success' : 'bg-indigo-500'}`} />
                            </div>
                            <div className="text-[11px] font-bold text-foreground truncate">{appInfo.mode === 'in-cluster' ? 'Native Cluster' : 'Local Kubeconfig'}</div>
                            <div className="text-[9px] text-muted-foreground mt-1 flex items-center gap-1">
                                {appInfo.api_ready ? <span className="text-success font-bold text-[8px]">●</span> : <span className="text-error font-bold text-[8px]">○</span>}
                                API Ready · v{appInfo.version}
                            </div>
                        </div>
                    </div>
                )}
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col relative overflow-hidden">
                <header className="h-16 flex items-center justify-between px-8 bg-card/50 backdrop-blur-md border-b border-border flex-shrink-0">
                    <div className="flex items-center gap-3">
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{activeTab}</h2>
                        <ChevronRight size={14} className="text-muted-foreground/40" />
                        <span className="text-sm font-medium text-foreground">{selectedNS || 'Loading...'}</span>
                    </div>

                    <div className="flex items-center gap-6">
                        {lastRefreshed && (
                            <span className="text-[10px] text-muted-foreground hidden md:flex items-center gap-1">
                                <Clock size={10} />
                                {lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                        )}
                        <div className="flex bg-muted rounded-full p-1 border border-border">
                            <span className={`px-3 py-1 text-[10px] font-bold flex items-center gap-1.5 ${stats && stats.unhealthy_pods > 0 ? 'text-warning' : 'text-success'}`}>
                                <div className={`w-2 h-2 rounded-full animate-pulse ${stats && stats.unhealthy_pods > 0 ? 'bg-warning' : 'bg-success'}`} />
                                {stats && stats.unhealthy_pods > 0 ? `${stats.unhealthy_pods} Unhealthy` : 'Cluster Healthy'}
                            </span>
                        </div>
                        <button
                            onClick={async () => {
                                setRefreshing(true);
                                await Promise.all([fetchPods(selectedNS), handleRefreshStats()]);
                                setRefreshing(false);
                            }}
                            className="text-muted-foreground hover:text-primary transition-all p-2 bg-card border border-border rounded-lg hover:shadow-sm"
                            title="Refresh data"
                        >
                            <RefreshCw size={18} className={refreshing ? 'animate-spin' : ''} />
                        </button>
                    </div>
                </header>

                <div className="flex-1 overflow-auto p-8 custom-scrollbar">
                    <AnimatePresence mode="wait">
                        {activeTab === 'dashboard' && (
                            <motion.div key="dashboard" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.4, ease: 'easeOut' }} className="space-y-8 max-w-6xl">
                                {statsLoading ? (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                                        {[1, 2, 3, 4].map(i => (
                                            <div key={i} className="h-32 bg-card border border-border rounded-2xl shimmer" />
                                        ))}
                                    </div>
                                ) : statsError ? (
                                    <div className="p-8 bg-error/10 border border-error/20 rounded-2xl text-center">
                                        <p className="text-error font-bold mb-2">Failed to fetch cluster stats</p>
                                        <p className="text-xs text-muted-foreground">{statsError}</p>
                                        <button onClick={() => handleRefreshStats()} className="mt-4 px-4 py-2 bg-card border border-border rounded-lg text-xs hover:bg-muted transition-all">Try Again</button>
                                    </div>
                                ) : stats && (
                                    <div className="space-y-8">
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6" data-stats-grid>
                                            {[
                                                {
                                                    label: 'Health Score', value: `${stats.health_score}%`, icon: <Shield className="text-indigo-600" />,
                                                    trend: stats.health_score === 100 ? 'Good' : stats.health_score >= 80 ? '+2%' : 'Critical',
                                                    detailTitle: 'Cluster Health Breakdown',
                                                    detailContent: (
                                                        <div className="space-y-4">
                                                            <div className="flex items-center justify-center">
                                                                <div className="relative w-20 h-20">
                                                                    <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                                                                        <path d="M18 2.0845a 15.9155 15.9155 0 0 1 0 31.831a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="rgb(var(--muted))" strokeWidth="3.5" />
                                                                        <motion.path d="M18 2.0845a 15.9155 15.9155 0 0 1 0 31.831a 15.9155 15.9155 0 0 1 0 -31.831" fill="none"
                                                                            stroke={stats.health_score >= 80 ? '#22c55e' : stats.health_score >= 50 ? '#f59e0b' : '#ef4444'}
                                                                            strokeWidth="3.5" strokeLinecap="round"
                                                                            initial={{ strokeDasharray: '0 100' }}
                                                                            animate={{ strokeDasharray: `${stats.health_score} ${100 - stats.health_score}` }}
                                                                            transition={{ duration: 1, delay: 0.3, type: 'spring' }}
                                                                        />
                                                                    </svg>
                                                                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                                                                        <span className="text-xl font-bold font-outfit text-foreground">{stats.health_score}%</span>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                            <div className="grid grid-cols-2 gap-2">
                                                                <div className="p-2.5 rounded-xl bg-success/10 text-center">
                                                                    <div className="text-sm font-bold text-success">{stats.total_pods - stats.unhealthy_pods}</div>
                                                                    <div className="text-[9px] text-success/70 font-medium uppercase">Healthy</div>
                                                                </div>
                                                                <div className="p-2.5 rounded-xl bg-error/10 text-center">
                                                                    <div className="text-sm font-bold text-error">{stats.unhealthy_pods}</div>
                                                                    <div className="text-[9px] text-error/70 font-medium uppercase">Unhealthy</div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    )
                                                },
                                                {
                                                    label: 'Running Pods', value: `${stats.running_pods}/${stats.total_pods}`, icon: <Cpu className="text-blue-500" />,
                                                    trend: stats.running_pods === stats.total_pods ? 'Good' : 'Critical',
                                                    detailTitle: 'Pod Status Overview',
                                                    detailContent: (
                                                        <div className="space-y-2">
                                                            {pods.length === 0 ? (
                                                                <p className="text-sm text-muted-foreground text-center py-4">No pods in current namespace</p>
                                                            ) : pods.map(p => (
                                                                <div key={p.name} className="flex items-center justify-between p-3 rounded-xl bg-muted/40 border border-border hover:border-indigo-500/20 transition-colors">
                                                                    <div className="flex items-center gap-3">
                                                                        <div className={`w-2 h-2 rounded-full ${p.is_healthy ? 'bg-success' : 'bg-error animate-pulse'}`} />
                                                                        <span className="text-xs font-semibold text-foreground truncate max-w-[180px]">{p.name}</span>
                                                                    </div>
                                                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${p.is_healthy ? 'bg-success/10 text-success' : 'bg-error/10 text-error'}`}>{p.status}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )
                                                },
                                                {
                                                    label: 'Unhealthy', value: stats.unhealthy_pods, icon: <AlertCircle className="text-red-500" />,
                                                    trend: stats.unhealthy_pods > 0 ? 'Critical' : 'Good',
                                                    detailTitle: stats.unhealthy_pods > 0 ? 'Unhealthy Pods' : 'All Pods Healthy',
                                                    detailContent: (
                                                        <div className="space-y-3">
                                                            {pods.filter(p => !p.is_healthy).length === 0 ? (
                                                                <div className="flex flex-col items-center py-6 gap-3">
                                                                    <CheckCircle2 size={40} className="text-success" />
                                                                    <p className="text-sm font-medium text-success">All pods are healthy!</p>
                                                                    <p className="text-[11px] text-muted-foreground">No action required.</p>
                                                                </div>
                                                            ) : pods.filter(p => !p.is_healthy).map(p => (
                                                                <div key={p.name} className="p-4 rounded-xl bg-error/5 border border-error/15 flex items-center justify-between">
                                                                    <div>
                                                                        <div className="text-xs font-bold text-foreground">{p.name}</div>
                                                                        <div className="text-[10px] text-muted-foreground mt-0.5">Restarts: {p.restarts}</div>
                                                                    </div>
                                                                    <button
                                                                        onClick={(e) => { e.stopPropagation(); setStatsDetail(null); setSelectedPod(p); setActiveTab('pods'); runDiagnosis(p.name); }}
                                                                        className="text-[10px] font-bold text-indigo-600 hover:text-indigo-700 px-3 py-1.5 bg-indigo-500/10 rounded-lg transition-colors"
                                                                    >
                                                                        Diagnose
                                                                    </button>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )
                                                },
                                                {
                                                    label: 'Namespaces', value: stats.namespaces, icon: <Layers className="text-purple-500" />,
                                                    detailTitle: 'Available Namespaces',
                                                    detailContent: (
                                                        <div className="space-y-2">
                                                            {namespaces.map(ns => (
                                                                <button
                                                                    key={ns}
                                                                    onClick={(e) => { e.stopPropagation(); setSelectedNS(ns); setStatsDetail(null); }}
                                                                    className={`w-full flex items-center justify-between p-3 rounded-xl border transition-all text-left ${ns === selectedNS
                                                                        ? 'bg-indigo-500/10 border-indigo-500/20 text-indigo-600'
                                                                        : 'bg-muted/40 border-border hover:border-indigo-500/20 text-foreground'
                                                                        }`}
                                                                >
                                                                    <span className="text-xs font-semibold">{ns}</span>
                                                                    {ns === selectedNS && <span className="text-[9px] font-bold bg-indigo-600 text-white px-2 py-0.5 rounded">ACTIVE</span>}
                                                                </button>
                                                            ))}
                                                        </div>
                                                    )
                                                },
                                            ].map((card, idx) => (
                                                <motion.div
                                                    key={card.label}
                                                    initial={{ opacity: 0, y: 30, scale: 0.95 }}
                                                    animate={{ opacity: 1, y: 0, scale: 1 }}
                                                    transition={{ delay: idx * 0.1, duration: 0.5, type: 'spring', stiffness: 100 }}
                                                    className="relative"
                                                >
                                                    <StatsCard {...card} onClick={() => setStatsDetail(prev => prev?.label === card.label ? null : card)} active={statsDetail?.label === card.label} />

                                                    {/* Popover anchored below this card */}
                                                    <AnimatePresence>
                                                        {statsDetail?.label === card.label && (
                                                            <motion.div
                                                                initial={{ opacity: 0, y: -8, scale: 0.95 }}
                                                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                                                exit={{ opacity: 0, y: -8, scale: 0.95 }}
                                                                transition={{ type: 'spring', damping: 25, stiffness: 400 }}
                                                                className={`absolute top-full mt-3 z-30 w-[340px] ${idx === 0 ? 'left-0' : idx >= 3 ? 'right-0' : 'left-1/2 -translate-x-1/2'
                                                                    }`}
                                                            >
                                                                {/* Arrow */}
                                                                <div className={`absolute -top-1.5 w-3 h-3 bg-card border-l border-t border-border rotate-45 ${idx === 0 ? 'left-6' : idx >= 3 ? 'right-6' : 'left-1/2 -translate-x-1/2'
                                                                    }`} />
                                                                <div className="relative bg-card border border-border rounded-2xl shadow-xl shadow-black/8 overflow-hidden">
                                                                    <div className="px-5 py-3.5 border-b border-border flex items-center justify-between">
                                                                        <div className="flex items-center gap-3">
                                                                            <div className="p-2 bg-muted rounded-xl">{card.icon}</div>
                                                                            <div>
                                                                                <h3 className="font-outfit font-bold text-sm text-foreground">{card.detailTitle}</h3>
                                                                                <p className="text-[10px] text-muted-foreground">{card.label} · {card.value}</p>
                                                                            </div>
                                                                        </div>
                                                                        <button onClick={(e) => { e.stopPropagation(); setStatsDetail(null); }} className="w-7 h-7 flex items-center justify-center hover:bg-muted rounded-full text-muted-foreground hover:text-foreground transition-colors text-xs">✕</button>
                                                                    </div>
                                                                    <div className="p-5 max-h-72 overflow-auto custom-scrollbar">
                                                                        {card.detailContent}
                                                                    </div>
                                                                </div>
                                                            </motion.div>
                                                        )}
                                                    </AnimatePresence>
                                                </motion.div>
                                            ))}
                                        </div>

                                        {/* ── New Tabs Overview Section ── */}
                                        <div className="space-y-4">
                                            <h3 className="font-outfit text-lg font-bold text-foreground">Cluster Resources Overview</h3>
                                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                                {/* Workloads Widget */}
                                                <motion.div
                                                    initial={{ opacity: 0, y: 20 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    transition={{ delay: 0.1 }}
                                                    className="bg-card rounded-2xl border border-border p-5 hover:shadow-md transition-all cursor-pointer group"
                                                    onClick={() => setActiveTab('workloads')}
                                                >
                                                    <div className="flex items-center justify-between mb-4">
                                                        <div className="p-2 bg-blue-500/10 rounded-xl"><Box className="text-blue-500" size={20} /></div>
                                                        <ArrowUpRight size={16} className="text-muted-foreground group-hover:text-blue-500 transition-colors" />
                                                    </div>
                                                    <h4 className="font-outfit font-bold text-foreground mb-1">Workloads</h4>
                                                    {dashOverviewLoading ? (
                                                        <div className="h-10 bg-muted rounded-lg shimmer" />
                                                    ) : (
                                                        <div className="space-y-1.5">
                                                            <div className="flex items-center justify-between text-xs">
                                                                <span className="text-muted-foreground">Deployments</span>
                                                                <span className="font-bold text-foreground">{dashDeployments.length}</span>
                                                            </div>
                                                            <div className="flex items-center justify-between text-xs">
                                                                <span className="text-muted-foreground">StatefulSets</span>
                                                                <span className="font-bold text-foreground">{dashStatefulsets.length}</span>
                                                            </div>
                                                            <div className="flex items-center justify-between text-xs">
                                                                <span className="text-muted-foreground">DaemonSets</span>
                                                                <span className="font-bold text-foreground">{dashDaemonsets.length}</span>
                                                            </div>
                                                            {(() => {
                                                                const allWL = [...dashDeployments, ...dashStatefulsets, ...dashDaemonsets];
                                                                const degraded = allWL.filter(w => w.ready_replicas < w.replicas).length;
                                                                return degraded > 0 ? (
                                                                    <div className="mt-2 px-2 py-1.5 bg-warning/10 rounded-lg text-[10px] font-bold text-warning flex items-center gap-1">
                                                                        <AlertCircle size={12} /> {degraded} degraded
                                                                    </div>
                                                                ) : (
                                                                    <div className="mt-2 px-2 py-1.5 bg-success/10 rounded-lg text-[10px] font-bold text-success flex items-center gap-1">
                                                                        <CheckCircle2 size={12} /> All healthy
                                                                    </div>
                                                                );
                                                            })()}
                                                        </div>
                                                    )}
                                                </motion.div>

                                                {/* Events Widget */}
                                                <motion.div
                                                    initial={{ opacity: 0, y: 20 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    transition={{ delay: 0.15 }}
                                                    className="bg-card rounded-2xl border border-border p-5 hover:shadow-md transition-all cursor-pointer group"
                                                    onClick={() => setActiveTab('events')}
                                                >
                                                    <div className="flex items-center justify-between mb-4">
                                                        <div className="p-2 bg-amber-500/10 rounded-xl"><Clock className="text-amber-500" size={20} /></div>
                                                        <ArrowUpRight size={16} className="text-muted-foreground group-hover:text-amber-500 transition-colors" />
                                                    </div>
                                                    <h4 className="font-outfit font-bold text-foreground mb-1">Events</h4>
                                                    {dashOverviewLoading ? (
                                                        <div className="h-10 bg-muted rounded-lg shimmer" />
                                                    ) : (
                                                        <div className="space-y-1.5">
                                                            <div className="flex items-center justify-between text-xs">
                                                                <span className="text-muted-foreground">Total Events</span>
                                                                <span className="font-bold text-foreground">{dashEvents.length}</span>
                                                            </div>
                                                            {(() => {
                                                                const warnings = dashEvents.filter(e => e.type === 'Warning');
                                                                const normals = dashEvents.filter(e => e.type === 'Normal');
                                                                return (
                                                                    <>
                                                                        <div className="flex items-center justify-between text-xs">
                                                                            <span className="text-muted-foreground">Normal</span>
                                                                            <span className="font-bold text-success">{normals.length}</span>
                                                                        </div>
                                                                        <div className="flex items-center justify-between text-xs">
                                                                            <span className="text-muted-foreground">Warnings</span>
                                                                            <span className={`font-bold ${warnings.length > 0 ? 'text-warning' : 'text-foreground'}`}>{warnings.length}</span>
                                                                        </div>
                                                                        {warnings.length > 0 ? (
                                                                            <div className="mt-2 px-2 py-1.5 bg-warning/10 rounded-lg text-[10px] font-bold text-warning flex items-center gap-1">
                                                                                <AlertCircle size={12} /> {warnings.length} warning{warnings.length > 1 ? 's' : ''} detected
                                                                            </div>
                                                                        ) : (
                                                                            <div className="mt-2 px-2 py-1.5 bg-success/10 rounded-lg text-[10px] font-bold text-success flex items-center gap-1">
                                                                                <CheckCircle2 size={12} /> No warnings
                                                                            </div>
                                                                        )}
                                                                    </>
                                                                );
                                                            })()}
                                                        </div>
                                                    )}
                                                </motion.div>

                                                {/* Networking Widget */}
                                                <motion.div
                                                    initial={{ opacity: 0, y: 20 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    transition={{ delay: 0.2 }}
                                                    className="bg-card rounded-2xl border border-border p-5 hover:shadow-md transition-all cursor-pointer group"
                                                    onClick={() => setActiveTab('networking')}
                                                >
                                                    <div className="flex items-center justify-between mb-4">
                                                        <div className="p-2 bg-emerald-500/10 rounded-xl"><Globe className="text-emerald-500" size={20} /></div>
                                                        <ArrowUpRight size={16} className="text-muted-foreground group-hover:text-emerald-500 transition-colors" />
                                                    </div>
                                                    <h4 className="font-outfit font-bold text-foreground mb-1">Networking</h4>
                                                    {dashOverviewLoading ? (
                                                        <div className="h-10 bg-muted rounded-lg shimmer" />
                                                    ) : (
                                                        <div className="space-y-1.5">
                                                            <div className="flex items-center justify-between text-xs">
                                                                <span className="text-muted-foreground">Services</span>
                                                                <span className="font-bold text-foreground">{dashServices.length}</span>
                                                            </div>
                                                            <div className="flex items-center justify-between text-xs">
                                                                <span className="text-muted-foreground">Ingresses</span>
                                                                <span className="font-bold text-foreground">{dashIngresses.length}</span>
                                                            </div>
                                                            <div className="flex items-center justify-between text-xs">
                                                                <span className="text-muted-foreground">Net Policies</span>
                                                                <span className="font-bold text-foreground">{dashNetpolicies.length}</span>
                                                            </div>
                                                            {(() => {
                                                                const nodeportSvcs = dashServices.filter(s => s.type === 'NodePort' || s.type === 'LoadBalancer');
                                                                return nodeportSvcs.length > 0 ? (
                                                                    <div className="mt-2 px-2 py-1.5 bg-blue-500/10 rounded-lg text-[10px] font-bold text-blue-500 flex items-center gap-1">
                                                                        <Globe size={12} /> {nodeportSvcs.length} externally exposed
                                                                    </div>
                                                                ) : (
                                                                    <div className="mt-2 px-2 py-1.5 bg-muted rounded-lg text-[10px] font-bold text-muted-foreground flex items-center gap-1">
                                                                        All internal (ClusterIP)
                                                                    </div>
                                                                );
                                                            })()}
                                                        </div>
                                                    )}
                                                </motion.div>

                                                {/* Topology Widget */}
                                                <motion.div
                                                    initial={{ opacity: 0, y: 20 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    transition={{ delay: 0.25 }}
                                                    className="bg-card rounded-2xl border border-border p-5 hover:shadow-md transition-all cursor-pointer group"
                                                    onClick={() => setActiveTab('topology')}
                                                >
                                                    <div className="flex items-center justify-between mb-4">
                                                        <div className="p-2 bg-violet-500/10 rounded-xl"><GitBranch className="text-violet-500" size={20} /></div>
                                                        <ArrowUpRight size={16} className="text-muted-foreground group-hover:text-violet-500 transition-colors" />
                                                    </div>
                                                    <h4 className="font-outfit font-bold text-foreground mb-1">Topology</h4>
                                                    {dashOverviewLoading ? (
                                                        <div className="h-10 bg-muted rounded-lg shimmer" />
                                                    ) : (
                                                        <div className="space-y-1.5">
                                                            {(() => {
                                                                const totalResources = dashDeployments.length + dashStatefulsets.length + dashDaemonsets.length + pods.length + dashServices.length;
                                                                return (
                                                                    <>
                                                                        <div className="flex items-center justify-between text-xs">
                                                                            <span className="text-muted-foreground">Total Resources</span>
                                                                            <span className="font-bold text-foreground">{totalResources}</span>
                                                                        </div>
                                                                        <div className="flex items-center justify-between text-xs">
                                                                            <span className="text-muted-foreground">Workloads</span>
                                                                            <span className="font-bold text-foreground">{dashDeployments.length + dashStatefulsets.length + dashDaemonsets.length}</span>
                                                                        </div>
                                                                        <div className="flex items-center justify-between text-xs">
                                                                            <span className="text-muted-foreground">Connections</span>
                                                                            <span className="font-bold text-foreground">{dashServices.length > 0 ? `~${dashServices.length * 2}` : '0'}</span>
                                                                        </div>
                                                                        <div className="mt-2 px-2 py-1.5 bg-violet-500/10 rounded-lg text-[10px] font-bold text-violet-500 flex items-center gap-1">
                                                                            <GitBranch size={12} /> View dependency graph
                                                                        </div>
                                                                    </>
                                                                );
                                                            })()}
                                                        </div>
                                                    )}
                                                </motion.div>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                                            <div className="lg:col-span-2 bg-card rounded-2xl border border-border p-6 shadow-sm">
                                                <div className="flex items-center justify-between mb-6">
                                                    <h3 className="font-outfit text-lg font-bold text-foreground">Incident Activity</h3>
                                                    <div className="flex items-center gap-4">
                                                        <span className="flex items-center gap-1.5 text-[10px] text-muted-foreground"><span className="w-2.5 h-2.5 rounded-sm bg-red-500 inline-block" /> Warning</span>
                                                        <span className="flex items-center gap-1.5 text-[10px] text-muted-foreground"><span className="w-2.5 h-2.5 rounded-sm bg-indigo-500 inline-block" /> Normal</span>
                                                    </div>
                                                </div>
                                                {(() => {
                                                    const reasonCounts = {};
                                                    dashEvents.forEach(evt => {
                                                        const r = evt.reason || 'Unknown';
                                                        if (!reasonCounts[r]) reasonCounts[r] = { normal: 0, warning: 0 };
                                                        const count = evt.count || 1;
                                                        if (evt.type === 'Warning') reasonCounts[r].warning += count;
                                                        else reasonCounts[r].normal += count;
                                                    });
                                                    const reasons = Object.entries(reasonCounts)
                                                        .map(([reason, counts]) => ({ reason, ...counts, total: counts.normal + counts.warning }))
                                                        .sort((a, b) => b.total - a.total)
                                                        .slice(0, 8);
                                                    const maxCount = Math.max(...reasons.map(r => r.total), 1);

                                                    if (reasons.length === 0) {
                                                        return (
                                                            <div className="h-52 flex flex-col items-center justify-center gap-3 text-center">
                                                                <CheckCircle2 size={40} className="text-success" />
                                                                <p className="text-sm font-medium text-success">No events in this namespace</p>
                                                                <p className="text-[11px] text-muted-foreground">Your cluster is quiet — nothing to report.</p>
                                                            </div>
                                                        );
                                                    }

                                                    return (
                                                        <div className="space-y-3">
                                                            {reasons.map((item, i) => (
                                                                <motion.div
                                                                    key={item.reason}
                                                                    initial={{ opacity: 0, x: -20 }}
                                                                    animate={{ opacity: 1, x: 0 }}
                                                                    transition={{ delay: 0.1 + i * 0.05 }}
                                                                    className="group"
                                                                >
                                                                    <div className="flex items-center justify-between mb-1">
                                                                        <span className="text-xs font-semibold text-foreground truncate max-w-[200px]">{item.reason}</span>
                                                                        <span className="text-[10px] text-muted-foreground font-mono">{item.total}</span>
                                                                    </div>
                                                                    <div className="h-5 bg-muted rounded-lg overflow-hidden flex">
                                                                        {item.warning > 0 && (
                                                                            <motion.div
                                                                                initial={{ width: 0 }}
                                                                                animate={{ width: `${(item.warning / maxCount) * 100}%` }}
                                                                                transition={{ delay: 0.3 + i * 0.05, duration: 0.6, type: 'spring', stiffness: 80 }}
                                                                                className="bg-red-500 rounded-l-lg group-hover:bg-red-400 transition-colors"
                                                                                style={{ minWidth: item.warning > 0 ? '4px' : 0 }}
                                                                                title={`${item.warning} warning${item.warning > 1 ? 's' : ''}`}
                                                                            />
                                                                        )}
                                                                        {item.normal > 0 && (
                                                                            <motion.div
                                                                                initial={{ width: 0 }}
                                                                                animate={{ width: `${(item.normal / maxCount) * 100}%` }}
                                                                                transition={{ delay: 0.35 + i * 0.05, duration: 0.6, type: 'spring', stiffness: 80 }}
                                                                                className={`bg-indigo-500 group-hover:bg-indigo-400 transition-colors ${item.warning === 0 ? 'rounded-l-lg' : ''} rounded-r-lg`}
                                                                                style={{ minWidth: item.normal > 0 ? '4px' : 0 }}
                                                                                title={`${item.normal} normal`}
                                                                            />
                                                                        )}
                                                                    </div>
                                                                </motion.div>
                                                            ))}
                                                        </div>
                                                    );
                                                })()}
                                            </div>
                                            <div className="bg-card rounded-2xl border border-border p-6 shadow-sm flex flex-col">
                                                <div className="flex items-center gap-3 mb-5">
                                                    <div className="p-2 bg-amber-500/10 rounded-xl"><AlertCircle className="text-amber-500" size={20} /></div>
                                                    <div>
                                                        <h3 className="font-outfit font-bold text-foreground">Recent Warnings</h3>
                                                        <p className="text-[10px] text-muted-foreground">Latest cluster warning events</p>
                                                    </div>
                                                </div>
                                                <div className="flex-1 overflow-auto custom-scrollbar space-y-2">
                                                    {(() => {
                                                        const warnings = dashEvents.filter(e => e.type === 'Warning').slice(0, 5);
                                                        if (warnings.length === 0) {
                                                            return (
                                                                <div className="flex flex-col items-center justify-center h-full gap-2 py-8">
                                                                    <CheckCircle2 size={28} className="text-success" />
                                                                    <p className="text-xs font-medium text-success">All clear</p>
                                                                    <p className="text-[10px] text-muted-foreground text-center">No warnings in this namespace</p>
                                                                </div>
                                                            );
                                                        }
                                                        return warnings.map((evt, i) => (
                                                            <div key={i} className="p-3 rounded-xl bg-amber-500/5 border border-amber-500/10 hover:border-amber-500/25 transition-colors">
                                                                <div className="flex items-center justify-between mb-1">
                                                                    <span className="text-[10px] font-bold text-amber-600 uppercase">{evt.reason}</span>
                                                                    {evt.count > 1 && <span className="text-[9px] font-bold bg-amber-500/10 text-amber-600 px-1.5 py-0.5 rounded">×{evt.count}</span>}
                                                                </div>
                                                                <p className="text-[11px] text-foreground line-clamp-2 leading-snug">{evt.message}</p>
                                                                <div className="flex items-center justify-between mt-1.5">
                                                                    <span className="text-[9px] text-muted-foreground truncate max-w-[120px]">{evt.involved_object}</span>
                                                                    <span className="text-[9px] text-muted-foreground">{evt.source}</span>
                                                                </div>
                                                            </div>
                                                        ));
                                                    })()}
                                                </div>
                                                <button
                                                    onClick={() => setActiveTab('events')}
                                                    className="w-full mt-4 py-2.5 bg-muted hover:bg-muted/80 text-foreground rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all active:scale-95"
                                                >
                                                    View All Events <ArrowUpRight size={14} />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </motion.div>
                        )}

                        {activeTab === 'pods' && (
                            <motion.div key="pods" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.35 }} className="space-y-6">
                                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }} className="flex items-center justify-between">
                                    <h2 className="text-2xl font-bold font-outfit text-foreground">Resource Explorer <span className="text-muted-foreground font-normal text-sm ml-2">Pods</span></h2>
                                    <div className="flex items-center gap-3">
                                        <span className="text-xs text-muted-foreground">{pods.length} total resources</span>
                                    </div>
                                </motion.div>

                                <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
                                    <table className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="text-[10px] text-muted-foreground uppercase tracking-wider border-b border-border">
                                                <th className="py-4 pl-6 font-bold">Pod Identifier</th>
                                                <th className="py-4 font-bold">Health Status</th>
                                                <th className="py-4 font-bold">Restarts</th>
                                                <th className="py-4 font-bold">Created At</th>
                                                <th className="py-4 pr-6 text-right">Utility</th>
                                            </tr>
                                        </thead>
                                        <tbody className="text-sm">
                                            {pods.length > 0 ? pods.map((pod, podIdx) => (
                                                <motion.tr
                                                    key={pod.name}
                                                    initial={{ opacity: 0, x: -30 }}
                                                    animate={{ opacity: 1, x: 0 }}
                                                    transition={{ delay: podIdx * 0.05, duration: 0.35, type: 'spring', stiffness: 120 }}
                                                    onClick={() => { setSelectedPod(pod); runDiagnosis(pod.name); }}
                                                    className={`border-b border-border/50 hover:bg-muted/30 cursor-pointer group transition-all ${selectedPod?.name === pod.name ? 'bg-muted/50 ring-1 ring-inset ring-indigo-500/10' : ''}`}
                                                >
                                                    <td className="py-5 pl-6">
                                                        <div className="flex items-center gap-4">
                                                            <div className={`p-2 rounded-lg ${pod.is_healthy ? 'bg-indigo-500/10 text-indigo-600' : 'bg-red-500/10 text-red-600'}`}>
                                                                <Server size={18} />
                                                            </div>
                                                            <div>
                                                                <div className="font-bold text-foreground text-sm">{pod.name}</div>
                                                                <div className="text-[10px] text-muted-foreground font-mono mt-0.5">{selectedNS}</div>
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="py-5">
                                                        <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-tight ${pod.is_healthy ? 'bg-success/10 text-success' : 'bg-red-500/10 text-red-600'
                                                            }`}>
                                                            {pod.status}
                                                        </span>
                                                    </td>
                                                    <td className="py-5">
                                                        <div className={`flex items-center gap-1.5 font-bold ${pod.restarts > 5 ? 'text-red-500' : 'text-foreground'}`}>
                                                            {pod.restarts}
                                                        </div>
                                                    </td>
                                                    <td className="py-5 text-muted-foreground tracking-tight">
                                                        {new Date(pod.age).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                                    </td>
                                                    <td className="py-5 pr-6 text-right">
                                                        <button className="p-2 bg-card border border-border rounded-lg text-muted-foreground group-hover:text-indigo-600 group-hover:border-indigo-500/20 transition-all">
                                                            <ChevronRight size={16} />
                                                        </button>
                                                    </td>
                                                </motion.tr>
                                            )) : (
                                                <tr>
                                                    <td colSpan="5">
                                                        <div className="py-32 flex flex-col items-center justify-center text-center px-6">
                                                            <div className="w-16 h-16 bg-muted/50 rounded-full flex items-center justify-center mb-4">
                                                                <LayoutGrid size={28} className="text-muted-foreground" />
                                                            </div>
                                                            <h3 className="text-lg font-bold text-foreground mb-1">Namespace is Empty</h3>
                                                            <p className="text-sm text-muted-foreground max-w-xs mb-6">No pods found in <span className="text-indigo-600 font-mono font-bold">{selectedNS}</span>. Switch namespace or inject an incident.</p>
                                                            <button onClick={() => setActiveTab('scenarios')} className="px-6 py-2 bg-indigo-600 text-white rounded-xl text-sm font-bold shadow-lg shadow-indigo-500/20 hover:scale-105 transition-all active:scale-95">
                                                                Explore Scenarios
                                                            </button>
                                                        </div>
                                                    </td>
                                                </tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </motion.div>
                        )}

                        {activeTab === 'scenarios' && (
                            <motion.div key="scenarios" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.35 }} className="space-y-8">
                                <div className="flex items-center justify-between gap-2">
                                    <div>
                                        <h2 className="text-2xl font-bold font-outfit text-foreground">Incident Scenarios</h2>
                                        <p className="text-muted-foreground text-sm">Inject pre-defined Kubernetes failures to benchmark your AI agent's response.</p>
                                    </div>
                                    <button
                                        onClick={fetchInitialData}
                                        className="p-2 hover:bg-muted rounded-lg transition-colors text-muted-foreground hover:text-foreground"
                                        title="Refresh Scenarios"
                                    >
                                        <RefreshCw size={18} />
                                    </button>
                                </div>

                                {/* Inject Result Toast */}
                                <AnimatePresence>
                                    {injectResult && (
                                        <motion.div
                                            initial={{ opacity: 0, y: -10 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            exit={{ opacity: 0, y: -10 }}
                                            className={`p-4 rounded-2xl border flex items-center justify-between gap-3 ${injectResult.type === 'success'
                                                ? 'bg-success/10 border-success/20 text-success'
                                                : 'bg-error/10 border-error/20 text-error'
                                                }`}
                                        >
                                            <div className="flex items-center gap-2">
                                                {injectResult.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                                                <span className="text-sm font-medium">{injectResult.message}</span>
                                            </div>
                                            <button onClick={() => setInjectResult(null)} className="text-xs opacity-60 hover:opacity-100">✕</button>
                                        </motion.div>
                                    )}
                                </AnimatePresence>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {scenarios.length === 0 ? (
                                        <div className="col-span-full py-20 bg-muted/30 border border-dashed border-border rounded-3xl flex flex-col items-center justify-center text-muted-foreground">
                                            <Zap size={48} className="mb-4 opacity-20 animate-float" />
                                            <p>No scenarios found in the ./scenarios directory.</p>
                                        </div>
                                    ) : scenarios.map((sc, scIdx) => (
                                        <motion.div
                                            key={sc.id}
                                            initial={{ opacity: 0, y: 30, scale: 0.9 }}
                                            animate={{ opacity: 1, y: 0, scale: 1 }}
                                            transition={{ delay: scIdx * 0.1, duration: 0.45, type: 'spring', stiffness: 80 }}
                                            className="bg-card border border-border rounded-3xl p-6 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all group flex flex-col relative overflow-hidden card-glow"
                                        >
                                            <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                                                <Zap size={64} className="text-indigo-600" />
                                            </div>
                                            <div className="mb-6 flex items-center justify-between">
                                                <div className="w-10 h-10 rounded-2xl bg-indigo-500/10 text-indigo-600 flex items-center justify-center">
                                                    <AlertCircle size={24} />
                                                </div>
                                                <span className="text-[10px] font-bold px-2 py-1 bg-yellow-500/10 text-yellow-600 rounded-md">V1.0</span>
                                            </div>
                                            <h3 className="font-outfit text-xl font-bold text-foreground mb-3">{sc.name}</h3>
                                            <p className="text-xs text-muted-foreground leading-relaxed flex-1 mb-8">{sc.description}</p>

                                            <button
                                                onClick={() => injectScenario(sc.id)}
                                                disabled={injecting === sc.id}
                                                className="w-full py-3 bg-primary text-primary-foreground hover:bg-primary/90 rounded-2xl text-[13px] font-bold transition-all flex items-center justify-center gap-2 group shadow-md shadow-primary/20 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                {injecting === sc.id ? <RefreshCw size={16} className="animate-spin" /> : <Zap size={16} className="group-hover:scale-125 transition-transform" />}
                                                {injecting === sc.id ? 'Injecting Chaos...' : 'Trigger Injection'}
                                            </button>
                                        </motion.div>
                                    ))}
                                </div>
                            </motion.div>
                        )}
                        {activeTab === 'benchmarks' && (
                            <motion.div key="benchmarks" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.35 }} className="space-y-8">
                                <div className="flex flex-col gap-2">
                                    <h2 className="text-2xl font-bold font-outfit text-foreground">Performance Benchmarks</h2>
                                    <p className="text-muted-foreground text-sm">Evaluation results of AI agent performance across different failure scenarios.</p>
                                </div>

                                {benchmarks.length === 0 ? (
                                    <div className="py-32 bg-card border border-dashed border-border rounded-[2.5rem] flex flex-col items-center justify-center text-center px-6">
                                        <div className="w-20 h-20 bg-muted rounded-full flex items-center justify-center mb-6">
                                            <History size={40} className="text-muted-foreground animate-float" />
                                        </div>
                                        <h3 className="text-xl font-bold mb-2 text-foreground">No Benchmarks Yet</h3>
                                        <p className="text-muted-foreground text-sm max-w-sm mb-8">Run your first diagnostic session and evaluate the results to see performance metrics here.</p>
                                        <button onClick={() => setActiveTab('scenarios')} className="px-8 py-3 bg-indigo-600 text-white rounded-2xl font-bold shadow-xl shadow-indigo-500/20 hover:scale-105 transition-all active:scale-95">
                                            Go to Scenarios
                                        </button>
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 gap-6">
                                        {benchmarks.map((b, i) => (
                                            <motion.div
                                                key={i}
                                                initial={{ opacity: 0, y: 20 }}
                                                animate={{ opacity: 1, y: 0 }}
                                                transition={{ delay: i * 0.1, duration: 0.4 }}
                                                className="bg-card border border-border rounded-3xl p-6 shadow-sm flex flex-col md:flex-row md:items-center gap-8 group hover:border-indigo-500/30 transition-all card-glow"
                                            >
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-3 mb-2">
                                                        <span className="text-[10px] font-bold px-2 py-0.5 bg-indigo-500/10 text-indigo-600 rounded uppercase">Scenario</span>
                                                        <h4 className="font-bold text-lg text-foreground">{b.scenario_id}</h4>
                                                    </div>
                                                    <p className="text-xs text-muted-foreground">Evaluation completed via LLM-as-a-Judge</p>
                                                </div>

                                                <div className="grid grid-cols-2 lg:grid-cols-3 gap-8 flex-[2]">
                                                    <BenchmarkMetric label="Root Cause Match" value={b.root_cause_match} />
                                                    <BenchmarkMetric label="Fix Correctness" value={b.fix_correctness} />
                                                    <div className="hidden lg:block">
                                                        <BenchmarkMetric label="AI Confidence" value={b.confidence_score} color="text-yellow-500" />
                                                    </div>
                                                </div>
                                            </motion.div>
                                        ))}
                                    </div>
                                )}
                            </motion.div>
                        )}
                        {activeTab === 'workloads' && (
                            <motion.div key="workloads" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.35 }}>
                                <WorkloadsTab api={api} selectedNS={selectedNS} onPodClick={(pod) => { setSelectedPod(pod); runDiagnosis(pod.name); }} />
                            </motion.div>
                        )}
                        {activeTab === 'events' && (
                            <motion.div key="events" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.35 }}>
                                <EventsTab api={api} selectedNS={selectedNS} />
                            </motion.div>
                        )}
                        {activeTab === 'networking' && (
                            <motion.div key="networking" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.35 }}>
                                <NetworkingTab api={api} selectedNS={selectedNS} />
                            </motion.div>
                        )}
                        {activeTab === 'topology' && (
                            <motion.div key="topology" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.35 }}>
                                <TopologyTab api={api} selectedNS={selectedNS} />
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </main>

            {/* Overlay for Drawer */}
            <AnimatePresence>
                {selectedPod && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
                        onClick={closeInspector}
                    />
                )}
            </AnimatePresence>

            {/* Right Drawer (SRE Inspector) */}
            <AnimatePresence>
                {selectedPod && (
                    <motion.div
                        initial={{ x: '100%', opacity: 0 }}
                        animate={{ x: 0, opacity: 1 }}
                        exit={{ x: '100%', opacity: 0 }}
                        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
                        className="fixed top-0 right-0 h-full w-full max-w-xl bg-card border-l border-border shadow-2xl z-50 flex flex-col"
                    >
                        <div className="h-20 flex items-center justify-between px-8 bg-card border-b border-border">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-indigo-600 rounded-lg text-white">
                                    <Terminal size={18} />
                                </div>
                                <div>
                                    <h2 className="text-lg font-bold font-outfit uppercase tracking-tight text-foreground">AI Inspector</h2>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => runDiagnosis(selectedPod.name)}
                                    disabled={loading}
                                    className="px-4 py-2 bg-indigo-50 border border-indigo-100 text-indigo-600 rounded-xl text-[11px] font-bold flex items-center gap-2 hover:bg-indigo-100 transition-all disabled:opacity-50"
                                >
                                    <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                                    REFRESH ANALYSIS
                                </button>
                                <button onClick={closeInspector} className="w-8 h-8 flex items-center justify-center hover:bg-muted rounded-full text-muted-foreground hover:text-foreground transition-colors" title="Close (Esc)">✕</button>
                            </div>
                        </div>

                        <div className="flex-1 overflow-auto p-8 custom-scrollbar relative">
                            <div className="mb-10 flex flex-col gap-6">
                                <div>
                                    <h4 className="text-2xl font-bold font-outfit text-foreground mb-1">{selectedPod.name}</h4>
                                    <div className="flex gap-4">
                                        <span className="text-[11px] text-muted-foreground flex items-center gap-1"><Layers size={12} /> {selectedNS}</span>
                                        <span className="text-[11px] text-muted-foreground flex items-center gap-1"><Clock size={12} /> Created {new Date(selectedPod.age).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div className="p-4 bg-muted/40 rounded-2xl border border-border">
                                        <label className="text-[9px] font-bold text-muted-foreground uppercase block mb-1">Phase</label>
                                        <div className="flex items-center gap-2">
                                            <div className={`text-sm font-bold ${selectedPod.is_healthy ? 'text-success' : 'text-error'}`}>{selectedPod.status}</div>
                                            {selectedPod.is_healthy && <span className="text-[9px] px-1.5 py-0.5 bg-success/10 text-success rounded font-bold">✓ Healthy</span>}
                                        </div>
                                    </div>
                                    <div className="p-4 bg-muted/40 rounded-2xl border border-border">
                                        <label className="text-[9px] font-bold text-muted-foreground uppercase block mb-1">Restarts</label>
                                        <div className="flex items-center gap-2">
                                            <div className={`text-sm font-bold ${selectedPod.restarts > 10 ? 'text-warning' : 'text-foreground'}`}>{selectedPod.restarts}</div>
                                            <span className="text-[9px] text-muted-foreground">total</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {loading ? (
                                <div className="h-64 flex flex-col items-center justify-center gap-6">
                                    <div className="relative">
                                        <div className="w-16 h-16 rounded-full border-2 border-indigo-600/10 border-t-indigo-600 animate-spin" />
                                        <div className="absolute inset-0 flex items-center justify-center">
                                            <Shield size={24} className="text-indigo-600 animate-pulse" />
                                        </div>
                                    </div>
                                    <p className="text-sm font-bold text-foreground animate-pulse text-center">Consulting Gemini 2.0 Expert...<br /><span className="text-[10px] text-muted-foreground font-normal">Analyzing logs and events</span></p>
                                </div>
                            ) : diagnosis ? (
                                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8 pb-12">
                                    <div className="group relative">
                                        <div className={`absolute -inset-0.5 bg-gradient-to-r rounded-2xl opacity-10 blur-sm ${diagnosis.risk_level === 'High' ? 'from-red-500 to-orange-500' :
                                            diagnosis.risk_level === 'Medium' ? 'from-yellow-500 to-orange-500' :
                                                'from-green-500 to-indigo-500'
                                            }`} />
                                        <div className="relative p-6 bg-card border border-border rounded-2xl">
                                            <div className={`flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest mb-3 ${diagnosis.risk_level === 'Low' ? 'text-success' : 'text-error'
                                                }`}>
                                                {diagnosis.risk_level === 'Low' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                                                Root Cause Analysis
                                            </div>
                                            <p className="text-foreground text-sm leading-relaxed italic border-l-2 border-indigo-500 pl-4 py-1">{diagnosis.root_cause}</p>
                                        </div>
                                    </div>

                                    {/* Symptoms */}
                                    {(diagnosis.symptoms || []).length > 0 && diagnosis.symptoms[0] !== 'No issues detected' && (
                                        <div className="space-y-3">
                                            <h5 className="text-xs font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                                                <Activity size={14} className="text-orange-500" /> Symptoms
                                            </h5>
                                            <div className="space-y-2">
                                                {diagnosis.symptoms.map((s, i) => (
                                                    <div key={i} className="flex items-start gap-3 text-xs text-muted-foreground p-3 bg-muted/30 rounded-xl border border-border">
                                                        <div className="mt-0.5 w-1.5 h-1.5 rounded-full bg-orange-400 flex-shrink-0" />
                                                        {s}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    <div className="space-y-4">
                                        <h5 className="text-xs font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2"><Zap size={14} className="text-yellow-500" /> Resolution Plan</h5>
                                        <p className="text-xs text-muted-foreground">{diagnosis.fix_summary}</p>
                                        <div className="space-y-3">
                                            {(diagnosis.fix_steps || []).filter(step => step.label).map((step, i) => (
                                                <div key={i} className="p-5 bg-muted/30 border border-border rounded-2xl hover:border-indigo-500/30 transition-all flex flex-col gap-4 group">
                                                    <div className="flex items-center justify-between">
                                                        <span className="text-[11px] font-bold text-foreground">{step.label}</span>
                                                        <span className="text-[9px] px-2 py-0.5 bg-indigo-500/10 text-indigo-600 rounded uppercase font-bold">{step.type}</span>
                                                    </div>

                                                    {step.reasoning && (
                                                        <div className="p-3 bg-indigo-50/50 border border-indigo-100/50 rounded-xl">
                                                            <div className="flex items-center gap-2 mb-1">
                                                                <Zap size={10} className="text-indigo-600" />
                                                                <span className="text-[9px] font-bold text-indigo-700 uppercase tracking-wider">Reasoning</span>
                                                            </div>
                                                            <p className="text-[11px] text-indigo-900/70 leading-relaxed italic">{step.reasoning}</p>
                                                        </div>
                                                    )}

                                                    {step.command && (
                                                        <div className="space-y-3">
                                                            <div className="flex flex-col gap-2">
                                                                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Proposed Fix:</span>
                                                                <div className="relative group">
                                                                    <code className="block w-full p-4 bg-slate-950 rounded-xl text-[11px] font-mono text-indigo-300 whitespace-pre-wrap break-all border border-indigo-500/20 shadow-inner">
                                                                        {step.command}
                                                                    </code>
                                                                </div>
                                                                <div className="flex justify-end gap-2">
                                                                    <button
                                                                        onClick={() => { navigator.clipboard.writeText(step.command); setCopiedCmd(i); setTimeout(() => setCopiedCmd(null), 2000); }}
                                                                        className={`p-2.5 border rounded-xl shadow-sm flex-shrink-0 transition-all ${copiedCmd === i ? 'bg-success/10 border-success/30 text-success' : 'bg-card border-border text-muted-foreground hover:text-indigo-600'}`}
                                                                        title="Copy to clipboard"
                                                                    >
                                                                        {copiedCmd === i ? <CheckCircle2 size={14} /> : <Command size={14} />}
                                                                    </button>
                                                                    {(step.command.toLowerCase().startsWith('kubectl') && !step.command.toLowerCase().includes(' edit ')) && (
                                                                        <button
                                                                            disabled={executingCmd !== null}
                                                                            onClick={() => handleExecuteCommand(step.command, i)}
                                                                            className={`p-2.5 border rounded-xl shadow-sm flex-shrink-0 transition-all flex items-center gap-2 ${executingCmd === i ? 'bg-indigo-500/10 border-indigo-500/30' : 'bg-card border-border text-indigo-600 hover:bg-indigo-50'}`}
                                                                            title="Execute on cluster"
                                                                        >
                                                                            {executingCmd === i ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
                                                                            <span className="text-[10px] font-bold">RUN</span>
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>

                                                            {executionResults[i] && (
                                                                <motion.div
                                                                    initial={{ opacity: 0, scale: 0.95 }}
                                                                    animate={{ opacity: 1, scale: 1 }}
                                                                    className={`rounded-xl border p-4 font-mono text-[10px] shadow-sm relative overflow-hidden group/console ${executionResults[i].success ? 'bg-emerald-50/50 border-emerald-200/50 text-emerald-800' : 'bg-rose-50/50 border-rose-200/50 text-rose-800'}`}
                                                                >
                                                                    <div className="flex justify-between items-center mb-3">
                                                                        <div className="flex items-center gap-2">
                                                                            <Terminal size={12} className="opacity-60" />
                                                                            <span className="font-bold uppercase tracking-widest text-[9px]">{executionResults[i].success ? 'Execution Success' : 'Execution Failed'}</span>
                                                                        </div>
                                                                        <button onClick={() => setExecutionResults(prev => { const n = { ...prev }; delete n[i]; return n; })} className="w-5 h-5 flex items-center justify-center rounded-full hover:bg-black/5 opacity-40 hover:opacity-100 transition-all">✕</button>
                                                                    </div>
                                                                    <div className="max-h-[150px] overflow-auto custom-scrollbar-thin">
                                                                        <pre className="whitespace-pre-wrap leading-relaxed">{executionResults[i].stdout || executionResults[i].stderr}</pre>
                                                                    </div>
                                                                    {executionResults[i].success && (
                                                                        <div className="mt-3 pt-3 border-t border-emerald-200/30 flex items-center gap-2">
                                                                            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                                                            <span className="text-[9px] font-bold opacity-60 uppercase italic">Health states re-polling...</span>
                                                                        </div>
                                                                    )}
                                                                </motion.div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    <div className="pt-8 border-t border-border grid grid-cols-2 gap-6">
                                        <div>
                                            <span className="text-[10px] font-bold text-muted-foreground uppercase block mb-2">Confidence</span>
                                            <div className="flex items-center gap-3">
                                                <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                                                    <motion.div initial={{ width: 0 }} animate={{ width: `${(diagnosis.confidence_score || 0) * 100}%` }} className="h-full bg-indigo-600" />
                                                </div>
                                                <span className="text-sm font-bold text-indigo-600">{((diagnosis.confidence_score || 0) * 100).toFixed(0)}%</span>
                                            </div>
                                        </div>
                                        <div>
                                            <span className="text-[10px] font-bold text-muted-foreground uppercase block mb-2">Risk Impact</span>
                                            <div className={`text-sm font-bold uppercase ${diagnosis.risk_level === 'High' ? 'text-red-500' : diagnosis.risk_level === 'Medium' ? 'text-yellow-500' : 'text-green-500'}`}>{diagnosis.risk_level}</div>
                                        </div>
                                    </div>
                                </motion.div>
                            ) : diagnosisError ? (
                                <div className="flex flex-col items-center justify-center h-64 gap-4 text-center">
                                    <div className="p-4 bg-error/10 rounded-full">
                                        <AlertCircle size={32} className="text-error" />
                                    </div>
                                    <h4 className="text-lg font-bold text-foreground">Diagnosis Failed</h4>
                                    <p className="text-sm text-muted-foreground max-w-xs">{diagnosisError}</p>
                                    <button
                                        onClick={() => runDiagnosis(selectedPod.name)}
                                        className="mt-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-bold hover:bg-indigo-700 transition-all active:scale-95"
                                    >
                                        Retry Diagnosis
                                    </button>
                                </div>
                            ) : null}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>



        </div>
    );
}

function NavItem({ icon, label, active, onClick, badge }) {
    return (
        <button
            onClick={onClick}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all group ${active
                ? 'bg-indigo-600 text-white shadow-xl shadow-indigo-500/20'
                : 'text-muted-foreground hover:bg-muted/80 hover:text-foreground'
                }`}
        >
            <div className={`${active ? 'text-white' : 'text-muted-foreground group-hover:text-indigo-500'}`}>
                {icon}
            </div>
            <span className="hidden lg:inline text-sm font-semibold tracking-tight leading-none flex-1 text-left">{label}</span>
            {badge != null && <span className={`hidden lg:inline text-[10px] font-bold px-1.5 py-0.5 rounded-md leading-none ${active ? 'bg-white/20 text-white' : 'bg-muted text-muted-foreground'}`}>{badge}</span>}
            {active && <div className={`ml-auto w-1 h-3 rounded-full hidden lg:block ${badge != null ? 'ml-1' : ''} bg-indigo-200`} />}
        </button>
    );
}

function StatsCard({ label, value, icon, trend, onClick, active }) {
    return (
        <motion.div
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}
            onClick={onClick}
            className={`bg-card border p-6 rounded-2xl shadow-sm hover:shadow-lg transition-all group cursor-pointer card-glow ${active ? 'border-indigo-500/40 ring-2 ring-indigo-500/10 shadow-indigo-500/10' : 'border-border'
                }`}
        >
            <div className="flex items-center justify-between mb-4">
                <motion.div
                    whileHover={{ rotate: [0, -10, 10, 0] }}
                    transition={{ duration: 0.5 }}
                    className="p-2.5 bg-muted rounded-xl transition-colors group-hover:bg-card group-hover:ring-1 group-hover:ring-border"
                >
                    {icon}
                </motion.div>
                {trend && (
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${trend === 'Critical' ? 'bg-red-500/10 text-red-500' :
                        trend === 'Good' ? 'bg-green-500/10 text-green-500' :
                            'bg-blue-500/10 text-blue-500'
                        }`}>
                        {trend}
                    </span>
                )}
            </div>
            <div className="text-2xl font-bold font-outfit text-foreground">{value}</div>
            <div className="text-[11px] font-medium text-muted-foreground mt-1 uppercase tracking-wider flex items-center gap-1">{label} <ChevronRight size={10} className="opacity-0 group-hover:opacity-100 transition-opacity" /></div>
        </motion.div>
    )
}

function BenchmarkMetric({ label, value, color = "text-indigo-600" }) {
    const percentage = ((value || 0) * 100).toFixed(0);
    return (
        <div className="space-y-2">
            <div className="flex justify-between items-end">
                <span className="text-[10px] font-bold text-muted-foreground uppercase">{label}</span>
                <span className={`text-sm font-bold ${color}`}>{percentage}%</span>
            </div>
            <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${percentage}%` }}
                    className={`h-full ${color.replace('text-', 'bg-')}`}
                />
            </div>
        </div>
    );
}

export default App;
