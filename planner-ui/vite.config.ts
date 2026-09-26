import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type ProxyOptions } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // The browser only ever talks to this origin; /api is forwarded to the
  // gateway, which proxies on to C01–C04. The Host header is left as-is so
  // the gateway sees the same origin the browser does.
  const gateway = loadEnv(mode, process.cwd(), '').GATEWAY_URL || 'http://localhost:8080'

  const api: ProxyOptions = {
    target: gateway,
    configure: (proxy) => {
      // Without this, a stopped gateway surfaces as a bare 500 that the UI can
      // only show as "Request failed". Answer in the gateway's own shape instead.
      proxy.on('error', (_err, _req, res) => {
        if (!('writeHead' in res) || res.headersSent) return
        res.writeHead(502, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ detail: `API gateway not reachable at ${gateway}. Is it running?` }))
      })
    },
  }

  return {
    plugins: [react()],
    server: { proxy: { '/api': api } },
    preview: { proxy: { '/api': api } },
  }
})
