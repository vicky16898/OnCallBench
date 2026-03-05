import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    MessageSquare,
    Send,
    X,
    Bot,
    User,
    Play,
    CheckCircle2,
    AlertCircle,
    Loader2,
    Sparkles,
    Terminal,
    Copy,
    Check
} from 'lucide-react';

const SUGGESTIONS = [
    "What's the health status of my cluster?",
    "Why is my pod crashlooping?",
    "Show me pods with high restart counts",
    "Are there any warning events?",
    "What network policies are active?",
    "How do I fix an OOMKilled pod?",
];

function ChatPanel({ api, namespace }) {
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [executingCmd, setExecutingCmd] = useState(null);
    const [cmdResults, setCmdResults] = useState({});
    const [copiedIdx, setCopiedIdx] = useState(null);
    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isLoading]);

    useEffect(() => {
        if (isOpen) {
            setTimeout(() => inputRef.current?.focus(), 300);
        }
    }, [isOpen]);

    const sendMessage = async (text) => {
        const userMsg = text || input.trim();
        if (!userMsg || isLoading) return;

        setInput('');
        setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
        setIsLoading(true);

        try {
            const res = await api.post('/chat', {
                message: userMsg,
                namespace: namespace
            });
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: res.data.response,
                commands: res.data.commands || []
            }]);
        } catch (err) {
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: `❌ Error: ${err.response?.data?.detail || err.message}`,
                commands: []
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const executeCommand = async (command, msgIdx, cmdIdx) => {
        const key = `${msgIdx}-${cmdIdx}`;
        setExecutingCmd(key);
        try {
            const res = await api.post('/execute', { command });
            setCmdResults(prev => ({ ...prev, [key]: res.data }));
        } catch (err) {
            setCmdResults(prev => ({
                ...prev,
                [key]: { success: false, stderr: err.response?.data?.detail || err.message }
            }));
        } finally {
            setExecutingCmd(null);
        }
    };

    const copyCommand = (cmd, idx) => {
        navigator.clipboard.writeText(cmd);
        setCopiedIdx(idx);
        setTimeout(() => setCopiedIdx(null), 2000);
    };

    const renderMarkdown = (text) => {
        // Simple markdown rendering — handles bold, code blocks, inline code, headers, lists
        const lines = text.split('\n');
        const elements = [];
        let i = 0;

        while (i < lines.length) {
            const line = lines[i];

            // Code block
            if (line.startsWith('```')) {
                const lang = line.slice(3).trim();
                const codeLines = [];
                i++;
                while (i < lines.length && !lines[i].startsWith('```')) {
                    codeLines.push(lines[i]);
                    i++;
                }
                i++; // skip closing ```
                elements.push(
                    <pre key={i} className="chat-code-block">
                        {lang && <span className="chat-code-lang">{lang}</span>}
                        <code>{codeLines.join('\n')}</code>
                    </pre>
                );
                continue;
            }

            // Headers
            if (line.startsWith('### ')) {
                elements.push(<h4 key={i} className="chat-h4">{line.slice(4)}</h4>);
            } else if (line.startsWith('## ')) {
                elements.push(<h3 key={i} className="chat-h3">{line.slice(3)}</h3>);
            } else if (line.startsWith('# ')) {
                elements.push(<h2 key={i} className="chat-h2">{line.slice(2)}</h2>);
            }
            // Bullet lists
            else if (line.match(/^[\-\*]\s/)) {
                elements.push(
                    <div key={i} className="chat-list-item">
                        <span className="chat-bullet">•</span>
                        <span dangerouslySetInnerHTML={{ __html: formatInline(line.slice(2)) }} />
                    </div>
                );
            }
            // Numbered lists
            else if (line.match(/^\d+\.\s/)) {
                const num = line.match(/^(\d+)\./)[1];
                elements.push(
                    <div key={i} className="chat-list-item">
                        <span className="chat-num">{num}.</span>
                        <span dangerouslySetInnerHTML={{ __html: formatInline(line.replace(/^\d+\.\s/, '')) }} />
                    </div>
                );
            }
            // Empty lines
            else if (line.trim() === '') {
                elements.push(<div key={i} className="chat-spacer" />);
            }
            // Regular paragraph
            else {
                elements.push(
                    <p key={i} className="chat-p" dangerouslySetInnerHTML={{ __html: formatInline(line) }} />
                );
            }
            i++;
        }
        return elements;
    };

    const formatInline = (text) => {
        return text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>');
    };

    return (
        <>
            {/* Floating Chat Button */}
            <AnimatePresence>
                {!isOpen && (
                    <motion.button
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        exit={{ scale: 0, opacity: 0 }}
                        whileHover={{ scale: 1.1 }}
                        whileTap={{ scale: 0.9 }}
                        onClick={() => setIsOpen(true)}
                        className="chat-fab"
                        title="AI Incident Commander"
                    >
                        <Sparkles size={24} />
                    </motion.button>
                )}
            </AnimatePresence>

            {/* Chat Panel Overlay */}
            <AnimatePresence>
                {isOpen && (
                    <>
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="chat-backdrop"
                            onClick={() => setIsOpen(false)}
                        />
                        <motion.div
                            initial={{ x: '100%', opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            exit={{ x: '100%', opacity: 0 }}
                            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
                            className="chat-panel"
                        >
                            {/* Header */}
                            <div className="chat-header">
                                <div className="chat-header-left">
                                    <div className="chat-header-icon">
                                        <Bot size={18} />
                                    </div>
                                    <div>
                                        <h3 className="chat-title">Incident Commander</h3>
                                        <p className="chat-subtitle">
                                            AI-powered · {namespace || 'oncall-bench'}
                                        </p>
                                    </div>
                                </div>
                                <button onClick={() => setIsOpen(false)} className="chat-close-btn">
                                    <X size={18} />
                                </button>
                            </div>

                            {/* Messages */}
                            <div className="chat-messages custom-scrollbar">
                                {messages.length === 0 && !isLoading && (
                                    <div className="chat-welcome">
                                        <div className="chat-welcome-icon">
                                            <Sparkles size={32} />
                                        </div>
                                        <h3>Ask anything about your cluster</h3>
                                        <p>I have live access to your Kubernetes namespace and can help diagnose issues, explain resources, and suggest fixes.</p>
                                        <div className="chat-suggestions">
                                            {SUGGESTIONS.map((s, idx) => (
                                                <button
                                                    key={idx}
                                                    onClick={() => sendMessage(s)}
                                                    className="chat-suggestion-chip"
                                                >
                                                    {s}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {messages.map((msg, msgIdx) => (
                                    <motion.div
                                        key={msgIdx}
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className={`chat-message ${msg.role}`}
                                    >
                                        <div className="chat-message-avatar">
                                            {msg.role === 'user' ? <User size={14} /> : <Bot size={14} />}
                                        </div>
                                        <div className="chat-message-body">
                                            <div className="chat-message-content">
                                                {msg.role === 'user' ? (
                                                    <p>{msg.content}</p>
                                                ) : (
                                                    renderMarkdown(msg.content)
                                                )}
                                            </div>

                                            {/* Executable Commands */}
                                            {msg.commands && msg.commands.length > 0 && (
                                                <div className="chat-commands">
                                                    <div className="chat-commands-label">
                                                        <Terminal size={12} />
                                                        Suggested commands
                                                    </div>
                                                    {msg.commands.map((cmd, cmdIdx) => {
                                                        const key = `${msgIdx}-${cmdIdx}`;
                                                        const result = cmdResults[key];
                                                        return (
                                                            <div key={cmdIdx} className="chat-command-block">
                                                                <div className="chat-command-row">
                                                                    <code className="chat-command-text">{cmd}</code>
                                                                    <div className="chat-command-actions">
                                                                        <button
                                                                            onClick={() => copyCommand(cmd, key)}
                                                                            className="chat-cmd-btn"
                                                                            title="Copy"
                                                                        >
                                                                            {copiedIdx === key ? <Check size={12} /> : <Copy size={12} />}
                                                                        </button>
                                                                        <button
                                                                            onClick={() => executeCommand(cmd, msgIdx, cmdIdx)}
                                                                            disabled={executingCmd === key}
                                                                            className="chat-cmd-run-btn"
                                                                            title="Execute"
                                                                        >
                                                                            {executingCmd === key ? (
                                                                                <Loader2 size={12} className="spin" />
                                                                            ) : (
                                                                                <><Play size={12} /> Run</>
                                                                            )}
                                                                        </button>
                                                                    </div>
                                                                </div>
                                                                {result && (
                                                                    <div className={`chat-cmd-result ${result.success ? 'success' : 'error'}`}>
                                                                        <div className="chat-cmd-result-header">
                                                                            {result.success ? (
                                                                                <><CheckCircle2 size={12} /> Success</>
                                                                            ) : (
                                                                                <><AlertCircle size={12} /> Failed</>
                                                                            )}
                                                                        </div>
                                                                        <pre>{result.stdout || result.stderr || 'Done'}</pre>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            )}
                                        </div>
                                    </motion.div>
                                ))}

                                {/* Loading indicator */}
                                {isLoading && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className="chat-message assistant"
                                    >
                                        <div className="chat-message-avatar">
                                            <Bot size={14} />
                                        </div>
                                        <div className="chat-thinking">
                                            <div className="chat-thinking-dots">
                                                <span /><span /><span />
                                            </div>
                                            Analyzing cluster...
                                        </div>
                                    </motion.div>
                                )}
                                <div ref={messagesEndRef} />
                            </div>

                            {/* Input */}
                            <div className="chat-input-area">
                                <div className="chat-input-wrapper">
                                    <input
                                        ref={inputRef}
                                        type="text"
                                        placeholder="Ask about your cluster..."
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
                                        disabled={isLoading}
                                        className="chat-input"
                                    />
                                    <button
                                        onClick={() => sendMessage()}
                                        disabled={!input.trim() || isLoading}
                                        className="chat-send-btn"
                                    >
                                        <Send size={16} />
                                    </button>
                                </div>
                                <p className="chat-disclaimer">
                                    AI responses may not always be accurate. Verify commands before executing.
                                </p>
                            </div>
                        </motion.div>
                    </>
                )}
            </AnimatePresence>
        </>
    );
}

export default ChatPanel;
