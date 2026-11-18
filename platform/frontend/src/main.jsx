import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API_URL = import.meta.env.VITE_API_URL || "";

export function App() {
  const [ideas, setIdeas] = useState([]);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadIdeas() {
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/ideas`);
      if (!response.ok) throw new Error("Unable to load ideas.");
      setIdeas(await response.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadIdeas(); }, []);

  async function submit(event) {
    event.preventDefault();
    if (!content.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/ideas`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!response.ok) throw new Error("Unable to submit idea.");
      const idea = await response.json();
      setIdeas((current) => [idea, ...current]);
      setContent("");
      setNotice("Idea submitted successfully.");
      window.setTimeout(() => setNotice(""), 3000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="shell">
      <header>
        <p className="eyebrow">Halcer / AI-first DevOps</p>
        <h1>Turn good ideas into <span>better systems.</span></h1>
        <p className="intro">A shared board for capturing the next improvement, backed by a cloud-agnostic platform.</p>
      </header>
      <section className="composer card">
        <h2>Share an idea</h2>
        <form onSubmit={submit}>
          <label htmlFor="idea">What should we build next?</label>
          <textarea id="idea" value={content} maxLength="2000" onChange={(event) => setContent(event.target.value)} placeholder="Describe an improvement..." />
          <div className="form-row"><small>{content.length}/2000</small><button disabled={submitting || !content.trim()}>{submitting ? "Submitting..." : "Submit idea"}</button></div>
        </form>
      </section>
      {notice && <div className="notice">{notice}</div>}
      {error && <div className="error">{error} <button onClick={loadIdeas}>Retry</button></div>}
      <section className="ideas">
        <div className="section-heading"><h2>Community ideas</h2><span>{ideas.length} shared</span></div>
        {loading ? <div className="card loading">Loading ideas...</div> : ideas.length === 0 ? <div className="card empty">No ideas yet. Be the first to share one.</div> : <div className="grid">{ideas.map((idea) => <article className="card idea" key={idea.id}><p>{idea.content}</p><time>{new Date(idea.created_at).toLocaleString()}</time></article>)}</div>}
      </section>
    </main>
  );
}

const root = document.getElementById("root");
if (root) createRoot(root).render(<App />);
