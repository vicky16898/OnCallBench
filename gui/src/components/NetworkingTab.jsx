import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Globe, Network, Shield, RefreshCw, ExternalLink, Lock, Unlock, Server, ArrowRight, ChevronDown, Terminal, Code } from 'lucide-react';

export default function NetworkingTab({ api, selectedNS }) {
    const [services, setServices] = useState([]);
    const [ingresses, setIngresses] = useState([]);
    const [netpolicies, setNetpolicies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [activeSection, setActiveSection] = useState('services');
    const [expandedApiRef, setExpandedApiRef] = useState({});

    const toggleApiRef = (id) => {
        setExpandedApiRef(prev => ({ ...prev, [id]: !prev[id] }));
    };

    const fetchNetworking = useCallback(async () => {
        if (!selectedNS) return;
        setLoading(true);
        try {
            const [svcRes, ingRes, npRes] = await Promise.all([
                api.get(`/namespaces/${selectedNS}/services`),
                api.get(`/namespaces/${selectedNS}/ingresses`),
                api.get(`/namespaces/${selectedNS}/networkpolicies`),
            ]);
            setServices(svcRes.data || []);
            setIngresses(ingRes.data || []);
            setNetpolicies(npRes.data || []);
        } catch (err) {
            console.error('Failed to fetch networking data', err);
        } finally {
            setLoading(false);
        }
    }, [api, selectedNS]);

    useEffect(() => { fetchNetworking(); }, [fetchNetworking]);

    const formatAge = (creationTimestamp) => {
        if (!creationTimestamp || creationTimestamp === 'None') return 'N/A';
        try {
            const created = new Date(creationTimestamp);
            if (isNaN(created.getTime())) return 'N/A';
            const diff = Date.now() - created.getTime();
            const secs = Math.floor(diff / 1000);
            if (secs < 60) return `${secs}s`;
            const mins = Math.floor(secs / 60);
            if (mins < 60) return `${mins}m`;
            const hours = Math.floor(mins / 60);
            if (hours < 24) return `${hours}h`;
            return `${Math.floor(hours / 24)}d`;
        } catch (e) {
            return 'N/A';
        }
    };

    return (
        <div className="networking-tab">
            {/* Section tabs */}
            <div className="networking-sections">
                <button
                    className={`section-btn ${activeSection === 'services' ? 'active' : ''}`}
                    onClick={() => setActiveSection('services')}
                >
                    <Globe size={16} />
                    Services
                    <span className="section-count">{services.length}</span>
                </button>
                <button
                    className={`section-btn ${activeSection === 'ingresses' ? 'active' : ''}`}
                    onClick={() => setActiveSection('ingresses')}
                >
                    <ExternalLink size={16} />
                    Ingresses
                    <span className="section-count">{ingresses.length}</span>
                </button>
                <button
                    className={`section-btn ${activeSection === 'policies' ? 'active' : ''}`}
                    onClick={() => setActiveSection('policies')}
                >
                    <Shield size={16} />
                    Network Policies
                    <span className="section-count">{netpolicies.length}</span>
                </button>
                <button className="refresh-btn-sm" onClick={fetchNetworking} disabled={loading}
                    style={{ marginLeft: 'auto' }}>
                    <RefreshCw size={16} className={loading ? 'spin' : ''} />
                </button>
            </div>

            {/* Services */}
            <AnimatePresence mode="wait">
                {activeSection === 'services' && (
                    <motion.div key="services" className="networking-content"
                        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                        {services.length === 0 ? (
                            <div className="empty-state"><Globe size={40} /><span>No services found</span></div>
                        ) : (
                            <div className="resource-grid">
                                {services.map((svc, idx) => (
                                    <motion.div key={svc.name} className="resource-card service-card"
                                        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: idx * 0.05 }}>
                                        <div className="resource-card-header">
                                            <Globe size={20} />
                                            <div className="resource-card-title">
                                                <h4>{svc.name}</h4>
                                                <span className="resource-type-badge">{svc.type}</span>
                                            </div>
                                            <span className="resource-age">{formatAge(svc.age)}</span>
                                        </div>

                                        <div className="resource-details">
                                            <div className="detail-row">
                                                <span className="detail-label">Cluster IP</span>
                                                <code className="detail-value">{svc.cluster_ip}</code>
                                            </div>
                                            <div className="detail-row">
                                                <span className="detail-label">Endpoints</span>
                                                <span className={`detail-value ${svc.endpoint_count > 0 ? 'green' : 'red'}`}>
                                                    {svc.endpoint_count} active
                                                </span>
                                            </div>
                                        </div>

                                        {/* Ports */}
                                        <div className="ports-list">
                                            {svc.ports.map((p, i) => (
                                                <div key={i} className="port-badge">
                                                    <span className="port-name">{p.name || p.protocol}</span>
                                                    <span className="port-mapping">
                                                        {p.port}
                                                        <ArrowRight size={12} />
                                                        {p.target_port}
                                                    </span>
                                                    {p.node_port && <span className="node-port">NodePort: {p.node_port}</span>}
                                                </div>
                                            ))}
                                        </div>

                                        {/* Selector */}
                                        {Object.keys(svc.selector).length > 0 && (
                                            <div className="selector-labels">
                                                <span className="selector-label-title">Selector:</span>
                                                {Object.entries(svc.selector).map(([k, v]) => (
                                                    <span key={k} className="label-chip">{k}={v}</span>
                                                ))}
                                            </div>
                                        )}

                                        {/* API Source */}
                                        <div className="api-source-section">
                                            <button className="api-source-toggle" onClick={() => toggleApiRef(`svc-${svc.name}`)}>
                                                <Code size={12} />
                                                <span>K8s API Source</span>
                                                <ChevronDown size={14} className={expandedApiRef[`svc-${svc.name}`] ? 'chevron-open' : ''} />
                                            </button>
                                            {expandedApiRef[`svc-${svc.name}`] && (
                                                <motion.div className="api-source-content" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} transition={{ duration: 0.2 }}>
                                                    <div className="api-cmd">
                                                        <Terminal size={11} />
                                                        <code>kubectl get svc {svc.name} -n {selectedNS} -o yaml</code>
                                                    </div>
                                                    <div className="api-path">
                                                        <span className="api-method">GET</span>
                                                        <code>/api/v1/namespaces/{selectedNS}/services/{svc.name}</code>
                                                    </div>
                                                    <div className="api-field-map">
                                                        <div className="field-row">
                                                            <span className="field-path">.spec.type</span>
                                                            <span className="field-arrow">→</span>
                                                            <span className="field-val">{svc.type}</span>
                                                        </div>
                                                        <div className="field-row">
                                                            <span className="field-path">.spec.clusterIP</span>
                                                            <span className="field-arrow">→</span>
                                                            <span className="field-val">{svc.cluster_ip}</span>
                                                        </div>
                                                        {svc.ports.map((p, i) => (
                                                            <div key={i} className="field-row">
                                                                <span className="field-path">.spec.ports[{i}].port</span>
                                                                <span className="field-arrow">→</span>
                                                                <span className="field-val">{p.port}</span>
                                                            </div>
                                                        ))}
                                                        {svc.ports.map((p, i) => p.node_port && (
                                                            <div key={`np-${i}`} className="field-row">
                                                                <span className="field-path">.spec.ports[{i}].nodePort</span>
                                                                <span className="field-arrow">→</span>
                                                                <span className="field-val">{p.node_port}</span>
                                                            </div>
                                                        ))}
                                                        <div className="field-row">
                                                            <span className="field-path">.spec.selector</span>
                                                            <span className="field-arrow">→</span>
                                                            <span className="field-val">{JSON.stringify(svc.selector)}</span>
                                                        </div>
                                                    </div>
                                                    <div className="api-endpoint-info">
                                                        <div className="api-cmd">
                                                            <Terminal size={11} />
                                                            <code>kubectl get endpoints {svc.name} -n {selectedNS}</code>
                                                        </div>
                                                        <div className="api-path">
                                                            <span className="api-method">GET</span>
                                                            <code>/api/v1/namespaces/{selectedNS}/endpoints/{svc.name}</code>
                                                        </div>
                                                        <div className="field-row">
                                                            <span className="field-path">.subsets[].addresses | length</span>
                                                            <span className="field-arrow">→</span>
                                                            <span className="field-val">{svc.endpoint_count} endpoints</span>
                                                        </div>
                                                    </div>
                                                </motion.div>
                                            )}
                                        </div>
                                    </motion.div>
                                ))}
                            </div>
                        )}
                    </motion.div>
                )}

                {activeSection === 'ingresses' && (
                    <motion.div key="ingresses" className="networking-content"
                        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                        {ingresses.length === 0 ? (
                            <div className="empty-state"><ExternalLink size={40} /><span>No ingresses found</span></div>
                        ) : (
                            <div className="resource-grid">
                                {ingresses.map((ing, idx) => (
                                    <motion.div key={ing.name} className="resource-card ingress-card"
                                        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: idx * 0.05 }}>
                                        <div className="resource-card-header">
                                            <ExternalLink size={20} />
                                            <div className="resource-card-title">
                                                <h4>{ing.name}</h4>
                                                {ing.class_name && <span className="resource-type-badge">{ing.class_name}</span>}
                                            </div>
                                            <span className="resource-age">{formatAge(ing.age)}</span>
                                        </div>

                                        {ing.rules.map((rule, rIdx) => (
                                            <div key={rIdx} className="ingress-rule">
                                                <div className="rule-host">
                                                    <Globe size={14} /> {rule.host}
                                                </div>
                                                {rule.paths.map((path, pIdx) => (
                                                    <div key={pIdx} className="rule-path">
                                                        <code>{path.path}</code>
                                                        <ArrowRight size={12} />
                                                        <span className="rule-backend">{path.backend_service}:{path.backend_port}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        ))}

                                        {ing.tls.length > 0 && (
                                            <div className="tls-info">
                                                <Lock size={14} />
                                                <span>TLS enabled ({ing.tls.length} certificate{ing.tls.length > 1 ? 's' : ''})</span>
                                            </div>
                                        )}

                                        {/* API Source */}
                                        <div className="api-source-section">
                                            <button className="api-source-toggle" onClick={() => toggleApiRef(`ing-${ing.name}`)}>
                                                <Code size={12} />
                                                <span>K8s API Source</span>
                                                <ChevronDown size={14} className={expandedApiRef[`ing-${ing.name}`] ? 'chevron-open' : ''} />
                                            </button>
                                            {expandedApiRef[`ing-${ing.name}`] && (
                                                <motion.div className="api-source-content" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} transition={{ duration: 0.2 }}>
                                                    <div className="api-cmd">
                                                        <Terminal size={11} />
                                                        <code>kubectl get ingress {ing.name} -n {selectedNS} -o yaml</code>
                                                    </div>
                                                    <div className="api-path">
                                                        <span className="api-method">GET</span>
                                                        <code>/apis/networking.k8s.io/v1/namespaces/{selectedNS}/ingresses/{ing.name}</code>
                                                    </div>
                                                    <div className="api-field-map">
                                                        <div className="field-row">
                                                            <span className="field-path">.spec.rules[].host</span>
                                                            <span className="field-arrow">→</span>
                                                            <span className="field-val">{ing.rules.map(r => r.host).join(', ')}</span>
                                                        </div>
                                                        <div className="field-row">
                                                            <span className="field-path">.spec.ingressClassName</span>
                                                            <span className="field-arrow">→</span>
                                                            <span className="field-val">{ing.class_name || '(none)'}</span>
                                                        </div>
                                                    </div>
                                                </motion.div>
                                            )}
                                        </div>
                                    </motion.div>
                                ))}
                            </div>
                        )}
                    </motion.div>
                )}

                {activeSection === 'policies' && (
                    <motion.div key="policies" className="networking-content"
                        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                        {netpolicies.length === 0 ? (
                            <div className="empty-state">
                                <Shield size={40} />
                                <span>No network policies found</span>
                                <p className="empty-hint">Network policies restrict pod-to-pod communication. None are currently applied.</p>
                            </div>
                        ) : (
                            <div className="resource-grid">
                                {netpolicies.map((np, idx) => (
                                    <motion.div key={np.name} className="resource-card policy-card"
                                        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: idx * 0.05 }}>
                                        <div className="resource-card-header">
                                            <Shield size={20} />
                                            <div className="resource-card-title">
                                                <h4>{np.name}</h4>
                                            </div>
                                            <span className="resource-age">{formatAge(np.age)}</span>
                                        </div>

                                        <div className="policy-rules">
                                            {np.policy_types.map(t => (
                                                <span key={t} className="policy-type-badge">{t}</span>
                                            ))}
                                        </div>

                                        <div className="resource-details">
                                            <div className="detail-row">
                                                <span className="detail-label">Ingress Rules</span>
                                                <span className="detail-value">{np.ingress_rules_count}</span>
                                            </div>
                                            <div className="detail-row">
                                                <span className="detail-label">Egress Rules</span>
                                                <span className="detail-value">{np.egress_rules_count}</span>
                                            </div>
                                        </div>

                                        {Object.keys(np.pod_selector).length > 0 && (
                                            <div className="selector-labels">
                                                <span className="selector-label-title">Targets:</span>
                                                {Object.entries(np.pod_selector).map(([k, v]) => (
                                                    <span key={k} className="label-chip">{k}={v}</span>
                                                ))}
                                            </div>
                                        )}

                                        {/* API Source */}
                                        <div className="api-source-section">
                                            <button className="api-source-toggle" onClick={() => toggleApiRef(`np-${np.name}`)}>
                                                <Code size={12} />
                                                <span>K8s API Source</span>
                                                <ChevronDown size={14} className={expandedApiRef[`np-${np.name}`] ? 'chevron-open' : ''} />
                                            </button>
                                            {expandedApiRef[`np-${np.name}`] && (
                                                <motion.div className="api-source-content" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} transition={{ duration: 0.2 }}>
                                                    <div className="api-cmd">
                                                        <Terminal size={11} />
                                                        <code>kubectl get networkpolicy {np.name} -n {selectedNS} -o yaml</code>
                                                    </div>
                                                    <div className="api-path">
                                                        <span className="api-method">GET</span>
                                                        <code>/apis/networking.k8s.io/v1/namespaces/{selectedNS}/networkpolicies/{np.name}</code>
                                                    </div>
                                                    <div className="api-field-map">
                                                        <div className="field-row">
                                                            <span className="field-path">.spec.podSelector</span>
                                                            <span className="field-arrow">→</span>
                                                            <span className="field-val">{JSON.stringify(np.pod_selector)}</span>
                                                        </div>
                                                        <div className="field-row">
                                                            <span className="field-path">.spec.policyTypes</span>
                                                            <span className="field-arrow">→</span>
                                                            <span className="field-val">{np.policy_types.join(', ')}</span>
                                                        </div>
                                                    </div>
                                                </motion.div>
                                            )}
                                        </div>
                                    </motion.div>
                                ))}
                            </div>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
