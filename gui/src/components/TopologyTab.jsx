import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import { RefreshCw, ZoomIn, ZoomOut, Maximize, Globe, Box, Server, Shield, Hexagon } from 'lucide-react';

export default function TopologyTab({ api, selectedNS }) {
    const [topology, setTopology] = useState({ nodes: [], edges: [] });
    const [loading, setLoading] = useState(true);
    const [zoom, setZoom] = useState(1);
    const [pan, setPan] = useState({ x: 0, y: 0 });
    const [hoveredNode, setHoveredNode] = useState(null);
    const [selectedNode, setSelectedNode] = useState(null);
    const svgRef = useRef(null);
    const isDragging = useRef(false);
    const dragStart = useRef({ x: 0, y: 0 });

    const fetchTopology = useCallback(async () => {
        if (!selectedNS) return;
        setLoading(true);
        try {
            const res = await api.get(`/namespaces/${selectedNS}/topology`);
            setTopology(res.data || { nodes: [], edges: [] });
        } catch (err) {
            console.error('Failed to fetch topology', err);
        } finally {
            setLoading(false);
        }
    }, [api, selectedNS]);

    useEffect(() => { fetchTopology(); }, [fetchTopology]);

    // Layout: organize nodes into columns by kind
    const layout = useMemo(() => {
        const { nodes, edges } = topology;
        if (nodes.length === 0) return { positionedNodes: [], positionedEdges: [] };

        const kindOrder = ['Service', 'Deployment', 'StatefulSet', 'DaemonSet', 'Pod'];
        const columns = {};
        kindOrder.forEach((kind, idx) => { columns[kind] = idx; });

        // Group by kind
        const groups = {};
        nodes.forEach(n => {
            const col = columns[n.kind] ?? 4;
            if (!groups[col]) groups[col] = [];
            groups[col].push(n);
        });

        const colWidth = 280;
        const rowHeight = 80;
        const startX = 60;
        const startY = 60;

        const posMap = {};
        const positionedNodes = [];

        Object.entries(groups).sort(([a], [b]) => a - b).forEach(([col, nodesInCol]) => {
            const colNum = parseInt(col);
            const totalHeight = nodesInCol.length * rowHeight;
            const offsetY = startY;

            nodesInCol.forEach((node, rowIdx) => {
                const x = startX + colNum * colWidth;
                const y = offsetY + rowIdx * rowHeight;
                posMap[node.id] = { x: x + 90, y: y + 25 }; // center of node
                positionedNodes.push({ ...node, x, y });
            });
        });

        const positionedEdges = edges.map(e => ({
            ...e,
            fromPos: posMap[e.from],
            toPos: posMap[e.to],
        })).filter(e => e.fromPos && e.toPos);

        return { positionedNodes, positionedEdges };
    }, [topology]);

    const getKindIcon = (kind) => {
        switch (kind) {
            case 'Service': return <Globe size={16} />;
            case 'Deployment': return <Box size={16} />;
            case 'StatefulSet': return <Server size={16} />;
            case 'DaemonSet': return <Shield size={16} />;
            case 'Pod': return <Hexagon size={16} />;
            default: return <Box size={16} />;
        }
    };

    const getStatusColor = (status) => {
        switch (status) {
            case 'healthy': return '#10b981';
            case 'degraded': case 'warning': return '#f59e0b';
            case 'unhealthy': return '#ef4444';
            default: return '#6b7280';
        }
    };

    const getKindColor = (kind) => {
        switch (kind) {
            case 'Service': return '#8b5cf6';
            case 'Deployment': return '#3b82f6';
            case 'StatefulSet': return '#06b6d4';
            case 'DaemonSet': return '#f59e0b';
            case 'Pod': return '#6b7280';
            default: return '#6b7280';
        }
    };

    // Find connected nodes for highlighting
    const connectedNodes = useMemo(() => {
        if (!hoveredNode && !selectedNode) return new Set();
        const target = selectedNode || hoveredNode;
        const connected = new Set([target]);
        topology.edges.forEach(e => {
            if (e.from === target) connected.add(e.to);
            if (e.to === target) connected.add(e.from);
        });
        return connected;
    }, [hoveredNode, selectedNode, topology.edges]);

    const svgWidth = Math.max(1400, (layout.positionedNodes.length * 60) + 400);
    const svgHeight = Math.max(600, (layout.positionedNodes.length * 30) + 200);

    // Pan & zoom handlers
    const handleMouseDown = (e) => {
        if (e.target === svgRef.current || e.target.tagName === 'svg' || e.target.tagName === 'rect') {
            isDragging.current = true;
            dragStart.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
        }
    };
    const handleMouseMove = (e) => {
        if (isDragging.current) {
            setPan({ x: e.clientX - dragStart.current.x, y: e.clientY - dragStart.current.y });
        }
    };
    const handleMouseUp = () => { isDragging.current = false; };
    const handleWheel = (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.1 : 0.1;
        setZoom(prev => Math.max(0.3, Math.min(2, prev + delta)));
    };

    return (
        <div className="topology-tab">
            {/* Controls */}
            <div className="topology-controls">
                <div className="topology-legend">
                    {['Service', 'Deployment', 'StatefulSet', 'DaemonSet', 'Pod'].map(kind => (
                        <span key={kind} className="legend-item">
                            <span className="legend-dot" style={{ backgroundColor: getKindColor(kind) }} />
                            {kind}
                        </span>
                    ))}
                    <span className="legend-divider">|</span>
                    <span className="legend-item"><span className="legend-dot" style={{ backgroundColor: '#10b981' }} />Healthy</span>
                    <span className="legend-item"><span className="legend-dot" style={{ backgroundColor: '#ef4444' }} />Unhealthy</span>
                </div>
                <div className="topology-actions">
                    <button onClick={() => setZoom(z => Math.min(2, z + 0.2))}><ZoomIn size={16} /></button>
                    <span className="zoom-label">{Math.round(zoom * 100)}%</span>
                    <button onClick={() => setZoom(z => Math.max(0.3, z - 0.2))}><ZoomOut size={16} /></button>
                    <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}><Maximize size={16} /></button>
                    <button className="refresh-btn-sm" onClick={fetchTopology} disabled={loading}>
                        <RefreshCw size={16} className={loading ? 'spin' : ''} />
                    </button>
                </div>
            </div>

            {/* Graph */}
            <div className="topology-canvas"
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                onWheel={handleWheel}
            >
                {loading && topology.nodes.length === 0 ? (
                    <div className="loading-state">
                        <RefreshCw size={24} className="spin" />
                        <span>Building topology graph...</span>
                    </div>
                ) : topology.nodes.length === 0 ? (
                    <div className="empty-state">
                        <Globe size={40} />
                        <span>No resources found to map</span>
                    </div>
                ) : (
                    <svg
                        ref={svgRef}
                        width="100%"
                        height="100%"
                        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
                        style={{ cursor: isDragging.current ? 'grabbing' : 'grab' }}
                    >
                        <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
                            {/* Column headers */}
                            {['Services', 'Deployments', 'StatefulSets', 'DaemonSets', 'Pods'].map((label, idx) => (
                                <text key={label} x={60 + idx * 280 + 90} y={30}
                                    textAnchor="middle" className="topo-column-header"
                                    fill="var(--text-secondary)" fontSize="13" fontWeight="600">
                                    {label}
                                </text>
                            ))}

                            {/* Edges */}
                            {layout.positionedEdges.map((edge, idx) => {
                                const isHighlighted = connectedNodes.size === 0 ||
                                    (connectedNodes.has(edge.from) && connectedNodes.has(edge.to));
                                const midX = (edge.fromPos.x + edge.toPos.x) / 2;
                                return (
                                    <path
                                        key={idx}
                                        d={`M ${edge.fromPos.x} ${edge.fromPos.y} C ${midX} ${edge.fromPos.y}, ${midX} ${edge.toPos.y}, ${edge.toPos.x} ${edge.toPos.y}`}
                                        fill="none"
                                        stroke={isHighlighted ? 'var(--color-primary)' : 'var(--border-color)'}
                                        strokeWidth={isHighlighted ? 2 : 1}
                                        strokeDasharray={isHighlighted ? 'none' : '4,4'}
                                        opacity={connectedNodes.size > 0 && !isHighlighted ? 0.15 : 0.6}
                                        className="topo-edge"
                                    />
                                );
                            })}

                            {/* Nodes */}
                            {layout.positionedNodes.map(node => {
                                const isHighlighted = connectedNodes.size === 0 || connectedNodes.has(node.id);
                                const isSelected = selectedNode === node.id;
                                const kindColor = getKindColor(node.kind);
                                const statusColor = getStatusColor(node.status);
                                const nodeWidth = 180;
                                const nodeHeight = 50;

                                return (
                                    <g key={node.id}
                                        transform={`translate(${node.x}, ${node.y})`}
                                        onMouseEnter={() => setHoveredNode(node.id)}
                                        onMouseLeave={() => setHoveredNode(null)}
                                        onClick={() => setSelectedNode(prev => prev === node.id ? null : node.id)}
                                        style={{ cursor: 'pointer' }}
                                        opacity={isHighlighted ? 1 : 0.25}
                                    >
                                        {/* Background */}
                                        <rect
                                            x={0} y={0} width={nodeWidth} height={nodeHeight}
                                            rx={8} ry={8}
                                            fill="var(--card-bg)"
                                            stroke={isSelected ? kindColor : statusColor}
                                            strokeWidth={isSelected ? 2.5 : 1.5}
                                            className="topo-node-bg"
                                        />
                                        {/* Kind indicator stripe */}
                                        <rect
                                            x={0} y={0} width={4} height={nodeHeight}
                                            rx={2} ry={0}
                                            fill={kindColor}
                                        />
                                        {/* Status dot */}
                                        <circle cx={nodeWidth - 14} cy={14} r={5} fill={statusColor} />

                                        {/* Label */}
                                        <text x={14} y={20} fontSize="12" fontWeight="600"
                                            fill="var(--text-primary)" className="topo-node-label">
                                            {node.label.length > 20 ? node.label.slice(0, 18) + '…' : node.label}
                                        </text>
                                        {/* Detail */}
                                        <text x={14} y={38} fontSize="10"
                                            fill="var(--text-secondary)" className="topo-node-detail">
                                            {node.kind} · {node.detail}
                                        </text>
                                    </g>
                                );
                            })}
                        </g>
                    </svg>
                )}
            </div>

            {/* Detail panel */}
            {selectedNode && (() => {
                const node = topology.nodes.find(n => n.id === selectedNode);
                if (!node) return null;
                const inEdges = topology.edges.filter(e => e.to === node.id);
                const outEdges = topology.edges.filter(e => e.from === node.id);
                return (
                    <motion.div className="topology-detail-panel"
                        initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                        <h4 style={{ color: getKindColor(node.kind) }}>
                            {getKindIcon(node.kind)} {node.label}
                        </h4>
                        <div className="detail-row">
                            <span className="detail-label">Kind</span>
                            <span className="detail-value">{node.kind}</span>
                        </div>
                        <div className="detail-row">
                            <span className="detail-label">Status</span>
                            <span className="detail-value" style={{ color: getStatusColor(node.status) }}>{node.status}</span>
                        </div>
                        <div className="detail-row">
                            <span className="detail-label">Detail</span>
                            <span className="detail-value">{node.detail}</span>
                        </div>
                        {inEdges.length > 0 && (
                            <div className="detail-connections">
                                <span className="detail-label">Receives from:</span>
                                {inEdges.map((e, i) => <span key={i} className="label-chip">{e.from}</span>)}
                            </div>
                        )}
                        {outEdges.length > 0 && (
                            <div className="detail-connections">
                                <span className="detail-label">Connects to:</span>
                                {outEdges.map((e, i) => <span key={i} className="label-chip">{e.to}</span>)}
                            </div>
                        )}
                        <button className="close-detail" onClick={() => setSelectedNode(null)}>×</button>
                    </motion.div>
                );
            })()}
        </div>
    );
}
