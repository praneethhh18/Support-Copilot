import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = "https://copilot.nexusagent.in";

function NotePanel({ messages, setMessages }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const send = async () => {
    if (!input.trim()) return;
    const newMessages = [...messages, { role: "customer", content: input }];
    setMessages(newMessages);
    setInput("");
    setLoading(true);
    try {
      const res = await axios.post(`${API}/chat`, { messages: newMessages });
      setMessages([...newMessages, { role: "system", content: res.data.nova_response, chunks: res.data.chunks_found }]);
    } catch (e) {
      setMessages([...newMessages, { role: "system", content: "Could not fetch notes.", chunks: 0 }]);
    }
    setLoading(false);
  };

  const clear = () => {
    setMessages([]);
    setInput("");
  };

  return (
    <div style={{ padding: "12px 20px", flex: 1, overflowY: "auto" }}>
      {messages.length === 0 && (
        <p style={{ color: "#bbb", fontSize: "14px", marginTop: "8px" }}>Start typing...</p>
      )}
      {messages.map((msg, i) => (
        <div key={i} style={{ marginBottom: "16px" }}>
          {msg.role === "customer" && (
            <p style={{ fontSize: "14px", color: "#555", fontFamily: "Georgia, serif", lineHeight: "1.8", margin: "0 0 4px 0" }}>
              <span style={{ color: "#999", fontSize: "12px" }}>Note: </span>
              {msg.content}
            </p>
          )}
          {msg.role === "system" && (
            <div style={{ borderLeft: "3px solid #ddd", paddingLeft: "12px", marginLeft: "8px" }}>
              <p style={{ color: "#999", fontSize: "11px", margin: "0 0 4px 0" }}>
                {msg.chunks > 0 ? `${msg.chunks} ref(s)` : "no refs"}
              </p>
              <pre style={{ fontSize: "13px", color: "#333", fontFamily: "Georgia, serif", whiteSpace: "pre-wrap", lineHeight: "1.8", margin: 0 }}>
                {msg.content}
              </pre>
            </div>
          )}
        </div>
      ))}
      {loading && (
        <p style={{ color: "#bbb", fontSize: "13px", fontStyle: "italic" }}>fetching...</p>
      )}
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send();
          }
        }}
        placeholder="Type here..."
        rows={3}
        style={{
          width: "100%",
          border: "none",
          borderTop: "1px solid #eee",
          outline: "none",
          fontSize: "14px",
          fontFamily: "Georgia, serif",
          color: "#333",
          resize: "none",
          padding: "10px 0",
          background: "transparent",
          boxSizing: "border-box",
          marginTop: "12px"
        }}
      />
      <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
        <button onClick={send} disabled={loading} style={{ padding: "4px 12px", background: "none", border: "1px solid #ddd", borderRadius: "4px", fontSize: "12px", color: "#666", cursor: "pointer" }}>
          {loading ? "..." : "Save"}
        </button>
        <button onClick={clear} style={{ padding: "4px 12px", background: "none", border: "1px solid #ddd", borderRadius: "4px", fontSize: "12px", color: "#999", cursor: "pointer" }}>
          Clear
        </button>
      </div>
    </div>
  );
}

function PersonalNotes() {
  const [content, setContent] = useState("");
  const [noteId, setNoteId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);
  const saveTimer = useRef(null);
  const editorRef = useRef(null);

  useEffect(() => {
    axios.get(`${API}/notes`).then(res => {
      setContent(res.data.content || "");
      setNoteId(res.data.id);
      if (editorRef.current) {
        editorRef.current.innerHTML = res.data.content || "";
      }
    }).catch(() => {});
  }, []);

  const handleInput = () => {
    const value = editorRef.current.innerHTML;
    setContent(value);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      autoSave(value);
    }, 1500);
  };

  const autoSave = async (text) => {
    setSaving(true);
    try {
      await axios.post(`${API}/notes`, { content: text, id: noteId });
      setLastSaved(new Date().toLocaleTimeString());
    } catch (e) {}
    setSaving(false);
  };

  const format = (cmd, value = null) => {
    document.execCommand(cmd, false, value);
    editorRef.current.focus();
    handleInput();
  };

  return (
    <div style={{ padding: "0" }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "4px",
        padding: "6px 12px",
        borderBottom: "1px solid #eee",
        background: "#fafafa",
        flexWrap: "wrap"
      }}>
        <select
          onChange={(e) => format("formatBlock", e.target.value)}
          style={{ fontSize: "12px", border: "1px solid #ddd", borderRadius: "3px", padding: "2px 4px", color: "#555", background: "white" }}
        >
          <option value="p">Normal</option>
          <option value="h1">Heading 1</option>
          <option value="h2">Heading 2</option>
          <option value="h3">Heading 3</option>
        </select>
        <button onClick={() => format("bold")} style={{ padding: "2px 8px", border: "1px solid #ddd", borderRadius: "3px", fontSize: "12px", fontWeight: "bold", background: "white", cursor: "pointer", color: "#555" }}>B</button>
        <button onClick={() => format("italic")} style={{ padding: "2px 8px", border: "1px solid #ddd", borderRadius: "3px", fontSize: "12px", fontStyle: "italic", background: "white", cursor: "pointer", color: "#555" }}>I</button>
        <button onClick={() => format("underline")} style={{ padding: "2px 8px", border: "1px solid #ddd", borderRadius: "3px", fontSize: "12px", textDecoration: "underline", background: "white", cursor: "pointer", color: "#555" }}>U</button>
        <button onClick={() => format("insertUnorderedList")} style={{ padding: "2px 8px", border: "1px solid #ddd", borderRadius: "3px", fontSize: "12px", background: "white", cursor: "pointer", color: "#555" }}>• List</button>
        <button onClick={() => format("insertOrderedList")} style={{ padding: "2px 8px", border: "1px solid #ddd", borderRadius: "3px", fontSize: "12px", background: "white", cursor: "pointer", color: "#555" }}>1. List</button>
        <button onClick={() => format("removeFormat")} style={{ padding: "2px 8px", border: "1px solid #ddd", borderRadius: "3px", fontSize: "12px", background: "white", cursor: "pointer", color: "#999" }}>Clear</button>
        <div style={{ flex: 1 }} />
        <p style={{ fontSize: "11px", color: "#bbb", margin: 0 }}>
          {saving ? "saving..." : lastSaved ? `saved ${lastSaved}` : ""}
        </p>
      </div>
      <div
        ref={editorRef}
        contentEditable
        onInput={handleInput}
        data-placeholder="Write your notes here..."
        style={{
          minHeight: "60vh",
          padding: "16px 20px",
          outline: "none",
          fontSize: "14px",
          fontFamily: "Georgia, serif",
          color: "#333",
          lineHeight: "1.8"
        }}
      />
    </div>
  );
}

function UploadPanel() {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const upload = async () => {
    if (!files || files.length === 0) return;
    setLoading(true);
    setResult(null);
    try {
      let totalChunks = 0;
      let results = [];
      for (const f of files) {
        const formData = new FormData();
        formData.append("file", f);
        const res = await axios.post(`${API}/upload-transcript`, formData);
        totalChunks += res.data.chunks_created;
        results.push({ filename: f.name, category: res.data.category, status: res.data.status });
      }
      setResult({ total: files.length, chunks: totalChunks, details: results });
    } catch (e) {
      setResult({ error: "Failed." });
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: "12px 20px" }}>
      <p style={{ color: "#999", fontSize: "13px", marginBottom: "12px", fontFamily: "Georgia, serif" }}>
        Attach files to this document
      </p>
      <input
        type="file"
        accept=".txt"
        multiple
        onChange={(e) => setFiles(Array.from(e.target.files))}
        style={{ fontSize: "13px", color: "#555", marginBottom: "10px", display: "block" }}
      />
      {files.length > 0 && (
        <p style={{ color: "#999", fontSize: "12px", marginBottom: "8px" }}>{files.length} file(s) selected</p>
      )}
      <button
        onClick={upload}
        disabled={loading || files.length === 0}
        style={{ padding: "4px 16px", background: "none", border: "1px solid #ddd", borderRadius: "4px", fontSize: "12px", color: "#666", cursor: "pointer" }}
      >
        {loading ? "Attaching..." : "Attach"}
      </button>
      {result && !result.error && (
        <div style={{ marginTop: "12px" }}>
          {result.details.map((d, i) => (
            <p key={i} style={{ fontSize: "12px", color: "#999", margin: "2px 0", fontFamily: "Georgia, serif" }}>
              ✓ {d.filename} — {d.category} / {d.status}
            </p>
          ))}
        </div>
      )}
      {result && result.error && (
        <p style={{ color: "#f0a0a0", marginTop: "12px", fontSize: "13px" }}>❌ {result.error}</p>
      )}
    </div>
  );
}

function ProductUploadPanel() {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const upload = async () => {
    if (!files || files.length === 0) return;
    setLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      for (const f of files) {
        formData.append("files", f);
      }
      const res = await axios.post(`${API}/upload-products`, formData);
      setResult(res.data);
    } catch (e) {
      setResult({ error: "Failed." });
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: "12px 20px" }}>
      <p style={{ color: "#999", fontSize: "13px", marginBottom: "12px", fontFamily: "Georgia, serif" }}>
        Attach reference sheet — any format, AI will parse it
      </p>
      <input
        type="file"
        accept=".txt"
        multiple
        onChange={(e) => setFiles(Array.from(e.target.files))}
        style={{ fontSize: "13px", color: "#555", marginBottom: "10px", display: "block" }}
      />
      {files.length > 0 && (
        <p style={{ color: "#999", fontSize: "12px", marginBottom: "8px" }}>{files.length} file(s) selected</p>
      )}
      <button
        onClick={upload}
        disabled={loading || files.length === 0}
        style={{ padding: "4px 16px", background: "none", border: "1px solid #ddd", borderRadius: "4px", fontSize: "12px", color: "#666", cursor: "pointer" }}
      >
        {loading ? "Attaching..." : "Attach"}
      </button>
      {result && !result.error && (
        <div style={{ marginTop: "12px" }}>
          <p style={{ fontSize: "12px", color: "#999", fontFamily: "Georgia, serif" }}>✓ {result.message}</p>
          {result.products && result.products.map((p, i) => (
            <p key={i} style={{ fontSize: "12px", color: "#999", margin: "2px 0" }}>📦 {p}</p>
          ))}
        </div>
      )}
      {result && result.error && (
        <p style={{ color: "#f0a0a0", marginTop: "12px", fontSize: "13px" }}>❌ {result.error}</p>
      )}
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState(1);
  const [page, setPage] = useState("notes");
  const [chatMessages, setChatMessages] = useState({ 1: [], 2: [], 3: [] });

  return (
    <div style={{
      minHeight: "100vh",
      background: "#ffffff",
      color: "#333",
      fontFamily: "Georgia, serif",
      maxWidth: "720px",
      margin: "0 auto",
      padding: "0",
      display: "flex",
      flexDirection: "column"
    }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        padding: "6px 16px",
        borderBottom: "1px solid #eee",
        background: "#fafafa",
        gap: "4px"
      }}>
        <button onClick={() => setPage("notes")} style={{ padding: "3px 10px", background: page === "notes" ? "#e8e8e8" : "none", border: "none", borderRadius: "3px", fontSize: "12px", color: "#555", cursor: "pointer" }}>
          Notes
        </button>
        <button onClick={() => setPage("upload")} style={{ padding: "3px 10px", background: page === "upload" ? "#e8e8e8" : "none", border: "none", borderRadius: "3px", fontSize: "12px", color: "#555", cursor: "pointer" }}>
          Files
        </button>
        <button onClick={() => setPage("products")} style={{ padding: "3px 10px", background: page === "products" ? "#e8e8e8" : "none", border: "none", borderRadius: "3px", fontSize: "12px", color: "#555", cursor: "pointer" }}>
          Reference
        </button>

        <div style={{ flex: 1 }} />

        {page === "notes" && (
          <div style={{ display: "flex", gap: "2px" }}>
            {[1, 2, 3, 4].map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: "3px 10px",
                  background: activeTab === tab ? "#e8e8e8" : "none",
                  border: "none",
                  borderRadius: "3px",
                  fontSize: "12px",
                  color: "#555",
                  cursor: "pointer"
                }}
              >
                {tab === 1 ? "Doc 1" : tab === 2 ? "Doc 2" : tab === 3 ? "Doc 3" : "Doc 4"}
              </button>
            ))}
          </div>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "20px 40px" }}>
        {page === "notes" && (
          <>
            {activeTab === 1 && <NotePanel messages={chatMessages[1]} setMessages={(msgs) => setChatMessages(prev => ({...prev, 1: msgs}))} />}
            {activeTab === 2 && <NotePanel messages={chatMessages[2]} setMessages={(msgs) => setChatMessages(prev => ({...prev, 2: msgs}))} />}
            {activeTab === 3 && <NotePanel messages={chatMessages[3]} setMessages={(msgs) => setChatMessages(prev => ({...prev, 3: msgs}))} />}
            {activeTab === 4 && <PersonalNotes />}
          </>
        )}
        {page === "upload" && <UploadPanel />}
        {page === "products" && <ProductUploadPanel />}
      </div>
    </div>
  );
}