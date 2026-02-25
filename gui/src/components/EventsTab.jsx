import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, AlertTriangle, Info, AlertCircle, RefreshCw, Filter, Clock, Search } from 'lucide-react';

export default function EventsTab({ api, selectedNS }) {
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [typeFilter, setTypeFilter] = useState('all');
    const [searchQuery, setSearchQuery] = useState('');
    const [timeFilter, setTimeFilter] = useState('all');

    const fetchEvents = useCallback(async () => {
        if (!selectedNS) return;
        setLoading(true);
        try {
            const res = await api.get(`/namespaces/${selectedNS}/events`);
            setEvents(res.data || []);
        } catch (err) {
            console.error('Failed to fetch events', err);
        } finally {
            setLoading(false);
        }
    }, [api, selectedNS]);

    useEffect(() => { fetchEvents(); }, [fetchEvents]);

    // Auto-refresh every 10s for near-real-time
    useEffect(() => {
        if (!selectedNS) return;
        const interval = setInterval(fetchEvents, 10000);
        return () => clearInterval(interval);
    }, [selectedNS, fetchEvents]);

    const getTimeDiff = (timeStr) => {
        try {
            const diff = Date.now() - new Date(timeStr).getTime();
            const seconds = Math.floor(diff / 1000);
            if (seconds < 60) return `${seconds}s ago`;
            const minutes = Math.floor(seconds / 60);
            if (minutes < 60) return `${minutes}m ago`;
            const hours = Math.floor(minutes / 60);
            if (hours < 24) return `${hours}h ago`;
            return `${Math.floor(hours / 24)}d ago`;
        } catch { return '–'; }
    };

    const isWithinTimeFilter = (timeStr) => {
        if (timeFilter === 'all') return true;
        try {
            const diff = Date.now() - new Date(timeStr).getTime();
            const minutes = diff / 60000;
            if (timeFilter === '30m') return minutes <= 30;
            if (timeFilter === '1h') return minutes <= 60;
            if (timeFilter === '6h') return minutes <= 360;
            if (timeFilter === '24h') return minutes <= 1440;
        } catch { return true; }
        return true;
    };

    const filteredEvents = events.filter(e => {
        if (typeFilter !== 'all' && e.type.toLowerCase() !== typeFilter) return false;
        if (!isWithinTimeFilter(e.last_seen)) return false;
        if (searchQuery) {
            const q = searchQuery.toLowerCase();
            return e.message.toLowerCase().includes(q) ||
                e.object_name.toLowerCase().includes(q) ||
                e.reason.toLowerCase().includes(q);
        }
        return true;
    });

    const warningCount = events.filter(e => e.type === 'Warning').length;
    const recentWarnings = events.filter(e => {
        if (e.type !== 'Warning') return false;
        try {
            return (Date.now() - new Date(e.last_seen).getTime()) < 1800000; // 30 min
        } catch { return false; }
    }).length;

    const getEventIcon = (type) => {
        switch (type) {
            case 'Warning': return <AlertTriangle size={16} />;
            case 'Normal': return <Info size={16} />;
            default: return <Activity size={16} />;
        }
    };

    return (
        <div className="events-tab">
            {/* Incident summary banner */}
            {recentWarnings > 0 && (
                <motion.div
                    className="incident-banner"
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    <AlertCircle size={20} />
                    <div className="incident-info">
                        <strong>{recentWarnings} warning{recentWarnings > 1 ? 's' : ''}</strong> in the last 30 minutes
                    </div>
                    <button className="incident-action" onClick={() => { setTypeFilter('warning'); setTimeFilter('30m'); }}>
                        View Incidents
                    </button>
                </motion.div>
            )}

            {/* Controls */}
            <div className="events-controls">
                <div className="events-search">
                    <Search size={16} />
                    <input
                        type="text"
                        placeholder="Search events..."
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                    />
                </div>
                <div className="events-filters">
                    <div className="filter-group">
                        <Filter size={14} />
                        {['all', 'warning', 'normal'].map(f => (
                            <button
                                key={f}
                                className={`filter-pill ${typeFilter === f ? 'active' : ''}`}
                                onClick={() => setTypeFilter(f)}
                            >
                                {f === 'all' ? 'All Types' : f.charAt(0).toUpperCase() + f.slice(1)}
                                {f === 'warning' && warningCount > 0 && (
                                    <span className="filter-count">{warningCount}</span>
                                )}
                            </button>
                        ))}
                    </div>
                    <div className="filter-group">
                        <Clock size={14} />
                        {['all', '30m', '1h', '6h', '24h'].map(t => (
                            <button
                                key={t}
                                className={`filter-pill ${timeFilter === t ? 'active' : ''}`}
                                onClick={() => setTimeFilter(t)}
                            >
                                {t === 'all' ? 'All Time' : `Last ${t}`}
                            </button>
                        ))}
                    </div>
                </div>
                <button className="refresh-btn-sm" onClick={fetchEvents} disabled={loading}>
                    <RefreshCw size={16} className={loading ? 'spin' : ''} />
                </button>
            </div>

            {/* Events timeline */}
            <div className="events-timeline">
                <AnimatePresence>
                    {loading && events.length === 0 ? (
                        <motion.div className="loading-state" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                            <RefreshCw size={24} className="spin" />
                            <span>Loading events...</span>
                        </motion.div>
                    ) : filteredEvents.length === 0 ? (
                        <motion.div className="empty-state" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                            <Activity size={40} />
                            <span>No events found{searchQuery ? ' matching your search' : ''}</span>
                        </motion.div>
                    ) : (
                        filteredEvents.map((event, idx) => (
                            <motion.div
                                key={`${event.object_name}-${event.reason}-${event.last_seen}-${idx}`}
                                className={`event-card ${event.type.toLowerCase()}`}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: Math.min(idx * 0.03, 0.5) }}
                            >
                                <div className="event-timeline-marker">
                                    <div className={`event-dot ${event.type.toLowerCase()}`} />
                                    {idx < filteredEvents.length - 1 && <div className="event-line" />}
                                </div>
                                <div className="event-content">
                                    <div className="event-header">
                                        <span className={`event-type-badge ${event.type.toLowerCase()}`}>
                                            {getEventIcon(event.type)}
                                            {event.reason}
                                        </span>
                                        <span className="event-object">
                                            <span className="event-kind">{event.object_kind}</span>
                                            {event.object_name}
                                        </span>
                                        <span className="event-time">
                                            {getTimeDiff(event.last_seen)}
                                            {event.count > 1 && <span className="event-count">×{event.count}</span>}
                                        </span>
                                    </div>
                                    <div className="event-message">{event.message}</div>
                                    {event.source && (
                                        <div className="event-source">Source: {event.source}</div>
                                    )}
                                </div>
                            </motion.div>
                        ))
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
