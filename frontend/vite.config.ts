import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_DEV_API_TARGET ?? "http://localhost:8000";
  const wsTarget = env.VITE_DEV_WS_TARGET ?? apiTarget.replace(/^http/, "ws");
  return {
    plugins: [react()],
    // The voice worker code-splits; ONNX Runtime and Transformers.js resolve their WebAssembly
    // through import.meta.url, which pre-bundling would break.
    worker: { format: "es" },
    optimizeDeps: { exclude: ["onnxruntime-web", "@huggingface/transformers"] },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
        "/ws": {
          target: wsTarget,
          ws: true,
        },
      },
    },
  };
});
