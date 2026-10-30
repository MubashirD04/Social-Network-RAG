// Promise wrapper around worker.js. The worker is created on first use, so
// visitors who only read the landing page download nothing.
let worker = null;
let nextId = 0;
const pending = new Map();

const call = (type, payload = {}, onProgress = null) => {
  if (!worker) {
    worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
    worker.onmessage = ({ data }) => {
      const request = pending.get(data.id);
      if (!request) return;
      if (data.progress !== undefined) {
        request.onProgress?.(data.progress);
      } else {
        pending.delete(data.id);
        if (data.error) request.reject(new Error(data.error));
        else request.resolve(data.result);
      }
    };
  }

  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject, onProgress });
    worker.postMessage({ id, type, payload });
  });
};

export const analyseFile = (file, onProgress) => call('analyse', { file }, onProgress);
export const setTopicCountInWorker = (topN) => call('setTopicCount', { topN });
export const searchMessages = (query, topK) => call('query', { query, topK });
