import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const crossOriginIsolation = {
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'credentialless'
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Multi-threaded WebAssembly needs a cross-origin isolated page. Keep this
  // in step with vercel.json, which sets the same headers in production.
  server: {
    headers: crossOriginIsolation,
    // The worker imports the Python sources from ../src.
    fs: { allow: ['..'] }
  },
  preview: { headers: crossOriginIsolation },
  worker: { format: 'es' }
})
