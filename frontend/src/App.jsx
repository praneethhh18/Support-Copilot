import { useState } from "react";
import axios from "axios";

const API = "https://copilot.nexusagent.in";

function ChatPanel() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
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
      setMessages([...newMessages, { role: "system", content: "Error connecting to server.", chunks: 0 }]);
    }
    setLoading(false);
  };

  const clear = () => {
    setMessages([]);
    setInput("");
  };

  return (
    <div style={{ padding: "16px" }}>
      {messages.length === 0 && (
        <p style={{ color: "#a0a0b0", fontSize: "13px", textAlign: "center", marginBottom: "12px" }}>
          Paste customer message to start
        </p>
      )}

      <div style={{ marginBottom: "12px", maxHeight: "50vh", overflowY: "auto" }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            marginBottom: "10px",
            padding: "10px 12px",
            borderRadius: "8px",
            background: msg.role === "customer" ? "#1e1e3f" : msg.role === "system" ? "#0f2f1f" : "#1e1e2e",
            border: `1px solid ${msg.role === "customer" ? "#4f46e5" : msg.role === "system" ? "#166534" : "#333"}`
          }}>
            <p style={{
              fontSize: "11px",
              color: msg.role === "customer" ? "#a78bfa" : "#4ade80",
              marginBottom: "6px",
              fontWeight: "bold"
            }}>
              {msg.role === "customer" ? "👤 Customer" : "🤖 Co-Pilot"}
              {msg.chunks !== undefined && (
                <span style={{ color: "#a0a0b0", fontWeight: "normal", marginLeft: "8px" }}>
                  {msg.chunks} case(s) found
                </span>
              )}
            </p>
            <pre style={{
              color: "#e0e0f0",
              fontSize: "13px",
              whiteSpace: "pre-wrap",
              lineHeight: "1.6",
              margin: 0
            }}>
              {msg.content}
            </pre>
          </div>
        ))}
        {loading && (
          <div style={{
            padding: "10px 12px",
            borderRadius: "8px",
            background: "#0f2f1f",
            border: "1px solid #166534",
            color: "#4ade80",
            fontSize: "13px"
          }}>
            🤖 Analysing...
          </div>
        )}
      </div>

      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Paste customer message here..."
        rows={3}
        style={{
          width: "100%",
          padding: "12px",
          borderRadius: "8px",
          border: "1px solid #333",
          background: "#1e1e2e",
          color: "white",
          fontSize: "14px",
          resize: "vertical",
          boxSizing: "border-box"
        }}
      />

      <div style={{ display: "flex", gap: "8px", marginTop: "10px" }}>
        <button
          onClick={send}
          disabled={loading}
          style={{
            flex: 1,
            padding: "12px",
            background: loading ? "#333" : "#4f46e5",
            color: "white",
            border: "none",
            borderRadius: "8px",
            fontSize: "15px",
            cursor: loading ? "not-allowed" : "pointer",
            fontWeight: "bold"
          }}
        >
          {loading ? "Analysing..." : "Analyse"}
        </button>
        <button
          onClick={clear}
          style={{
            padding: "12px 16px",
            background: "#1e1e2e",
            color: "#a0a0b0",
            border: "1px solid #333",
            borderRadius: "8px",
            fontSize: "13px",
            cursor: "pointer"
          }}
        >
          Clear
        </button>
      </div>
    </div>
  );
}

function ChatTab({ tabId, activeTab, setActiveTab }) {
  return (
    <button
      onClick={() => setActiveTab(tabId)}
      style={{
        padding: "8px 20px",
        background: activeTab === tabId ? "#4f46e5" : "#1e1e2e",
        color: "white",
        border: "none",
        borderRadius: "8px 8px 0 0",
        cursor: "pointer",
        fontWeight: activeTab === tabId ? "bold" : "normal"
      }}
    >
      Chat {tabId}
    </button>
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
        results.push({
          filename: f.name,
          category: res.data.category,
          status: res.data.status
        });
      }
      setResult({ total: files.length, chunks: totalChunks, details: results });
    } catch (e) {
      setResult({ error: "Upload failed. Check server." });
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: "16px" }}>
      <p style={{ color: "#a0a0b0", fontSize: "13px", marginBottom: "12px" }}>
        Upload chat transcripts — category and status are auto-detected
      </p>

      <input
        type="file"
        accept=".txt"
        multiple
        onChange={(e) => setFiles(Array.from(e.target.files))}
        style={{
          width: "100%",
          padding: "10px",
          background: "#1e1e2e",
          color: "white",
          border: "1px solid #333",
          borderRadius: "8px",
          marginBottom: "10px",
          boxSizing: "border-box"
        }}
      />

      {files.length > 0 && (
        <p style={{ color: "#a78bfa", fontSize: "13px", marginBottom: "10px" }}>
          {files.length} file(s) selected
        </p>
      )}

      <button
        onClick={upload}
        disabled={loading || files.length === 0}
        style={{
          width: "100%",
          padding: "12px",
          background: loading || files.length === 0 ? "#333" : "#7c3aed",
          color: "white",
          border: "none",
          borderRadius: "8px",
          fontSize: "15px",
          cursor: loading || files.length === 0 ? "not-allowed" : "pointer",
          fontWeight: "bold"
        }}
      >
        {loading ? `Uploading... (${files.length} files)` : "Upload Transcripts"}
      </button>

      {result && !result.error && (
        <div style={{
          marginTop: "16px",
          background: "#1e1e2e",
          borderRadius: "8px",
          padding: "16px",
          border: "1px solid #333"
        }}>
          <p style={{ color: "#a0f0a0", fontSize: "13px", marginBottom: "10px" }}>
            ✅ {result.total} transcript(s) uploaded — {result.chunks} total chunks
          </p>
          {result.details.map((d, i) => (
            <div key={i} style={{
              fontSize: "12px",
              color: "#a0a0b0",
              marginBottom: "4px",
              padding: "6px",
              background: "#13131f",
              borderRadius: "4px"
            }}>
              📄 {d.filename} → <span style={{ color: "#a78bfa" }}>{d.category}</span> / <span style={{ color: d.status === "solved" ? "#a0f0a0" : "#f0a0a0" }}>{d.status}</span>
            </div>
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
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const upload = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await axios.post(`${API}/upload-products`, formData);
      setResult(res.data);
    } catch (e) {
      setResult({ error: "Upload failed. Check server." });
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: "16px" }}>
      <p style={{ color: "#a0a0b0", fontSize: "13px", marginBottom: "12px" }}>
        Upload your product list as a .txt file in this format:
      </p>
      <pre style={{
        background: "#0f0f1a",
        padding: "10px",
        borderRadius: "6px",
        fontSize: "11px",
        color: "#a78bfa",
        marginBottom: "12px",
        whiteSpace: "pre-wrap"
      }}>
{`PRODUCT: Business Email Pro
DESCRIPTION: Managed email hosting
PRICE: ₹499/month
DISCOUNT: 20% off annual plan
BEST FOR: Email downtime issues`}
      </pre>

      <input
        type="file"
        accept=".txt"
        onChange={(e) => setFile(e.target.files[0])}
        style={{
          width: "100%",
          padding: "10px",
          background: "#1e1e2e",
          color: "white",
          border: "1px solid #333",
          borderRadius: "8px",
          marginBottom: "10px",
          boxSizing: "border-box"
        }}
      />

      <button
        onClick={upload}
        disabled={loading || !file}
        style={{
          width: "100%",
          padding: "12px",
          background: loading || !file ? "#333" : "#0ea5e9",
          color: "white",
          border: "none",
          borderRadius: "8px",
          fontSize: "15px",
          cursor: loading || !file ? "not-allowed" : "pointer",
          fontWeight: "bold"
        }}
      >
        {loading ? "Uploading Products..." : "Upload Products"}
      </button>

      {result && !result.error && (
        <div style={{
          marginTop: "16px",
          background: "#1e1e2e",
          borderRadius: "8px",
          padding: "16px",
          border: "1px solid #333"
        }}>
          <p style={{ color: "#a0f0a0", fontSize: "13px", marginBottom: "10px" }}>
            ✅ {result.message}
          </p>
          {result.products && result.products.map((p, i) => (
            <div key={i} style={{
              fontSize: "12px",
              color: "#a0a0b0",
              marginBottom: "4px",
              padding: "6px",
              background: "#13131f",
              borderRadius: "4px"
            }}>
              📦 {p}
            </div>
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
  const [page, setPage] = useState("chat");

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0f0f1a",
      color: "white",
      fontFamily: "sans-serif",
      maxWidth: "480px",
      margin: "0 auto",
      padding: "16px"
    }}>
      <h2 style={{ textAlign: "center", color: "#a78bfa", marginBottom: "12px" }}>
        Support Co-Pilot
      </h2>

      <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
        <button
          onClick={() => setPage("chat")}
          style={{
            flex: 1,
            padding: "8px",
            background: page === "chat" ? "#4f46e5" : "#1e1e2e",
            color: "white",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontWeight: page === "chat" ? "bold" : "normal"
          }}
        >
          Chat
        </button>
        <button
          onClick={() => setPage("upload")}
          style={{
            flex: 1,
            padding: "8px",
            background: page === "upload" ? "#7c3aed" : "#1e1e2e",
            color: "white",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontWeight: page === "upload" ? "bold" : "normal"
          }}
        >
          Transcripts
        </button>
        <button
          onClick={() => setPage("products")}
          style={{
            flex: 1,
            padding: "8px",
            background: page === "products" ? "#0ea5e9" : "#1e1e2e",
            color: "white",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontWeight: page === "products" ? "bold" : "normal"
          }}
        >
          Products
        </button>
      </div>

      {page === "chat" && (
        <>
          <div style={{ display: "flex", gap: "4px", marginBottom: "0" }}>
            <ChatTab tabId={1} activeTab={activeTab} setActiveTab={setActiveTab} />
            <ChatTab tabId={2} activeTab={activeTab} setActiveTab={setActiveTab} />
            <ChatTab tabId={3} activeTab={activeTab} setActiveTab={setActiveTab} />
          </div>
          <div style={{
            background: "#13131f",
            borderRadius: "0 8px 8px 8px",
            border: "1px solid #333"
          }}>
            {activeTab === 1 && <ChatPanel key="chat-1" />}
            {activeTab === 2 && <ChatPanel key="chat-2" />}
            {activeTab === 3 && <ChatPanel key="chat-3" />}
          </div>
        </>
      )}

      {page === "upload" && (
        <div style={{ background: "#13131f", borderRadius: "8px", border: "1px solid #333" }}>
          <UploadPanel />
        </div>
      )}

      {page === "products" && (
        <div style={{ background: "#13131f", borderRadius: "8px", border: "1px solid #333" }}>
          <ProductUploadPanel />
        </div>
      )}
    </div>
  );
}