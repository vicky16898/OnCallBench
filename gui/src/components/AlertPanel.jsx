import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Bell,
    X,
    AlertTriangle,
    AlertCircle,
    Info,
    CheckCircle2,
    Activity,
    Clock,
    Trash2,
    ChevronRight,
    Shield,
    Loader2,
    Zap
} from 'lucide-react';

function AlertPanel({ api, onDiagnose }) {
    const [alerts, setAlerts] = useState([]);
    const [isOpen, setIsOpen] = useState(false);
    const [dismissing, setDismissing] = useState(null);
    const panelRef = useRef(null);
    const prevCountRef = useRef(0);
    const [flashNew, setFlashNew] = useState(false);

    // Fetch alerts on interval
    useEffect(() => {
        const fetchAlerts = async () => {
            try {
                const res = await api.get('/alerts');
                setAlerts(res.data || []);
            } catch (err) {
                // Silently fail — watcher may not be active
            }
        };
        fetchAlerts();
        const interval = setInterval(fetchAlerts, 10000);
        return () => clearInterval(interval);
    }, [api]);

    // Flash the bell when new alerts arrive
    const activeAlerts = alerts.filter(a => !a.dismissed && !a.resolved);
    const resolvedAlerts = alerts.filter(a => a.resolved && !a.dismissed);
    const activeCount = activeAlerts.length;

    useEffect(() => {
        if (activeCount > prevCountRef.current && prevCountRef.current >= 0) {
            setFlashNew(true);
            setTimeout(() => setFlashNew(false), 2000);
        }
        prevCountRef.current = activeCount;
    }, [activeCount]);

    // Close on click outside
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (panelRef.current && !panelRef.current.contains(e.target)) {
                setIsOpen(false);
            }
        };
        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside);
        }
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [isOpen]);

    // Close on Escape
    useEffect(() => {
        const handleKey = (e) => {
            if (e.key === 'Escape') setIsOpen(false);
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, []);

    const handleDismiss = async (alertId, e) => {
        e.stopPropagation();
        setDismissing(alertId);
        try {
            await api.post(`/alerts/${alertId}/dismiss`);
            setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, dismissed: true } : a));
        } catch (err) {
            console.error('Failed to dismiss alert', err);
        } finally {
            setDismissing(null);
        }
    };

    const handleDismissAll = async () => {
        try {
            await api.post('/alerts/dismiss-all');
            setAlerts(prev => prev.map(a => ({ ...a, dismissed: true })));
        } catch (err) {
            console.error('Failed to dismiss all', err);
        }
    };

    const handleAlertClick = (alert) => {
        if (alert.resource_kind === 'Pod' && onDiagnose) {
            onDiagnose(alert.resource_name, alert.namespace);
            setIsOpen(false);
        }
    };

    const formatTimeAgo = (iso) => {
        if (!iso) return '';
        try {
            const diff = Date.now() - new Date(iso).getTime();
            const secs = Math.floor(diff / 1000);
            if (secs < 60) return `${secs}s ago`;
            const mins = Math.floor(secs / 60);
            if (mins < 60) return `${mins}m ago`;
            const hours = Math.floor(mins / 60);
            if (hours < 24) return `${hours}h ago`;
            return `${Math.floor(hours / 24)}d ago`;
        } catch { return ''; }
    };

    const getSeverityConfig = (severity) => {
        switch (severity) {
            case 'critical':
                return {
                    icon: <AlertCircle size={14} />,
                    color: 'text-red-500',
                    bg: 'bg-red-500/10',
                    border: 'border-red-500/20',
                    dot: 'bg-red-500',
                    label: 'CRITICAL'
                };
            case 'warning':
                return {
                    icon: <AlertTriangle size={14} />,
                    color: 'text-amber-500',
                    bg: 'bg-amber-500/10',
                    border: 'border-amber-500/20',
                    dot: 'bg-amber-500',
                    label: 'WARNING'
                };
            default:
                return {
                    icon: <Info size={14} />,
                    color: 'text-blue-500',
                    bg: 'bg-blue-500/10',
                    border: 'border-blue-500/20',
                    dot: 'bg-blue-500',
                    label: 'INFO'
                };
        }
    };

    const criticalCount = activeAlerts.filter(a => a.severity === 'critical').length;

    return (
        <div className="relative" ref={panelRef}>
            {/* Bell Button */}
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`relative p-2 rounded-lg border transition-all duration-200 ${isOpen
                        ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-600'
                        : activeCount > 0
                            ? 'bg-card border-border text-foreground hover:bg-muted hover:shadow-sm'
                            : 'bg-card border-border text-muted-foreground hover:text-foreground hover:bg-muted hover:shadow-sm'
                    } ${flashNew ? 'alert-bell-flash' : ''}`}
                title={`${activeCount} active alert${activeCount !== 1 ? 's' : ''}`}
            >
                <Bell size={18} className={activeCount > 0 && criticalCount > 0 ? 'text-red-500' : ''} />

                {/* Badge */}
                <AnimatePresence>
                    {activeCount > 0 && (
                        <motion.div
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            exit={{ scale: 0 }}
                            className={`absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] rounded-full flex items-center justify-center text-[9px] font-bold text-white px-1 ${criticalCount > 0 ? 'bg-red-500' : 'bg-amber-500'
                                }`}
                        >
                            {activeCount > 99 ? '99+' : activeCount}
                        </motion.div>
                    )}
                </AnimatePresence>
            </button>

            {/* Dropdown Panel */}
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, y: 8, scale: 0.96 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 8, scale: 0.96 }}
                        transition={{ duration: 0.15, ease: 'easeOut' }}
                        className="alert-panel-dropdown"
                    >
                        {/* Header */}
                        <div className="alert-panel-header">
                            <div className="flex items-center gap-2">
                                <Shield size={16} className="text-indigo-500" />
                                <span className="text-xs font-bold text-foreground">Proactive Alerts</span>
                                {activeCount > 0 && (
                                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${criticalCount > 0 ? 'bg-red-500/10 text-red-500' : 'bg-amber-500/10 text-amber-500'
                                        }`}>
                                        {activeCount} active
                                    </span>
                                )}
                            </div>
                            <div className="flex items-center gap-1">
                                {activeCount > 0 && (
                                    <button
                                        onClick={handleDismissAll}
                                        className="text-[10px] text-muted-foreground hover:text-foreground px-2 py-1 rounded-md hover:bg-muted transition-colors"
                                        title="Dismiss all"
                                    >
                                        Clear all
                                    </button>
                                )}
                                <button
                                    onClick={() => setIsOpen(false)}
                                    className="p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    <X size={14} />
                                </button>
                            </div>
                        </div>

                        {/* Alert List */}
                        <div className="alert-panel-body custom-scrollbar">
                            {activeAlerts.length === 0 && resolvedAlerts.length === 0 ? (
                                <div className="alert-panel-empty">
                                    <CheckCircle2 size={32} className="text-emerald-500 mx-auto mb-3" />
                                    <p className="text-xs font-semibold text-foreground">All clear</p>
                                    <p className="text-[10px] text-muted-foreground mt-1">
                                        The event watcher is monitoring your cluster. Anomalies will appear here automatically.
                                    </p>
                                </div>
                            ) : (
                                <>
                                    {/* Active Alerts */}
                                    {activeAlerts.map((alert) => {
                                        const sev = getSeverityConfig(alert.severity);
                                        const isPod = alert.resource_kind === 'Pod';
                                        return (
                                            <motion.div
                                                key={alert.id}
                                                layout
                                                initial={{ opacity: 0, x: -10 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                exit={{ opacity: 0, x: 10, height: 0 }}
                                                className={`alert-item ${sev.border} ${isPod ? 'cursor-pointer' : ''}`}
                                                onClick={() => handleAlertClick(alert)}
                                            >
                                                <div className="alert-item-top">
                                                    <div className="flex items-center gap-2 flex-1 min-w-0">
                                                        <div className={`alert-severity-dot ${sev.dot}`} />
                                                        <span className={`text-[9px] font-bold uppercase tracking-wider ${sev.color}`}>
                                                            {sev.label}
                                                        </span>
                                                        {alert.count > 1 && (
                                                            <span className="text-[9px] font-bold text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">
                                                                ×{alert.count}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-1.5">
                                                        <span className="text-[9px] text-muted-foreground whitespace-nowrap flex items-center gap-1">
                                                            <Clock size={9} />
                                                            {formatTimeAgo(alert.updated_at)}
                                                        </span>
                                                        <button
                                                            onClick={(e) => handleDismiss(alert.id, e)}
                                                            disabled={dismissing === alert.id}
                                                            className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                                                            title="Dismiss"
                                                        >
                                                            {dismissing === alert.id
                                                                ? <Loader2 size={12} className="animate-spin" />
                                                                : <X size={12} />
                                                            }
                                                        </button>
                                                    </div>
                                                </div>
                                                <div className="alert-item-title">{alert.title}</div>
                                                <div className="alert-item-message">{alert.message}</div>
                                                <div className="alert-item-meta">
                                                    <span className="text-[9px] text-muted-foreground">
                                                        {alert.resource_kind}/{alert.resource_name}
                                                    </span>
                                                    <span className="text-[9px] text-indigo-500 font-medium">
                                                        {alert.namespace}
                                                    </span>
                                                    {isPod && (
                                                        <span className="text-[9px] font-bold text-indigo-600 flex items-center gap-0.5 ml-auto">
                                                            Diagnose <ChevronRight size={10} />
                                                        </span>
                                                    )}
                                                </div>
                                            </motion.div>
                                        );
                                    })}

                                    {/* Resolved Alerts */}
                                    {resolvedAlerts.length > 0 && (
                                        <>
                                            <div className="alert-section-divider">
                                                <CheckCircle2 size={10} />
                                                <span>Resolved ({resolvedAlerts.length})</span>
                                            </div>
                                            {resolvedAlerts.slice(0, 10).map((alert) => (
                                                <div key={alert.id} className="alert-item resolved">
                                                    <div className="alert-item-top">
                                                        <div className="flex items-center gap-2 flex-1 min-w-0">
                                                            <CheckCircle2 size={12} className="text-emerald-500" />
                                                            <span className="text-[10px] font-medium text-muted-foreground line-through">
                                                                {alert.title}
                                                            </span>
                                                        </div>
                                                        <span className="text-[9px] text-emerald-500 font-medium">
                                                            {formatTimeAgo(alert.resolved_at)}
                                                        </span>
                                                    </div>
                                                </div>
                                            ))}
                                        </>
                                    )}
                                </>
                            )}
                        </div>

                        {/* Footer */}
                        <div className="alert-panel-footer">
                            <div className="flex items-center gap-1.5">
                                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                <span className="text-[9px] text-muted-foreground">Watcher active</span>
                            </div>
                            <span className="text-[9px] text-muted-foreground">
                                {alerts.length} total events tracked
                            </span>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

export default AlertPanel;
