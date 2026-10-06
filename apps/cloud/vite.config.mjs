import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { drawingAssetsPlugin } from "@text-to-cad/ui/drawing-assets";

// The viewer page of a hosted build: a normal multi-file build, served by the cloud server
// from `dist/` at the root (`/assets/…`, the workers beside them, the drawing editor's fonts
// under `/excalidraw/`) while the page itself answers at `/b/<build>/<path>` (`<base href="/">`
// in index.html keeps every relative URL at the root). Nothing the page loads leaves its origin.
//
// `npm run dev` here serves the page alone; CLOUD_DEV_BACKEND names a running cloud server (or
// the test harness, `test/serveExport.mjs`) to proxy the build's routes to.
const backend = String(process.env.CLOUD_DEV_BACKEND || "").trim().replace(/\/+$/u, "");

// The page's `<base href="/">` must come before anything in `<head>` that names a URL: the
// drawing-assets plugin prepends its bootstrap script there, so the base is moved back to the
// front once every plugin has had its say.
function baseFirst() {
  return {
    name: "cloud-base-first",
    transformIndexHtml: { order: "post", handler(html) {
      const base = /<base\s[^>]*>/i.exec(html);
      if (!base) throw new Error("index.html must carry <base href=\"/\">");
      return html.replace(base[0], "").replace(/<head>/i, `<head>\n    ${base[0]}`);
    } },
  };
}

export default defineConfig({
  plugins: [drawingAssetsPlugin({ exclude: [/\/fonts\/Xiaolai\//] }), react(), baseFirst()],
  resolve: { dedupe: ["react", "react-dom", "three", "lucide-react"] },
  build: {
    chunkSizeWarningLimit: 800,
    rolldownOptions: { output: { codeSplitting: { groups: [
      { name: "vendor-three", test: /[\\/]node_modules[\\/]three[\\/]/ },
      { name: "vendor-react", test: /[\\/]node_modules[\\/]react(?:-dom)?[\\/]/ },
      { name: "vendor-ui", test: /[\\/]node_modules[\\/]@?radix-ui[\\/]/ },
      { name: "vendor-icons", test: /[\\/]node_modules[\\/]lucide-react[\\/]/ },
    ] } } },
  },
  worker: { format: "es" },
  server: {
    host: "127.0.0.1",
    strictPort: true,
    proxy: backend ? {
      // The page itself stays Vite's (with HMR); the build's routes and objects go to the backend.
      "/b": { target: backend, changeOrigin: false, bypass: request => String(request.headers.accept || "").includes("text/html") ? "/index.html" : undefined },
      "/o": { target: backend, changeOrigin: false },
      "/v1": { target: backend, changeOrigin: false },
    } : undefined,
  },
});
