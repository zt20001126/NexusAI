import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyRequest, request) => {
            // 保留浏览器访问 Vite 页面时的 Host，供后端校验认证请求 Origin。
            if (request.headers.host) {
              proxyRequest.setHeader('x-forwarded-host', request.headers.host)
            }
          })
        },
      },
    },
  },
})
