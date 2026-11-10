import { defineConfig } from 'vite';
// Source lives in day-10-prompting-only/scripts/app; the build lands in the day folder itself.
// Relative base so the page works from the GitHub Pages subfolder. Fixed file names so a
// rebuild overwrites the previous one instead of piling up hashed copies in git.
export default defineConfig({
  base: './',
  server: { port: 5173 },
  build: {
    outDir: '../..',
    emptyOutDir: false,
    assetsDir: 'assets',
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: { entryFileNames: 'assets/[name].js', chunkFileNames: 'assets/[name].js', assetFileNames: 'assets/[name][extname]' },
    },
  },
  worker: { rollupOptions: { output: { entryFileNames: 'assets/[name].js' } } },
});
