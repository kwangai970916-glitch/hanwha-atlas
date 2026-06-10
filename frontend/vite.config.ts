import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { viteSingleFile } from 'vite-plugin-singlefile'

// mode === 'offline' 일 때만 단일 HTML(viteSingleFile)로 인라인 빌드한다.
export default defineConfig(({ mode }) => ({
  plugins: [react(), ...(mode === 'offline' ? [viteSingleFile()] : [])],
  ...(mode === 'offline' ? { build: { target: 'es2018' } } : {}),
  test: {
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
}))
