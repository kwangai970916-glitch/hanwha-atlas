import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'
import { installOffline } from './offline/offline'

// 제출용 오프라인 빌드: 렌더 전에 fetch/EventSource를 캡처 fixture로 가로채 설치한다.
if (import.meta.env.VITE_OFFLINE === '1') {
  installOffline()
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
