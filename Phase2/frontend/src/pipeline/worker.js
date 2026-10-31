// Runs the whole analysis off the main thread: Pyodide executes the same
// Python as the FastAPI service (see src/browser_entry.py), and transformers.js
// computes the embeddings fastembed would produce on the server.
//
// Both runtimes load from public CDNs at exact versions, which keeps them out
// of the bundle and out of the site's own hosting bandwidth.
const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.29.0/full/pyodide.mjs';
const TRANSFORMERS_URL = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.7.5';
const EMBEDDING_MODEL = 'Xenova/all-MiniLM-L6-v2';
const EMBEDDING_DIMENSION = 384;
const EMBED_BATCH_SIZE = 32;
const MAX_ONNX_THREADS = 4;

const PYODIDE_PACKAGES = ['numpy', 'scipy', 'pydantic', 'micropip', 'regex'];
// Installed without dependency resolution: Pyodide's own networkx package
// pulls in matplotlib, pillow and fonttools, none of which this pipeline uses.
const PYPI_PACKAGES = ['networkx==3.4.2', 'yake==0.7.3', 'segtok', 'tabulate', 'click', 'jellyfish'];

const pythonSources = import.meta.glob('../../../src/*.py', { query: '?raw', import: 'default', eager: true });

let runtimePromise = null;

const onnxThreadCount = () => (
  self.crossOriginIsolated
    ? Math.min(MAX_ONNX_THREADS, Math.max(1, navigator.hardwareConcurrency - 1))
    : 1
);

const loadRuntime = async (report) => {
  report({ status: 'Loading Python runtime…' });
  const { loadPyodide } = await import(/* @vite-ignore */ PYODIDE_URL);
  const pyodide = await loadPyodide();
  await pyodide.loadPackage(PYODIDE_PACKAGES, { messageCallback: () => {} });
  const micropip = pyodide.pyimport('micropip');
  await micropip.install.callKwargs(pyodide.toPy(PYPI_PACKAGES), { deps: false });

  pyodide.FS.mkdirTree('/app/src');
  for (const [path, source] of Object.entries(pythonSources)) {
    pyodide.FS.writeFile(`/app/src/${path.split('/').pop()}`, source);
  }
  pyodide.runPython("import sys; sys.path.insert(0, '/app')");
  const entry = pyodide.pyimport('src.browser_entry');

  report({ status: 'Loading embedding model…' });
  const { pipeline, env } = await import(/* @vite-ignore */ TRANSFORMERS_URL);
  env.backends.onnx.wasm.numThreads = onnxThreadCount();
  const embed = await pipeline('feature-extraction', EMBEDDING_MODEL, {
    dtype: 'q8',
    device: 'wasm',
    // Tracks only the weights: the small config files finish first and would
    // otherwise send the bar to 100% and back.
    progress_callback: ({ status, file, loaded, total }) => {
      if (status === 'progress' && file?.endsWith('.onnx')) {
        report({ model: { fraction: total ? loaded / total : 0, loaded, total } });
      }
    },
  });

  return { pyodide, entry, embed };
};

const getRuntime = (report) => {
  if (!runtimePromise) {
    runtimePromise = loadRuntime(report).catch((err) => {
      runtimePromise = null;
      throw err;
    });
  }
  return runtimePromise;
};

const embedTexts = async (embed, texts, report) => {
  const vectors = new Float32Array(texts.length * EMBEDDING_DIMENSION);
  for (let i = 0; i < texts.length; i += EMBED_BATCH_SIZE) {
    const output = await embed(texts.slice(i, i + EMBED_BATCH_SIZE), { pooling: 'mean', normalize: true });
    vectors.set(output.data, i * EMBEDDING_DIMENSION);
    report({
      status: 'Embedding messages…',
      embedding: { fraction: Math.min(i + EMBED_BATCH_SIZE, texts.length) / texts.length, done: Math.min(i + EMBED_BATCH_SIZE, texts.length), total: texts.length },
    });
  }
  return vectors;
};

const toPythonBytes = (pyodide, vectors) => pyodide.toPy(new Uint8Array(vectors.buffer));

const handlers = {
  async analyse({ file }, report) {
    const { pyodide, entry, embed } = await getRuntime(report);
    // Also covers a second upload and a browser-cached model, neither of
    // which report any download.
    report({ model: { fraction: 1 } });

    report({ status: 'Parsing chat…' });
    const uploadPath = `/tmp/${file.name.replace(/[^\w.-]/g, '_')}`;
    pyodide.FS.writeFile(uploadPath, new Uint8Array(await file.arrayBuffer()));
    let texts;
    try {
      texts = JSON.parse(entry.parse_file(uploadPath));
    } finally {
      entry.remove_upload(uploadPath);
    }
    if (texts.length === 0) {
      throw new Error('No messages found in this file. Check that it is a supported chat export.');
    }

    const vectors = await embedTexts(embed, texts, report);

    report({ status: 'Building graph…' });
    const chatName = file.name.replace(/\.[^.]+$/, '');
    return JSON.parse(await entry.analyse(toPythonBytes(pyodide, vectors), EMBEDDING_DIMENSION, chatName));
  },

  async setTopicCount({ topN }, report) {
    const { entry } = await getRuntime(report);
    return JSON.parse(await entry.set_topic_count(topN));
  },

  async query({ query, topK }, report) {
    const { pyodide, entry, embed } = await getRuntime(report);
    const output = await embed([query], { pooling: 'mean', normalize: true });
    return JSON.parse(entry.query(toPythonBytes(pyodide, output.data), topK));
  },
};

self.onmessage = async ({ data: { id, type, payload } }) => {
  try {
    const result = await handlers[type](payload, (progress) => self.postMessage({ id, progress }));
    self.postMessage({ id, result });
  } catch (err) {
    self.postMessage({ id, error: err.message || String(err) });
  }
};
