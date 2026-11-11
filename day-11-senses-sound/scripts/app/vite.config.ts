import { defineConfig } from 'vite';
// Source lives in day-11-senses-sound/scripts/app; the build lands in the day folder itself.
// Relative base so the page works from the GitHub Pages subfolder; fixed names so rebuilds overwrite.
export default defineConfig({
  base: './',
  server: { port: 5173 },
  build: {
    outDir: '../..',
    emptyOutDir: false,
    assetsDir: 'assets',
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      output: { entryFileNames: 'assets/[name].js', chunkFileNames: 'assets/[name].js', assetFileNames: 'assets/[name][extname]' },
    },
  },
});
