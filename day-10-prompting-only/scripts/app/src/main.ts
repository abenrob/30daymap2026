// Entry point: mount the terminal and start the game. A fatal error (for example the
// SQL API refusing the token) is shown on the page instead of failing silently.
import '@xterm/xterm/css/xterm.css';
import './style.css';
import { Game } from './game';

const el = document.getElementById('term')!;
new Game(el).run().catch((e) => {
  console.error(e);
  const p = document.createElement('pre');
  p.className = 'fatal';
  p.textContent = `Something went wrong: ${e?.message ?? e}\nReload to try again.`;
  document.body.appendChild(p);
});
