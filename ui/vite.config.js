import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load environment variables from the current directory
  const env = loadEnv(mode, process.cwd(), '');
  const backendUrl = env.VITE_BACKEND_URL || env.BACKEND_URL || 'http://127.0.0.1:8000';
  const port = Number(env.VITE_PORT || 5173);

  return {
    plugins: [react()],
    build: {
      target: 'esnext',
      minify: false,
    },
    server: {
      port,
      host: '127.0.0.1',
      watch: {
        ignored: ['**/*.zip', '**/*.tar.gz', '**/*.tmp', '**/evidence/**', '**/dist/**'],
      },
      proxy: {
        '/api': {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
  };
});
