import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true,
    proxy: { '/api': loadEnv('test', '.', 'UNLOOP_TEST_API_PORT').UNLOOP_TEST_API_PORT === '5002' ? 'http://127.0.0.1:5002' : 'http://127.0.0.1:5001' } },
});
