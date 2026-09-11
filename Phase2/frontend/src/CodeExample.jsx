// Static, hand-tokenized snippet — not a real highlighter, just enough
// span/class markup to read like one without pulling in a highlighting lib.
const LINES = [
  [{ t: 'c', v: '// 1. Upload a chat export' }],
  [{ t: 'k', v: 'const' }, { t: 'p', v: ' form = ' }, { t: 'k', v: 'new' }, { t: 'p', v: ' FormData();' }],
  [{ t: 'p', v: 'form.append(' }, { t: 's', v: "'file'" }, { t: 'p', v: ', file); ' }, { t: 'c', v: '// .txt, .json, or .zip' }],
  [{ t: 'p', v: ' ' }],
  [{ t: 'k', v: 'const' }, { t: 'p', v: ' { id } = ' }, { t: 'k', v: 'await' }, { t: 'p', v: ' fetch(' }, { t: 's', v: "'/analyse'" }, { t: 'p', v: ', {' }],
  [{ t: 'p', v: '  method: ' }, { t: 's', v: "'POST'" }, { t: 'p', v: ',' }],
  [{ t: 'p', v: '  body: form,' }],
  [{ t: 'p', v: '}).then(r => r.json());' }],
  [{ t: 'p', v: ' ' }],
  [{ t: 'c', v: '// 2. Ask a natural-language question — RAG over every message' }],
  [{ t: 'k', v: 'const' }, { t: 'p', v: ' { results } = ' }, { t: 'k', v: 'await' }, { t: 'p', v: ' fetch(`/graph/${id}/query`, {' }],
  [{ t: 'p', v: '  method: ' }, { t: 's', v: "'POST'" }, { t: 'p', v: ',' }],
  [{ t: 'p', v: "  headers: { 'Content-Type': " }, { t: 's', v: "'application/json'" }, { t: 'p', v: ' },' }],
  [{ t: 'p', v: '  body: JSON.stringify({' }],
  [{ t: 'p', v: '    query: ' }, { t: 's', v: "'who organized the offsite?'" }, { t: 'p', v: ',' }],
  [{ t: 'p', v: '    top_k: 5' }],
  [{ t: 'p', v: '  }),' }],
  [{ t: 'p', v: '}).then(r => r.json());' }],
];

function CodeExample() {
  return (
    <div className="code-window">
      <div className="code-window-bar">
        <span className="code-dot" style={{ background: '#FF6B6B' }} />
        <span className="code-dot" style={{ background: '#FFD93D' }} />
        <span className="code-dot" style={{ background: '#4ECDC4' }} />
        <span className="code-window-title">example.js</span>
      </div>
      <pre className="code-window-body">
        <code>
          {LINES.map((line, i) => (
            <div className="code-line" key={i}>
              {line.map((tok, j) => (
                <span key={j} className={`tok-${tok.t}`}>{tok.v}</span>
              ))}
            </div>
          ))}
        </code>
      </pre>
    </div>
  );
}

export default CodeExample;
