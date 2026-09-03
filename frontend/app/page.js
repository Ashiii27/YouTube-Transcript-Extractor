"use client";

import { useState } from "react";

export default function Home() {
  const [url, setUrl] = useState("");
  const [refine, setRefine] = useState(true);
  const [summaryMode, setSummaryMode] = useState("auto");
  const [summaryLanguage, setSummaryLanguage] = useState("English");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [tab, setTab] = useState("summary");
  const [dragOver, setDragOver] = useState(false);

  function handleFile(e) {
    const selected = e.target.files?.[0] || null;
    setFile(selected);
  }

  async function runRequest(path, options) {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch(path, options);
      if (!res.ok) {
        let detail = `Request failed (${res.status})`;
        try {
          const data = await res.json();
          if (data?.detail) detail = String(data.detail);
        } catch (_) {
          /* ignore */
        }
        throw new Error(detail);
      }
      const data = await res.json();
      setResult(data);
      setTab("summary");
    } catch (e) {
      setError(e.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  function extractUrl(e) {
    if (!url.trim()) return;
    const body = {
      url: url.trim(),
      refine,
      summary_mode: summaryMode,
      summary_language: summaryLanguage,
      languages_input: "en,en-US,en-GB,en-orig,eng",
    };
    runRequest("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  function extractFile() {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("refine", String(refine));
    fd.append("summary_mode", summaryMode);
    fd.append("summary_language", summaryLanguage);
    runRequest("/api/extract/file", { method: "POST", body: fd });
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (file) return extractFile();
    extractUrl(e);
  }

  const hasSelection = Boolean(url.trim() || file);

  return (
    <main className="app">
      <header className="hero">
        <div className="brand">
          <span className="brand-dot" />
          Transcript Extractor
        </div>
        <h1>Turn any video into a clean transcript and summary.</h1>
        <p className="subtitle">
          Paste a YouTube or any-platform video URL, or upload an audio / video
          / subtitle file. Get the transcript plus an optional refined report.
        </p>
        <a
          className="download-link"
          href="/downloads/YouTube-Transcript-Extractor-fullstack.zip"
          download
        >
          ⬇ Download project ZIP
        </a>
      </header>

      <section className="card">
        <h2 className="section-title">Extract</h2>
        <form onSubmit={handleSubmit}>
          <label htmlFor="url">Video URL or YouTube ID</label>
          <input
            id="url"
            type="text"
            placeholder="https://www.youtube.com/watch?v=... or https://vimeo.com/..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />

          <div
            className="file-drop"
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              setFile(e.dataTransfer.files?.[0] || null);
            }}
          >
            {file ? (
              <p>
                Selected: <strong>{file.name}</strong>
              </p>
            ) : (
              <p>
                Drop a local file here, or{" "}
                <label
                  htmlFor="file-input"
                  style={{ color: "var(--accent)", cursor: "pointer" }}
                >
                  browse
                </label>
                .
              </p>
            )}
            <input id="file-input" type="file" onChange={handleFile} />
          </div>

          <div className="row">
            <div>
              <label htmlFor="mode">Summary mode</label>
              <select
                id="mode"
                value={summaryMode}
                onChange={(e) => setSummaryMode(e.target.value)}
              >
                <option value="auto">Auto (LLM if key is set)</option>
                <option value="extractive">Local extractive (no keys)</option>
                <option value="llm">LLM (requires API key)</option>
              </select>
            </div>
            <div>
              <label htmlFor="sum-language">Summary language</label>
              <select
                id="sum-language"
                value={summaryLanguage}
                onChange={(e) => setSummaryLanguage(e.target.value)}
              >
                <option>English</option>
                <option>Hindi</option>
                <option>Spanish</option>
                <option>French</option>
                <option>German</option>
              </select>
            </div>
          </div>

          <div className="switch-row">
            <div className="switch-label">
              <strong>Refined summary</strong>
              <span>
                Structured report with key points, highlights, actions &amp;
                stats
              </span>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={refine}
                onChange={(e) => setRefine(e.target.checked)}
              />
              <span className="slider" />
            </label>
          </div>

          <div className="actions">
            <button
              className="primary"
              type="submit"
              disabled={loading || !hasSelection}
            >
              {loading && <span className="spinner" />}
              {file ? "Extract file" : "Extract & summarize"}
            </button>
            {file && (
              <button
                className="secondary"
                type="button"
                onClick={extractFile}
                disabled={loading}
              >
                Extract uploaded file instead
              </button>
            )}
          </div>
          {error && <p className="status error">{error}</p>}
          {loading && !error && (
            <p className="status">Extracting and summarizing…</p>
          )}
        </form>
      </section>

      {result && (
        <section className="card">
          <div className="meta">
            <span className="chip">{result.meta.source}</span>
            <span className="chip">{result.meta.language}</span>
            <span className="chip">{result.meta.word_count} words</span>
            <span className="chip">{result.summary_method}</span>
            {result.refined && <span className="chip">refined</span>}
          </div>
          <h2 className="section-title">{result.meta.title}</h2>

          <div className="tabs">
            <button
              className={tab === "summary" ? "tab active" : "tab"}
              onClick={() => setTab("summary")}
            >
              Summary
            </button>
            <button
              className={tab === "transcript" ? "tab active" : "tab"}
              onClick={() => setTab("transcript")}
            >
              Transcript
            </button>
          </div>

          {tab === "summary" ? (
            <SummaryView summary={result.summary} refined={result.refined} />
          ) : (
            <div className="transcript">
              {result.segments.map((seg, i) => (
                <div className="line" key={i}>
                  <span className="time">{formatTime(seg.start)}</span>
                  <span className="text">{seg.text}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <footer>
        Works with YouTube, Vimeo, TED, Facebook, Twitter/X and more via yt-dlp.
        Local files can be transcribed with Whisper or OpenAI whisper-1.
      </footer>
    </main>
  );
}

function SummaryView({ summary, refined }) {
  if (!summary) return <p className="summary-block">No summary generated.</p>;

  if (!refined) {
    return <p className="summary-block">{summary}</p>;
  }

  const s = summary;
  return (
    <div className="summary-block">
      {s.overview && (
        <div className="summary-section">
          <h3>Overview</h3>
          <p>{s.overview}</p>
        </div>
      )}
      {s.summary && s.summary !== s.overview && (
        <div className="summary-section">
          <h3>Summary</h3>
          <p>{s.summary}</p>
        </div>
      )}
      {s.key_points?.length > 0 && (
        <div className="summary-section">
          <h3>Key Points</h3>
          <ul>
            {s.key_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {s.highlights?.length > 0 && (
        <div className="summary-section">
          <h3>Highlights</h3>
          <ul>
            {s.highlights.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {s.action_items?.length > 0 && (
        <div className="summary-section">
          <h3>Action Items</h3>
          <ul>
            {s.action_items.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {s.stats && (
        <div className="summary-section">
          <h3>Stats</h3>
          <div className="stats">
            {Object.entries(s.stats).map(([k, v]) => (
              <div className="stat" key={k}>
                <strong>{String(v)}</strong>
                {humanize(k)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatTime(seconds) {
  if (seconds == null) return "00:00";
  const s = Math.max(0, Math.floor(seconds));
  const min = Math.floor(s / 60) % 60;
  const hour = Math.floor(s / 3600);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return hour > 0
    ? `${pad(hour)}:${pad(min)}:${pad(sec)}`
    : `${pad(min)}:${pad(sec)}`;
}

function humanize(key) {
  return key.replace(/_/g, " ");
}
