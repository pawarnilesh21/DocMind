import { useState, useEffect, useRef, useCallback } from 'react';
import { MessageSquare, FileText, Send, UploadCloud, Trash2, Plus, HelpCircle, Layers, BookOpen } from 'lucide-react';
import { authApi, documentApi, chatApi, errorMessage } from './services/api';
import './App.css';

export default function App() {
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState('');
  useEffect(() => {
    let active = true;
    authApi.me().then(value => { if (active) setAccount(value); })
      .catch(error => { if (active && error.response?.status !== 401) setSessionError(errorMessage(error)); })
      .finally(() => { if (active) setLoading(false); });
    const expired = () => { setAccount(null); setSessionError('Your session expired. Please sign in again.'); };
    window.addEventListener('docmind:session-expired', expired);
    return () => { active = false; window.removeEventListener('docmind:session-expired', expired); };
  }, []);
  if (loading) return <main className="login-page"><p role="status">Loading your workspace…</p></main>;
  if (!account) return <Login onLogin={setAccount} initialError={sessionError} />;
  return <Workspace key={account.email} email={account.email} onLogout={() => setAccount(null)} />;
}

function Login({ onLogin, initialError }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setBusy(true); setError('');
    try { onLogin(await authApi.login(email, password)); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <main className="login-page"><form className="login-card" onSubmit={submit}>
    <Layers size={36} /><h1>DocMind</h1><p>Sign in to your private document workspace.</p>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <label>Email<input type="email" autoComplete="username" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} /></label>
    <label>Password<input type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></label>
    <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    <small>Accounts are provisioned by your administrator.</small>
  </form></main>;
}

function Workspace({ email, onLogout }) {
  const [view, setView] = useState('chat');
  const [conversations, setConversations] = useState([]);
  const [moreConversations, setMoreConversations] = useState(false);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [moreMessages, setMoreMessages] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [docPage, setDocPage] = useState(0);
  const [moreDocs, setMoreDocs] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [inputText, setInputText] = useState('');
  const [queryMode, setQueryMode] = useState('qa');
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [activeSource, setActiveSource] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const chatEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const activeIdRef = useRef(null);
  const sourceRequest = useRef(0);
  const pendingSend = useRef(null);

  const fetchConversations = useCallback(async () => {
    const response = await chatApi.listConversations();
    setConversations(response.data);
    setMoreConversations(response.data.length === 50);
    setActiveConvId(current => current ?? response.data[0]?.id ?? null);
  }, []);
  const fetchDocuments = useCallback(async signal => {
    const response = await documentApi.list(docPage * 50, 50, signal);
    setDocuments(response.data.documents);
    setMoreDocs(response.data.has_more);
  }, [docPage]);
  useEffect(() => {
    fetchConversations().catch(err => setError(errorMessage(err)));
  }, [fetchConversations]);
  useEffect(() => {
    const controller = new AbortController();
    fetchDocuments(controller.signal).catch(err => { if (err.code !== 'ERR_CANCELED') setError(errorMessage(err)); });
    const interval = setInterval(() => {
      fetchDocuments(controller.signal).catch(err => { if (err.code !== 'ERR_CANCELED') setError(errorMessage(err)); });
    }, 5000);
    return () => { controller.abort(); clearInterval(interval); };
  }, [fetchDocuments]);
  useEffect(() => {
    activeIdRef.current = activeConvId;
    sourceRequest.current += 1;
    setActiveSource(null); setMessages([]); setMoreMessages(false);
    if (!activeConvId) return;
    const controller = new AbortController();
    setHistoryLoading(true);
    chatApi.getHistory(activeConvId, 0, controller.signal).then(response => {
      setMessages(response.data.messages); setMoreMessages(response.data.has_more);
    }).catch(err => { if (err.code !== 'ERR_CANCELED') setError(errorMessage(err)); })
      .finally(() => { if (!controller.signal.aborted) setHistoryLoading(false); });
    return () => controller.abort();
  }, [activeConvId]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages.length]);

  async function createConversation() {
    try {
      const response = await chatApi.createConversation();
      setConversations(current => [response.data, ...current]);
      setActiveConvId(response.data.id); setView('chat');
    } catch (err) { setError(errorMessage(err)); }
  }
  async function deleteConversation(id, event) {
    event.stopPropagation();
    if (!confirm('Delete this conversation and its history?')) return;
    try {
      await chatApi.deleteConversation(id);
      setConversations(current => current.filter(c => c.id !== id));
      if (activeConvId === id) setActiveConvId(null);
    } catch (err) { setError(errorMessage(err)); }
  }
  async function sendMessage(event) {
    event.preventDefault();
    if (sending || !activeConvId || (queryMode === 'qa' && !inputText.trim())) return;
    if (queryMode === 'summary' && selectedDocIds.length !== 1) {
      setError('Select exactly one ready document for a summary.'); return;
    }
    const conversationId = activeConvId;
    const content = inputText.trim();
    const fingerprint = JSON.stringify([conversationId, content, queryMode, selectedDocIds]);
    if (pendingSend.current?.fingerprint !== fingerprint) {
      pendingSend.current = { fingerprint, id: crypto.randomUUID() };
    }
    setSending(true); setError('');
    try {
      await chatApi.sendMessage(conversationId, content, queryMode, selectedDocIds.length ? selectedDocIds : null, pendingSend.current.id);
      pendingSend.current = null;
      if (activeIdRef.current === conversationId) {
        setInputText('');
        const response = await chatApi.getHistory(conversationId);
        if (activeIdRef.current === conversationId) {
          setMessages(response.data.messages); setMoreMessages(response.data.has_more);
        }
      }
      await fetchConversations();
    } catch (err) { setError(errorMessage(err)); }
    finally { setSending(false); }
  }
  async function upload(event) {
    const file = event.target.files[0];
    if (!file || uploading) return;
    if (file.size > 20 * 1024 * 1024) { setError('The upload limit is 20 MB.'); event.target.value = ''; return; }
    setUploading(true); setError('');
    try {
      await documentApi.upload(file);
      setNotice('Upload saved. Processing will continue in the background.');
      setDocPage(0); await fetchDocuments();
    } catch (err) { setError(errorMessage(err)); }
    finally { setUploading(false); if (fileInputRef.current) fileInputRef.current.value = ''; }
  }
  async function deleteDocument(id) {
    if (!confirm('Delete this document, its source file, and indexed text?')) return;
    try {
      await documentApi.delete(id);
      setSelectedDocIds(current => current.filter(value => value !== id));
      setActiveSource(null); sourceRequest.current += 1;
      await fetchDocuments();
    } catch (err) { setError(errorMessage(err)); }
  }
  async function inspectSource(source) {
    const request = ++sourceRequest.current;
    setActiveSource({ ...source, content: 'Loading source…' });
    try {
      const response = await documentApi.chunk(source.document_id, source.chunk_index);
      if (request === sourceRequest.current) setActiveSource({ ...source, content: response.data[0]?.content || 'This source is no longer available.' });
    } catch (err) {
      if (request === sourceRequest.current) setActiveSource({ ...source, content: errorMessage(err) });
    }
  }
  async function olderMessages() {
    const id = activeConvId;
    try {
      const response = await chatApi.getHistory(id, messages.length);
      if (activeIdRef.current === id) {
        setMessages(current => [...response.data.messages, ...current]); setMoreMessages(response.data.has_more);
      }
    } catch (err) { setError(errorMessage(err)); }
  }
  async function logout() {
    try { await authApi.logout(); onLogout(); } catch (err) { setError(errorMessage(err)); }
  }

  return <div className="app-container">
    <aside className="sidebar">
      <div className="sidebar-brand"><Layers className="brand-icon" /><span>DocMind AI</span></div>
      <button className="new-chat-btn" onClick={createConversation} disabled={sending}><Plus size={16} /> New Chat</button>
      <nav className="nav-menu" aria-label="Workspace">
        <button className={`nav-item ${view === 'chat' ? 'active' : ''}`} onClick={() => setView('chat')}><MessageSquare size={18} /> Chat Workspace</button>
        <button className={`nav-item ${view === 'documents' ? 'active' : ''}`} onClick={() => setView('documents')}><FileText size={18} /> Documents</button>
      </nav>
      <div className="conversations-list-container">
        <div className="section-label">Recent Chats</div>
        <div className="conversations-list">{conversations.map(conv =>
          <div key={conv.id} className={`conversation-item ${activeConvId === conv.id ? 'active' : ''}`}>
            <button className="conversation-select" onClick={() => { setActiveConvId(conv.id); setView('chat'); }} disabled={sending}>{conv.title}</button>
            <button className="delete-conv-btn" aria-label={`Delete ${conv.title}`} disabled={sending} onClick={e => deleteConversation(conv.id, e)}><Trash2 size={14} /></button>
          </div>)}
          {moreConversations && <button onClick={async () => {
            try { const response = await chatApi.listConversations(conversations.length); setConversations(current => [...current, ...response.data]); setMoreConversations(response.data.length === 50); }
            catch (err) { setError(errorMessage(err)); }
          }}>Load more chats</button>}
        </div>
      </div>
      <div className="account-controls"><small>{email}</small><button onClick={logout}>Sign out</button></div>
    </aside>
    <main className="main-workspace">
      {error && <div role="alert" className="error-banner">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
      {notice && <div role="status" className="notice-banner">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss notice">×</button></div>}
      {view === 'chat' ? <div className="chat-view-container">
        <header className="view-header">
          <div className="header-info"><h1>Chat Workspace</h1><p>{conversations.find(c => c.id === activeConvId)?.title || 'Start a chat to ask questions'}</p></div>
          <div className="rag-controls">
            <label className="control-group">Mode:
              <select className="sleek-select" value={queryMode} disabled={sending} onChange={e => setQueryMode(e.target.value)}><option value="qa">Grounded Q&A</option><option value="summary">Document Summary</option></select>
            </label>
            <details className="document-picker"><summary>Target documents ({selectedDocIds.length || 'all ready'})</summary>
              {documents.filter(doc => doc.status === 'ready').map(doc => <label key={doc.id}>
                <input type="checkbox" disabled={sending} checked={selectedDocIds.includes(doc.id)}
                  onChange={() => setSelectedDocIds(current => current.includes(doc.id) ? current.filter(id => id !== doc.id) : [...current, doc.id].slice(0, 20))} />{doc.filename}
              </label>)}
              <small>Use the Documents page to navigate document pages.</small>
            </details>
          </div>
        </header>
        <div className="messages-area" aria-live="polite">
          {historyLoading && <p role="status">Loading conversation…</p>}
          {moreMessages && <button onClick={olderMessages}>Load earlier messages</button>}
          {!historyLoading && messages.length === 0 && <div className="chat-placeholder"><Layers size={48} /><h2>Ask about your documents</h2><p>Upload a document, wait until it is ready, and start a chat. Inspect citations to verify answers.</p><small>AI verification reduces errors but does not guarantee correctness.</small></div>}
          {messages.map(msg => <div key={msg.id} className={`message-bubble ${msg.role}`}>
            <div className="message-avatar">{msg.role === 'user' ? 'U' : 'AI'}</div>
            <div className="message-content-box"><p className="message-text">{msg.content}</p>
              {!!msg.sources?.length && <div className="citations-container">{msg.sources.map((source, index) =>
                <button key={index} className="citation-badge" onClick={() => inspectSource(source)}><BookOpen size={12} /> {source.filename}{source.page_number ? ` (Pg ${source.page_number})` : ` (Chunk ${source.chunk_index + 1})`}</button>)}</div>}
              <span className="message-time">{new Date(msg.created_at.endsWith('Z') ? msg.created_at : msg.created_at + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          </div>)}
          {sending && <p role="status">Retrieving sources and verifying the answer…</p>}
          <div ref={chatEndRef} />
        </div>
        <form className="chat-input-bar" onSubmit={sendMessage}>
          <input aria-label="Question" value={inputText} maxLength={4000} disabled={sending || !activeConvId}
            onChange={e => setInputText(e.target.value)} placeholder={queryMode === 'summary' ? 'Select one document and send to summarize' : 'Ask a question about your documents…'} />
          <button type="submit" className="send-btn" aria-label="Send message" disabled={sending || !activeConvId || (queryMode === 'qa' && !inputText.trim())}><Send size={16} /></button>
        </form>
      </div> : <div className="documents-view-container">
        <header className="view-header"><h1>Documents</h1><p>Private to your account</p></header>
        <div className="documents-content">
          <button className="upload-zone" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
            <UploadCloud size={48} /><h3>{uploading ? 'Saving upload…' : 'Upload a document'}</h3><p>PDF, DOCX, or UTF-8 TXT · up to 20 MB</p>
          </button>
          <input type="file" ref={fileInputRef} onChange={upload} accept=".pdf,.docx,.txt" hidden />
          <div className="doc-list-panel"><h2>Your files</h2>
            {documents.length === 0 && <p>No documents on this page.</p>}
            {documents.map(doc => <div className="doc-card" key={doc.id}>
              <div className="doc-card-info"><FileText /><div className="doc-details"><h3>{doc.filename}</h3><span>{(doc.file_size / 1024).toFixed(1)} KB · {doc.total_chunks} chunks</span>{doc.metadata_?.error && <p role="status">{doc.metadata_.error}</p>}</div></div>
              <div className="doc-card-actions"><span className={`status-badge ${doc.status}`}>{doc.status}</span>
                {doc.status === 'failed' && <button onClick={async () => { try { await documentApi.retry(doc.id); await fetchDocuments(); } catch (err) { setError(errorMessage(err)); } }}>Retry</button>}
                <button className="delete-doc-btn" aria-label={`Delete ${doc.filename}`} onClick={() => deleteDocument(doc.id)}><Trash2 size={16} /></button>
              </div>
            </div>)}
            <div className="pagination"><button disabled={docPage === 0} onClick={() => setDocPage(page => page - 1)}>Previous</button><span>Page {docPage + 1}</span><button disabled={!moreDocs} onClick={() => setDocPage(page => page + 1)}>Next</button></div>
          </div>
        </div>
      </div>}
    </main>
    <aside className={`source-panel ${activeSource ? 'open' : ''}`} aria-label="Source inspector">
      <div className="source-panel-header"><h2>Source Inspector</h2><button aria-label="Close source" onClick={() => { sourceRequest.current += 1; setActiveSource(null); }}>×</button></div>
      {activeSource ? <div className="source-panel-body"><h3>{activeSource.filename}</h3><p>{activeSource.page_number ? `Page ${activeSource.page_number}` : 'Page number unavailable'} · Chunk {activeSource.chunk_index + 1}</p><div className="source-content-text">{activeSource.content}</div></div>
        : <div className="source-panel-empty"><HelpCircle size={32} /><p>Select a citation to inspect its original text.</p></div>}
    </aside>
  </div>;
}
