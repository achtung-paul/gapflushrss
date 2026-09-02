import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite rejects any request whose Host header isn't localhost/the bind IP
// (server.allowedHosts, a DNS-rebinding protection) -- on a domain-fronted
// host (preprod, behind the Cloudflare Tunnel, see docs/PREPROD_DEPLOY.md)
// nginx forwards the tunnel's real public hostname straight through, so
// every request gets blocked unless that host is explicitly allowed.
// FRONTEND_ORIGIN (docker-compose.yml passes it through to this
// container) is already this host's one source of truth for its public
// domain -- reuse it rather than hardcoding a domain that would only be
// right for one host. Unset falls through to Vite's own default.
const allowedHost = process.env.FRONTEND_ORIGIN
  ? new URL(process.env.FRONTEND_ORIGIN).hostname
  : undefined

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    allowedHosts: allowedHost ? [allowedHost] : undefined,
  },
})
