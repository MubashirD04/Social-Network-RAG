import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';
import { motion as Motion, useScroll, useTransform } from 'motion/react';
import { ArrowDown, ArrowRight, Network, ShieldCheck, UploadCloud } from 'lucide-react';
import CodeExample from '../CodeExample';
import { prefersReducedMotion } from '../graph/graphStyle';
import { FLOW_COLORS, FLOW_STOPS } from './flow';
import './Landing.css';

const NodeField = lazy(() => import('./NodeField'));

const STEPS = [
  { title: 'Drop in an export', desc: 'A WhatsApp .txt, a Telegram .json, or a Slack .zip. No account needed.' },
  { title: 'It\'s analyzed on your device', desc: 'Python compiled to WebAssembly builds the graph, and a small model embeds each message, all inside this tab.' },
  { title: 'Explore and ask', desc: 'Follow connections through the graph, or ask a question in plain English and jump to the messages that answer it.' },
];

const QUESTIONS = [
  { q: 'Who holds the room?', a: 'PageRank surfaces the people the conversation turns around.' },
  { q: 'Who connects the groups?', a: 'Betweenness finds the brokers bridging otherwise separate circles.' },
  { q: 'Which sub-groups exist?', a: 'Community detection reveals the clusters hiding inside a big chat.' },
  { q: 'What was it all about?', a: 'Keyword extraction pulls out topics and links them to the messages behind them.' },
  { q: 'Who said that thing?', a: 'Semantic search finds messages by meaning, along with the conversation around them.' },
];

const reveal = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-10% 0px' },
  transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
};

const toMB = (bytes) => (bytes / 1e6).toFixed(0);

const describeModel = (model) => {
  if (!model) return 'Waiting';
  if (model.fraction >= 1) return 'Ready';
  return model.total ? `${toMB(model.loaded)} / ${toMB(model.total)} MB` : `${Math.round(model.fraction * 100)}%`;
};

const describeEmbedding = (embedding) => (
  embedding ? `${embedding.done.toLocaleString()} / ${embedding.total.toLocaleString()}` : 'Waiting'
);

function ProgressBar({ label, detail, fraction }) {
  const percent = Math.round((fraction ?? 0) * 100);
  return (
    <div className="progress-row">
      <div className="progress-labels">
        <span>{label}</span>
        <span className="progress-detail">{detail}</span>
      </div>
      <div
        className={`progress-track ${fraction === undefined ? 'is-waiting' : ''}`}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <Motion.span
          className="progress-fill"
          initial={false}
          animate={{ scaleX: fraction ?? 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}

function Landing({ loading, progress, error, onFile }) {
  const fileInputRef = useRef(null);
  const stepsRef = useRef(null);
  const [dragActive, setDragActive] = useState(false);
  const [showField, setShowField] = useState(false);

  const { scrollYProgress } = useScroll();
  const flow = useTransform(scrollYProgress, FLOW_STOPS, FLOW_COLORS);
  const { scrollYProgress: stepsProgress } = useScroll({ target: stepsRef, offset: ['start 75%', 'end 60%'] });

  useEffect(() => {
    if (prefersReducedMotion()) return undefined;
    const lenis = new Lenis({ autoRaf: true, anchors: true, lerp: 0.1 });
    return () => lenis.destroy();
  }, []);

  // The graph view has no page scroll, so don't hand it a scrolled body.
  useEffect(() => () => window.scrollTo(0, 0), []);

  // three.js only loads once the page itself has painted, and never for
  // someone who has asked their browser to save data.
  useEffect(() => {
    if (navigator.connection?.saveData) return undefined;
    const schedule = window.requestIdleCallback ?? ((callback) => setTimeout(callback, 200));
    const cancel = window.cancelIdleCallback ?? clearTimeout;
    const id = schedule(() => setShowField(true));
    return () => cancel(id);
  }, []);

  const onDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(e.type === 'dragenter' || e.type === 'dragover');
  };

  const onDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    onFile(e.dataTransfer.files?.[0]);
  };

  return (
    <Motion.div className="landing" style={{ '--flow': flow }}>
      <div className="landing-glow" aria-hidden="true" />
      {showField && (
        <Suspense fallback={null}>
          <Motion.div className="node-field-wrap" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.2 }}>
            <NodeField progress={scrollYProgress} />
          </Motion.div>
        </Suspense>
      )}

      <main className="landing-main">
        <section className="hero" id="upload">
          <div className="brand"><Network size={20} aria-hidden="true" /> Social RAG</div>
          <h1>See who really runs your group chat</h1>
          <p className="lede">
            Turn a chat export into a living map of who talks to whom, who holds the
            room, and what it's all about, without your messages ever leaving this browser.
          </p>

          <div
            className={`drop-zone ${dragActive ? 'is-dragging' : ''}`}
            onDragEnter={onDrag}
            onDragLeave={onDrag}
            onDragOver={onDrag}
            onDrop={onDrop}
          >
            {loading ? (
              <div className="drop-target drop-progress">
                <p className="drop-status" role="status">{progress.status}</p>
                <ProgressBar label="Embedding model" detail={describeModel(progress.model)} fraction={progress.model?.fraction} />
                <ProgressBar label="Message embeddings" detail={describeEmbedding(progress.embedding)} fraction={progress.embedding?.fraction} />
              </div>
            ) : (
              <button type="button" className="drop-target" onClick={() => fileInputRef.current.click()}>
                <UploadCloud size={32} aria-hidden="true" />
                <span className="drop-title">Drop a chat export, or click to choose</span>
                <span className="drop-hint">WhatsApp .txt · Telegram .json · Slack .zip</span>
              </button>
            )}
            <input
              type="file"
              ref={fileInputRef}
              className="hidden"
              aria-label="Chat export file"
              onChange={(e) => {
                onFile(e.target.files[0]);
                e.target.value = '';
              }}
              accept=".txt,.json,.zip"
            />
          </div>
          {error && <p className="drop-error" role="alert">{error}</p>}
          <p className="drop-note">The first run downloads the analysis runtime, then your file stays on this device.</p>

          <a className="scroll-cue" href="#how">
            How it works <ArrowDown size={16} aria-hidden="true" />
          </a>
        </section>

        <section className="section" id="how">
          <Motion.h2 {...reveal}>From export to insight in three steps</Motion.h2>
          <ol className="steps" ref={stepsRef}>
            <Motion.span className="steps-progress" style={{ scaleY: stepsProgress }} aria-hidden="true" />
            {STEPS.map((step, i) => (
              <Motion.li className="step" key={step.title} {...reveal}>
                <span className="step-marker" aria-hidden="true">{i + 1}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.desc}</p>
                </div>
              </Motion.li>
            ))}
          </ol>
        </section>

        <section className="section">
          <Motion.h2 {...reveal}>The questions it answers</Motion.h2>
          <dl className="questions">
            {QUESTIONS.map(({ q, a }) => (
              <Motion.div className="question" key={q} {...reveal}>
                <dt>{q}</dt>
                <dd>{a}</dd>
              </Motion.div>
            ))}
          </dl>
        </section>

        <Motion.section className="section privacy" {...reveal}>
          <ShieldCheck size={28} aria-hidden="true" />
          <h2>Private because it can't be otherwise</h2>
          <p>
            Your export is read and analyzed inside this tab. There's no upload step and no
            server to send it to. Only the open-source runtime and embedding model are
            downloaded, from public CDNs.
          </p>
        </Motion.section>

        <section className="section">
          <Motion.div {...reveal}>
            <h2>Building something? There's an API</h2>
            <p className="section-lead">
              Run the FastAPI service locally to get the same analysis over REST, in two calls.
            </p>
          </Motion.div>
          <Motion.div {...reveal}><CodeExample /></Motion.div>
        </section>

        <Motion.section className="section closing" {...reveal}>
          <h2>Ready to see your chat?</h2>
          <a className="cta" href="#upload">Choose an export <ArrowRight size={18} aria-hidden="true" /></a>
        </Motion.section>
      </main>
    </Motion.div>
  );
}

export default Landing;
