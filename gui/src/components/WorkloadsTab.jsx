import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Box, Layers, Server, ChevronDown, ChevronRight, RefreshCw, AlertTriangle, CheckCircle, Clock, Image, Shield } from 'lucide-react';

export default function WorkloadsTab({ api, selectedNS, onPodClick }) {
    const [deployments, setDeployments] = useState([]);
    const [statefulsets, setStatefulsets] = useState([]);
    const [daemonsets, setDaemonsets] = useState([]);
    const [pods, setPods] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expandedWorkloads, setExpandedWorkloads] = useState({});
    const [activeFilter, setActiveFilter] = useState('all');

    const fetchWorkloads = useCallback(async () => {
        if (!selectedNS) return;
        setLoading(true);
        try {
            const [depRes, stsRes, dsRes, podRes] = await Promise.all([
                api.get(`/namespaces/${selectedNS}/deployments`),
                api.get(`/namespaces/${selectedNS}/statefulsets`),
                api.get(`/namespaces/${selectedNS}/daemonsets`),
                api.get(`/namespaces/${selectedNS}/pods`),
            ]);
            setDeployments(depRes.data || []);
            setStatefulsets(stsRes.data || []);
            setDaemonsets(dsRes.data || []);
            setPods(podRes.data || []);
        } catch (err) {
            console.error('Failed to fetch workloads', err);
        } finally {
            setLoading(false);
        }
    }, [api, selectedNS]);

    useEffect(() => { fetchWorkloads(); }, [fetchWorkloads]);

    // Auto-refresh every 15s
    useEffect(() => {
        if (!selectedNS) return;
        const interval = setInterval(fetchWorkloads, 15000);
        return () => clearInterval(interval);
    }, [selectedNS, fetchWorkloads]);

    const toggleExpand = (id) => {
        setExpandedWorkloads(prev => ({ ...prev, [id]: !prev[id] }));
    };

    const getPodsForWorkload = (workloadName, workloadKind) => {
        return pods.filter(pod => {
            // Match pods by name prefix (e.g., "imagepull-app-xxx" belongs to "imagepull-app" deployment)
            return pod.name.startsWith(workloadName);
        });
    };

    const getStatusColor = (status) => {
        switch (status) {
            case 'Healthy': return 'var(--color-success)';
            case 'Degraded': case 'Progressing': return 'var(--color-warning)';
            case 'Unhealthy': case 'Waiting': return 'var(--color-danger)';
            default: return 'var(--text-secondary)';
        }
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case 'Healthy': return <CheckCircle size={16} />;
            case 'Degraded': case 'Progressing': return <Clock size={16} />;
            case 'Unhealthy': case 'Waiting': return <AlertTriangle size={16} />;
            default: return <Box size={16} />;
        }
    };

    const allWorkloads = [
        ...deployments.map(d => ({ ...d, kind: 'Deployment', status: d.rollout_status })),
        ...statefulsets.map(s => ({ ...s, kind: 'StatefulSet' })),
        ...daemonsets.map(d => ({ ...d, kind: 'DaemonSet', replicas: d.desired, ready_replicas: d.ready })),
    ];

    const filteredWorkloads = activeFilter === 'all'
        ? allWorkloads
        : activeFilter === 'unhealthy'
            ? allWorkloads.filter(w => w.status !== 'Healthy')
            : allWorkloads.filter(w => w.kind.toLowerCase() === activeFilter);

    const healthyCount = allWorkloads.filter(w => w.status === 'Healthy').length;
    const unhealthyCount = allWorkloads.length - healthyCount;

    const formatAge = (ageStr) => {
        try {
            const diff = Date.now() - new Date(ageStr).getTime();
            const hours = Math.floor(diff / 3600000);
            const days = Math.floor(hours / 24);
            if (days > 0) return `${days}d`;
            if (hours > 0) return `${hours}h`;
            return `${Math.floor(diff / 60000)}m`;
        } catch { return '–'; }
    };

    return (
        <div className="workloads-tab">
            {/* Header stats */}
            <div className="workloads-header">
                <div className="workloads-summary">
                    <div className="summary-stat">
                        <Layers size={18} />
                        <span className="stat-value">{allWorkloads.length}</span>
                        <span className="stat-label">Total Workloads</span>
                    </div>
                    <div className="summary-stat healthy">
                        <CheckCircle size={18} />
                        <span className="stat-value">{healthyCount}</span>
                        <span className="stat-label">Healthy</span>
                    </div>
                    {unhealthyCount > 0 && (
                        <div className="summary-stat unhealthy">
                            <AlertTriangle size={18} />
                            <span className="stat-value">{unhealthyCount}</span>
                            <span className="stat-label">Issues</span>
                        </div>
                    )}
                </div>
                <div className="workloads-actions">
                    <div className="filter-pills">
                        {['all', 'deployment', 'statefulset', 'daemonset', 'unhealthy'].map(f => (
                            <button
                                key={f}
                                className={`filter-pill ${activeFilter === f ? 'active' : ''}`}
                                onClick={() => setActiveFilter(f)}
                            >
                                {f === 'all' ? 'All' : f === 'unhealthy' ? '⚠ Issues' : f.charAt(0).toUpperCase() + f.slice(1) + 's'}
                            </button>
                        ))}
                    </div>
                    <button className="refresh-btn-sm" onClick={fetchWorkloads} disabled={loading}>
                        <RefreshCw size={16} className={loading ? 'spin' : ''} />
                    </button>
                </div>
            </div>

            {/* Workload cards */}
            <div className="workloads-list">
                <AnimatePresence>
                    {loading && allWorkloads.length === 0 ? (
                        <motion.div className="loading-state" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                            <RefreshCw size={24} className="spin" />
                            <span>Loading workloads...</span>
                        </motion.div>
                    ) : filteredWorkloads.length === 0 ? (
                        <motion.div className="empty-state" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                            <Layers size={40} />
                            <span>No workloads found</span>
                        </motion.div>
                    ) : (
                        filteredWorkloads.map((workload, idx) => {
                            const wlId = `${workload.kind}/${workload.name}`;
                            const isExpanded = expandedWorkloads[wlId];
                            const wlPods = getPodsForWorkload(workload.name, workload.kind);
                            const replicaPercent = workload.replicas > 0
                                ? ((workload.ready_replicas || 0) / workload.replicas) * 100 : 0;

                            return (
                                <motion.div
                                    key={wlId}
                                    className={`workload-card ${workload.status?.toLowerCase()}`}
                                    initial={{ opacity: 0, y: 20 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -10 }}
                                    transition={{ delay: idx * 0.05 }}
                                >
                                    <div className="workload-header" onClick={() => toggleExpand(wlId)}>
                                        <div className="workload-expand">
                                            {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                                        </div>
                                        <div className="workload-icon" style={{ color: getStatusColor(workload.status) }}>
                                            {workload.kind === 'Deployment' ? <Box size={22} /> :
                                                workload.kind === 'StatefulSet' ? <Server size={22} /> :
                                                    <Shield size={22} />}
                                        </div>
                                        <div className="workload-info">
                                            <div className="workload-name">{workload.name}</div>
                                            <div className="workload-meta">
                                                <span className="wl-kind-badge">{workload.kind}</span>
                                                {workload.strategy && (
                                                    <span className="wl-strategy">{workload.strategy}</span>
                                                )}
                                                <span className="wl-age">{formatAge(workload.age)}</span>
                                            </div>
                                        </div>
                                        <div className="workload-replica-gauge">
                                            <div className="replica-bar">
                                                <div
                                                    className="replica-fill"
                                                    style={{
                                                        width: `${replicaPercent}%`,
                                                        backgroundColor: getStatusColor(workload.status)
                                                    }}
                                                />
                                            </div>
                                            <span className="replica-text">
                                                {workload.ready_replicas || 0}/{workload.replicas} ready
                                            </span>
                                        </div>
                                        <div className="workload-status" style={{ color: getStatusColor(workload.status) }}>
                                            {getStatusIcon(workload.status)}
                                            <span>{workload.status}</span>
                                        </div>
                                    </div>

                                    {/* Images */}
                                    {workload.images && (
                                        <div className="workload-images">
                                            <Image size={12} />
                                            {workload.images.map((img, i) => (
                                                <span key={i} className="image-tag">{img}</span>
                                            ))}
                                        </div>
                                    )}

                                    {/* Expanded pod list */}
                                    <AnimatePresence>
                                        {isExpanded && (
                                            <motion.div
                                                className="workload-pods"
                                                initial={{ height: 0, opacity: 0 }}
                                                animate={{ height: 'auto', opacity: 1 }}
                                                exit={{ height: 0, opacity: 0 }}
                                                transition={{ duration: 0.2 }}
                                            >
                                                <div className="pods-header-row">
                                                    <span>Pod Name</span>
                                                    <span>Status</span>
                                                    <span>Restarts</span>
                                                    <span>Actions</span>
                                                </div>
                                                {wlPods.length === 0 ? (
                                                    <div className="no-pods">No pods found for this workload</div>
                                                ) : wlPods.map(pod => (
                                                    <div
                                                        key={pod.name}
                                                        className={`pod-row ${pod.is_healthy ? 'healthy' : 'unhealthy'}`}
                                                        onClick={() => onPodClick && onPodClick(pod)}
                                                    >
                                                        <span className="pod-name-cell">
                                                            <span className={`pod-dot ${pod.is_healthy ? 'green' : 'red'}`} />
                                                            {pod.name}
                                                        </span>
                                                        <span className={`pod-status-badge ${pod.is_healthy ? 'running' : 'error'}`}>
                                                            {pod.status}
                                                        </span>
                                                        <span className="pod-restarts">{pod.restarts}</span>
                                                        <button
                                                            className="diagnose-btn-sm"
                                                            onClick={(e) => { e.stopPropagation(); onPodClick && onPodClick(pod); }}
                                                        >
                                                            Diagnose
                                                        </button>
                                                    </div>
                                                ))}
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </motion.div>
                            );
                        })
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
