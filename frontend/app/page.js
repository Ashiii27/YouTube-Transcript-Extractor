"use client";

import { useEffect, useMemo, useRef, useState } from "react";

/* -------------------------------------------------------------------------- */
/* Icons (inline SVG — no extra dependencies)                                 */
/* -------------------------------------------------------------------------- */
const Icon = {
  logo: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 5h16M4 12h10M4 19h16" />
    </svg>
  ),
  sparkle: (
    <svg viewBox="0 0 24 24" fill="currentColor" className="sparkle">
      <path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8z" />
    </svg>
  ),
  link: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
    </svg>
  ),
  upload: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <path d="M17 8l-5-5-5 5M12 3v12" />
    </svg>
  ),
  file: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
    </svg>
  ),
  bolt: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />
    </svg>
  ),
  check: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  ),
  alert: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01" />
    </svg>
  ),
  info: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" />
    </svg>
  ),
  copy: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
    </svg>
  ),
  download: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
    </svg>
  ),
  doc: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
    </svg>
  ),
  list: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  ),
  quote: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M7 7h4v4H7c0 2 1 3 3 3v2c-3 0-5-2-5-5V7zm8 0h4v4h-4c0 2 1 3 3 3v2c-3 0-5-2-5-5V7z" />
    </svg>
  ),
  target: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
    </svg>
  ),
  chart: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 20V10M12 20V4M6 20v-6" />
    </svg>
  ),
  globe: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
    </svg>
  ),
  close: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  ),
  play: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M8 5v14l11-7z" />
    </svg>
  ),
};

const LANGUAGES = ["English", "Hindi", "Spanish", "French", "German", "Portuguese", "Japanese", "Arabic"];

const LOADING_MESSAGES = [
  "Fetching captions from the video…",
  "Processing the transcript…",
  "Google Gemini is writing your summary…",
  "Polishing the refined report…",
];

function youtubeId(url) {
  const m = (url || "").match(
    /(?:v=|\/v\/|\/embed\/|\/shorts\/|youtu\.be\/)([A-Za-z0-9_-]{6,50})/
  );
  return m ? m[1] : null;
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [refine, setRefine] = useState(true);
  const [summaryMode, setSummaryMode] = useState("auto");
  const [summaryLanguage, setSummaryLanguage] = useState("English");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [warnings, setWarnings] = useState([]);
  const [result, setResult] = useState(null);
  const [tab, setTab] = useState("summary");
  const [dragOver, setDragOver] = useState(false);
  const [search, setSearch] = useState("");
  const [copied, setCopied] = useState("");
  const [aiStatus, setAiStatus] = useState(null);
  const [step, setStep] = useState(0);
  const resultRef = useRef(null);

  /* Poll backend health to show whether Google Gemini is configured. */
  useEffect(() => {
    let alive = true;
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => alive && setAiStatus(d))
      .catch(() => alive && setAiStatus(null));
    return () => {
      alive = false;
    };
  }, []);

  /* Cycle the loading messages. */
  useEffect(() => {
    if (!loading) return;
    setStep(0);
    const id = setInterval(() => setStep((s) => (s + 1) % LOADING_MESSAGES.length), 2600);
    return () => clearInterval(id);
  }, [loading]);

  /* Scroll results into view when they arrive. */
  useEffect(() => {
    if (result && resultRef.current) {
      resultRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [result]);

  function handleFile(e) {
    setFile(e.target.files?.[0] || null);
  }

  async function runRequest(path, options) {
    setLoading(true);
    setError("");
    setWarnings([]);
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
      setWarnings(data.warnings || []);
      setTab("summary");
    } catch (e) {
      setError(e.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("refine", String(refine));
      fd.append("summary_mode", summaryMode);
      fd.append("summary_language", summaryLanguage);
      runRequest("/api/extract/file", { method: "POST", body: fd });
      return;
    }
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

  function resetAll() {
    setUrl("");
    setFile(null);
    setResult(null);
    setError("");
    setWarnings([]);
    setSearch("");
  }

  const hasSelection = Boolean(url.trim() || file);
  const vid = youtubeId(url);

  async function copyText(text, key) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied(""), 1800);
    } catch (_) {
      /* clipboard unavailable */
    }
  }

  function download(filename, content, type = "text/plain") {
    const blob = new Blob([content], { type });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const summaryMarkdown = useMemo(() => {
    if (!result) return "";
    return buildMarkdown(result);
  }, [result]);

  return (
    <>
      <div className="bg-aurora">
        <div className="blob blob-1" />
        <div className="blob blob-2" />
        <div className="blob blob-3" />
      </div>
      <div className="bg-grid" />

      <main className="app">
        <nav className="nav">
          <div className="brand">
            <span className="brand-mark">{Icon.logo}</span>
            TranscriptIQ
          </div>
          <div className={`ai-pill ${aiStatus?.gemini_available ? "ready" : ""}`}>
            <span className="dot" />
            <span className="pill-label">
              {aiStatus?.gemini_available
                ? "Google Gemini connected"
                : "Local mode (no API key)"}
            </span>
          </div>
        </nav>

        <header className="hero">
          <div className="hero-badge">
            {Icon.sparkle}
            Powered by Google Gemini
          </div>
          <h1>
            Turn any video into a <span className="grad-text">brilliant summary</span> in seconds.
          </h1>
          <p className="subtitle">
            Paste a YouTube or any-platform video link — or drop a file — and get a
            clean transcript plus an AI-crafted report with key points, highlights,
            and action items.
          </p>
          <div className="hero-stats">
            <span className="hero-stat">{Icon.bolt} Instant captions</span>
            <span className="hero-stat">{Icon.globe} YouTube, Vimeo, TED, X &amp; more</span>
            <span className="hero-stat">{Icon.file} Audio / video / subtitle files</span>
          </div>
        </header>

        <section className="card delay-1">
          <h2 className="section-title">{Icon.bolt} Extract &amp; summarize</h2>
          <form onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="url">Video URL or YouTube ID</label>
              <div className="input-wrap">
                <span className="input-icon">{Icon.link}</span>
                <input
                  id="url"
                  type="text"
                  placeholder="https://www.youtube.com/watch?v=… or https://vimeo.com/…"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    if (file) setFile(null);
                  }}
                />
                {url && (
                  <button
                    type="button"
                    className="clear-btn"
                    onClick={() => setUrl("")}
                    aria-label="Clear URL"
                  >
                    {Icon.close}
                  </button>
                )}
              </div>
              {vid && (
                <a
                  className="thumb"
                  href={`https://www.youtube.com/watch?v=${vid}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <img
                    src={`https://i.ytimg.com/vi/${vid}/mqdefault.jpg`}
                    alt="Video thumbnail"
                    onError={(e) => (e.currentTarget.style.display = "none")}
                  />
                  <span className="thumb-play">{Icon.play}</span>
                </a>
              )}
            </div>

            <div
              className={`file-drop ${dragOver ? "drag" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                const f = e.dataTransfer.files?.[0];
                if (f) {
                  setFile(f);
                  setUrl("");
                }
              }}
            >
              <div className="drop-icon">{Icon.upload}</div>
              {file ? (
                <p>
                  <span className="file-name">
                    {Icon.file} {file.name}
                  </span>
                </p>
              ) : (
                <p>
                  Drop an audio / video / subtitle file here, or{" "}
                  <label htmlFor="file-input" className="file-link">
                    browse
                  </label>
                </p>
              )}
              <input
                id="file-input"
                type="file"
                accept=".mp4,.m4a,.mp3,.wav,.vtt,.srt,.txt,.aac,.ogg,.opus,.flac,.webm"
                onChange={handleFile}
              />
            </div>

            <div className="row">
              <div className="field">
                <label htmlFor="mode">Summary mode</label>
                <div className="select-wrap">
                  <select
                    id="mode"
                    value={summaryMode}
                    onChange={(e) => setSummaryMode(e.target.value)}
                  >
                    <option value="auto">Auto — Gemini when available</option>
                    <option value="llm">Google Gemini (AI summary)</option>
                    <option value="extractive">Local extractive (offline)</option>
                  </select>
                </div>
              </div>
              <div className="field">
                <label htmlFor="sum-language">Summary language</label>
                <div className="select-wrap">
                  <select
                    id="sum-language"
                    value={summaryLanguage}
                    onChange={(e) => setSummaryLanguage(e.target.value)}
                  >
                    {LANGUAGES.map((l) => (
                      <option key={l}>{l}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            <div className={`switch-row ${refine ? "on" : ""}`}>
              <div className="switch-label">
                <strong>
                  Refined report <span className="gemini-tag">Gemini</span>
                </strong>
                <span>
                  Structured overview, key points, highlights, action items &amp; stats
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
              <button className="primary" type="submit" disabled={loading || !hasSelection}>
                {loading ? (
                  <>
                    <span className="spinner" />
                    Working…
                  </>
                ) : (
                  <>
                    {Icon.sparkle}
                    {file ? "Extract file" : "Extract & summarize"}
                  </>
                )}
              </button>
              {(result || url || file) && (
                <button type="button" className="ghost" onClick={resetAll} disabled={loading}>
                  {Icon.close} New
                </button>
              )}
            </div>

            {error && (
              <p className="status error">
                {Icon.alert}
                {error}
              </p>
            )}
            {warnings.map((w, i) => (
              <p className="status warn" key={i}>
                {Icon.info}
                {w}
              </p>
            ))}
          </form>

          {loading && (
            <div className="loading-panel">
              {LOADING_MESSAGES.map((msg, i) => (
                <div
                  key={i}
                  className={`loading-step ${
                    i < step ? "done" : i === step ? "active" : ""
                  }`}
                >
                  <span className="step-icon">
                    {i < step ? Icon.check : i === step ? (
                      <span className="mini-spinner" />
                    ) : (
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: "currentColor", opacity: 0.4 }} />
                    )}
                  </span>
                  {msg}
                </div>
              ))}
            </div>
          )}
        </section>

        {result && (
          <section className="card delay-2" ref={resultRef}>
            <div className="result-head">
              <div>
                <h2 className="result-title">{result.meta.title}</h2>
                <div className="meta">
                  <span className="chip">{Icon.globe}{result.meta.source}</span>
                  <span className="chip">{result.meta.language}</span>
                  <span className="chip">{result.meta.word_count.toLocaleString()} words</span>
                  <span className={`chip ${result.summary_method === "llm" ? "llm" : "auto"}`}>
                    {result.summary_method === "llm" ? Icon.sparkle : Icon.bolt}
                    {result.summary_method === "llm" ? "Google Gemini" : "Extractive"}
                  </span>
                  {result.meta.is_auto_caption && <span className="chip auto">auto-captions</span>}
                </div>
              </div>
              <div className="result-actions">
                <button
                  className={`icon-btn ${copied === "copy" ? "copied" : ""}`}
                  title="Copy summary"
                  onClick={() =>
                    copyText(summaryMarkdown, "copy")
                  }
                >
                  {copied === "copy" ? Icon.check : Icon.copy}
                </button>
                <button
                  className="icon-btn"
                  title="Download summary (.md)"
                  onClick={() =>
                    download(
                      `${slug(result.meta.title)}-summary.md`,
                      summaryMarkdown,
                      "text/markdown"
                    )
                  }
                >
                  {Icon.download}
                </button>
                <button
                  className="icon-btn"
                  title="Download transcript (.txt)"
                  onClick={() =>
                    download(
                      `${slug(result.meta.title)}-transcript.txt`,
                      result.segments
                        .map((s) => `[${formatTime(s.start)}] ${s.text}`)
                        .join("\n"),
                      "text/plain"
                    )
                  }
                >
                  {Icon.doc}
                </button>
              </div>
            </div>

            <div className="tabs">
              <button
                className={tab === "summary" ? "tab active" : "tab"}
                onClick={() => setTab("summary")}
              >
                {Icon.sparkle} Summary
              </button>
              <button
                className={tab === "transcript" ? "tab active" : "tab"}
                onClick={() => setTab("transcript")}
              >
                {Icon.list} Transcript
                <span className="chip" style={{ padding: "2px 9px" }}>
                  {result.segments.length}
                </span>
              </button>
            </div>

            {tab === "summary" ? (
              <div className="tab-panel">
                <SummaryView summary={result.summary} refined={result.refined} />
              </div>
            ) : (
              <div className="tab-panel">
                <div className="transcript-toolbar">
                  <div className="input-wrap">
                    <span className="input-icon">{Icon.search}</span>
                    <input
                      type="text"
                      placeholder="Search transcript…"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                </div>
                <TranscriptView segments={result.segments} search={search} />
              </div>
            )}
          </section>
        )}

        {!result && !loading && (
          <div className="features">
            <div className="feature">
              <div className="feature-icon">{Icon.bolt}</div>
              <h3>Instant captions</h3>
              <p>
                YouTube subtitles are fetched in one call — no video download
                required. Other platforms are handled via yt-dlp.
              </p>
            </div>
            <div className="feature">
              <div className="feature-icon">{Icon.sparkle}</div>
              <h3>Gemini-crafted reports</h3>
              <p>
                Google Gemini turns raw transcripts into polished overviews, key
                points, memorable highlights, and action items — in 8 languages.
              </p>
            </div>
            <div className="feature">
              <div className="feature-icon">{Icon.file}</div>
              <h3>Works with your files</h3>
              <p>
                Drop an audio, video, or subtitle file. Local Whisper transcribes
                offline; otherwise Gemini handles the audio in the cloud.
              </p>
            </div>
          </div>
        )}

        <footer>
          <div className="platforms">
            Works with YouTube, Vimeo, TED, Facebook, Twitter/X and many more via yt-dlp.
          </div>
          <div className="google-badge">
            <span className="g-dot" style={{ background: "var(--google-blue)" }} />
            <span className="g-dot" style={{ background: "var(--google-red)" }} />
            <span className="g-dot" style={{ background: "var(--google-yellow)" }} />
            <span className="g-dot" style={{ background: "var(--google-green)" }} />
            AI summaries powered exclusively by Google Gemini
          </div>
        </footer>
      </main>

      <style jsx global>{`
        .thumb {
          display: block;
          position: relative;
          margin-top: 14px;
          width: fit-content;
          border-radius: 12px;
          overflow: hidden;
          border: 1px solid var(--border);
          transition: transform 0.2s var(--ease), box-shadow 0.2s var(--ease);
        }
        .thumb:hover {
          transform: translateY(-2px);
          box-shadow: var(--glow);
        }
        .thumb img {
          display: block;
          width: 220px;
        }
        .thumb-play {
          position: absolute;
          inset: 0;
          display: grid;
          place-items: center;
          background: rgba(4, 8, 18, 0.35);
          color: #fff;
          opacity: 0;
          transition: opacity 0.2s;
        }
        .thumb-play svg {
          width: 38px;
          height: 38px;
          filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.6));
        }
        .thumb:hover .thumb-play {
          opacity: 1;
        }
      `}</style>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Summary rendering                                                          */
/* -------------------------------------------------------------------------- */
function SummaryView({ summary, refined }) {
  if (!summary) return <p className="summary-block">No summary generated.</p>;

  if (!refined) {
    return <p className="summary-block">{summary}</p>;
  }

  const s = summary;
  return (
    <div className="summary-block">
      {s.overview && (
        <Section title="Overview" icon={<span className="h-icon indigo">{Icon.doc}</span>}>
          <p>{s.overview}</p>
        </Section>
      )}
      {s.summary && s.summary !== s.overview && (
        <Section title="Summary" icon={<span className="h-icon blue">{Icon.list}</span>}>
          <p>{s.summary}</p>
        </Section>
      )}
      {s.key_points?.length > 0 && (
        <Section title="Key Points" icon={<span className="h-icon indigo">{Icon.target}</span>}>
          <ul>
            {s.key_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </Section>
      )}
      {s.highlights?.length > 0 && (
        <Section title="Highlights" icon={<span className="h-icon pink">{Icon.quote}</span>} listClass="highlights">
          <ul>
            {s.highlights.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </Section>
      )}
      {s.action_items?.length > 0 && (
        <Section title="Action Items" icon={<span className="h-icon green">{Icon.check}</span>} listClass="actions-list">
          <ul>
            {s.action_items.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </Section>
      )}
      {s.stats && (
        <Section title="Stats" icon={<span className="h-icon amber">{Icon.chart}</span>}>
          <div className="stats">
            {Object.entries(s.stats).map(([k, v]) => (
              <div className="stat" key={k}>
                <strong>{typeof v === "number" ? v.toLocaleString() : String(v)}</strong>
                <span>{humanize(k)}</span>
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function Section({ title, icon, children, listClass = "" }) {
  return (
    <div className={`summary-section ${listClass}`}>
      <h3 className="summary-heading">
        {icon}
        {title}
      </h3>
      {children}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Transcript rendering with search                                           */
/* -------------------------------------------------------------------------- */
function TranscriptView({ segments, search }) {
  const q = search.trim().toLowerCase();
  const filtered = q
    ? segments
        .map((seg, i) => ({ ...seg, i }))
        .filter((seg) => seg.text.toLowerCase().includes(q))
    : segments.map((seg, i) => ({ ...seg, i }));

  if (q && filtered.length === 0) {
    return (
      <div className="transcript">
        <div className="no-match">No lines match “{search}”.</div>
      </div>
    );
  }

  return (
    <div className="transcript">
      {filtered.map((seg) => (
        <div className="line" key={seg.i} style={{ animationDelay: `${Math.min(seg.i * 12, 300)}ms` }}>
          <span className="time">{formatTime(seg.start)}</span>
          <span className="text" dangerouslySetInnerHTML={{ __html: highlight(seg.text, q) }} />
        </div>
      ))}
    </div>
  );
}

function highlight(text, q) {
  if (!q) return escapeHtml(text);
  const safe = escapeHtml(text);
  const safeQ = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return safe.replace(new RegExp(`(${safeQ})`, "gi"), "<mark>$1</mark>");
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */
function formatTime(seconds) {
  if (seconds == null) return "00:00";
  const s = Math.max(0, Math.floor(seconds));
  const min = Math.floor(s / 60) % 60;
  const hour = Math.floor(s / 3600);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return hour > 0 ? `${pad(hour)}:${pad(min)}:${pad(sec)}` : `${pad(min)}:${pad(sec)}`;
}

function humanize(key) {
  return key.replace(/_/g, " ");
}

function slug(name) {
  return (
    String(name || "transcript")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "transcript"
  );
}

function buildMarkdown(result) {
  const m = result.meta;
  const parts = [`# ${m.title}`, ""];
  parts.push(`- **Source:** ${m.source}`);
  parts.push(`- **Language:** ${m.language}`);
  parts.push(`- **Words:** ${m.word_count}`);
  parts.push(`- **Summary engine:** ${result.summary_method === "llm" ? "Google Gemini" : "Extractive"}`);
  parts.push("");
  const s = result.summary;
  if (result.refined && s && typeof s === "object") {
    if (s.overview) parts.push(`## Overview\n\n${s.overview}\n`);
    if (s.summary && s.summary !== s.overview) parts.push(`## Summary\n\n${s.summary}\n`);
    for (const [key, label] of [
      ["key_points", "Key Points"],
      ["highlights", "Highlights"],
      ["action_items", "Action Items"],
    ]) {
      if (s[key]?.length) {
        parts.push(`## ${label}\n`);
        s[key].forEach((v) => parts.push(`- ${v}`));
        parts.push("");
      }
    }
  } else if (s) {
    parts.push(`## Summary\n\n${s}\n`);
  }
  return parts.join("\n");
}
