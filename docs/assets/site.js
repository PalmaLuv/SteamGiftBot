/* SteamGiftBot — project page behaviour: theme, Ctrl+K menu, the log replay,
   the odds calculator, install tabs, copy buttons, GitHub stars, Konami. */
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const T = JSON.parse($('#i18n').textContent);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const store = { get: k => { try { return localStorage.getItem(k); } catch { return null; } },
                  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} } };

  /* ---------- toast ---------- */
  const toastBox = $('[data-toast]');
  let toastTimer;
  function toast(text) {
    toastBox.textContent = text; toastBox.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { toastBox.hidden = true; }, 3200);
  }

  /* ---------- theme ---------- */
  function setTheme(next) {
    document.documentElement.dataset.theme = next; store.set('sgb-theme', next);
    document.querySelector('meta[name="theme-color"]').content = next === 'light' ? '#F2F3F7' : '#0C0C0E';
  }
  function toggleTheme() {
    const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    setTheme(next); toast(next === 'light' ? T.light : T.dark);
  }
  $('[data-theme-toggle]').addEventListener('click', toggleTheme);
  $$('.langs a').forEach(a => a.addEventListener('click', () => store.set('sgb-lang', a.hreflang)));

  /* ---------- log replay ---------- */
  const term = $('[data-term]');
  const kind = line => line.startsWith('🎉') ? 'win' : /Пропущено|Skipped|Чекає|Ждёт|Waiting|нет|немає|no giveaway/.test(line) ? 'skip' : /Вошёл|Увійшов|Entered/.test(line) ? 'ok' : 'dim';
  let replayRun = 0;
  async function replay() {
    const run = ++replayRun;
    if (reduced) return;
    term.textContent = '';
    for (const line of T.lines) {
      const row = document.createElement('span'); row.className = kind(line); term.appendChild(row);
      for (let i = 0; i <= line.length; i += 2) {
        if (run !== replayRun) return;
        row.textContent = line.slice(0, i);
        await new Promise(r => setTimeout(r, 12));
      }
      term.appendChild(document.createTextNode('\n'));
      await new Promise(r => setTimeout(r, 260));
      if (line.startsWith('🎉') && run === replayRun) confetti(60);
    }
    const cursor = document.createElement('span'); cursor.className = 'cursor'; term.appendChild(cursor);
  }
  $('[data-replay]').addEventListener('click', replay);
  if ('IntersectionObserver' in window) {
    const seen = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) { seen.disconnect(); replay(); } }, {threshold: .4});
    seen.observe(term);
  }

  /* ---------- odds ---------- */
  const entrants = $('#entrants'), price = $('#price');
  const fmt = n => n.toLocaleString(document.documentElement.lang);
  function odds() {
    const e = +entrants.value, p = +price.value, value = 1 / ((e + 1) * Math.max(1, p));
    $('#entrantsOut').textContent = fmt(e); $('#priceOut').textContent = fmt(p);
    $('[data-chance]').textContent = `1 / ${fmt(e + 1)}`;
    $('[data-value]').textContent = value >= .001 ? value.toFixed(4) : value.toExponential(1);
    // 1/41 per iS is a very good giveaway, 1/20000 a hopeless one; a log scale in between.
    const score = Math.max(0, Math.min(1, (Math.log10(value) + 4.3) / 2.7));
    $('[data-meter]').style.width = Math.round(4 + score * 96) + '%';
    $('[data-verdict]').textContent = score > .62 ? T.verdictHigh : score > .3 ? T.verdictMid : T.verdictLow;
  }
  entrants.addEventListener('input', odds); price.addEventListener('input', odds);
  $$('[data-odds]').forEach(b => b.addEventListener('click', () => { const [e, p] = b.dataset.odds.split(','); entrants.value = e; price.value = p; odds(); }));
  odds();
  function roll() {
    const total = +entrants.value + 1, n = 1 + Math.floor(Math.random() * total);
    const out = $('[data-roll-out]');
    if (n === 1) { out.textContent = T.win; confetti(140); }
    else out.textContent = T.lose.replace('{n}', fmt(n)).replace('{total}', fmt(total));
  }
  $('[data-roll]').addEventListener('click', roll);

  /* ---------- install tabs ---------- */
  const tabs = $$('[role=tab]');
  function selectTab(tab) {
    tabs.forEach(t => { const on = t === tab; t.setAttribute('aria-selected', on); t.tabIndex = on ? 0 : -1; $('#' + t.getAttribute('aria-controls')).hidden = !on; });
  }
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => selectTab(t));
    t.addEventListener('keydown', e => {
      const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (step) { const next = tabs[(i + step + tabs.length) % tabs.length]; selectTab(next); next.focus(); }
    });
  });

  /* ---------- copy ---------- */
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast(T.copied); } catch { toast(T.copyFail); }
  }
  $$('.copy').forEach(b => b.addEventListener('click', () => copy($('pre', b.parentElement).textContent)));

  /* ---------- GitHub stars ---------- */
  fetch('https://api.github.com/repos/PalmaLuv/SteamGiftBot').then(r => r.ok ? r.json() : null).then(d => {
    if (!d || typeof d.stargazers_count !== 'number') return;
    const s = $('[data-stars]'); s.textContent = `★ ${fmt(d.stargazers_count)}`; s.title = `${d.stargazers_count} ${T.stars}`; s.hidden = false;
  }).catch(() => {});

  /* ---------- confetti ---------- */
  const canvas = $('[data-confetti]'), ctx = canvas.getContext('2d');
  let bits = [], raf = 0;
  function confetti(count) {
    if (reduced) return;
    canvas.width = innerWidth * devicePixelRatio; canvas.height = innerHeight * devicePixelRatio;
    const colors = ['#FF6B47', '#FF9A6C', '#FFB347', '#18C362', '#3987e5', '#F4F2EE'];
    for (let i = 0; i < count; i++) bits.push({
      x: innerWidth * (.2 + Math.random() * .6), y: innerHeight * .35, vx: (Math.random() - .5) * 9, vy: -4 - Math.random() * 8,
      r: 3 + Math.random() * 4, a: Math.random() * 6, va: (Math.random() - .5) * .3, c: colors[i % colors.length], life: 0,
    });
    if (!raf) raf = requestAnimationFrame(draw);
  }
  function draw() {
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    bits = bits.filter(b => b.life < 180 && b.y < innerHeight + 20);
    for (const b of bits) {
      b.life++; b.vy += .22; b.vx *= .99; b.x += b.vx; b.y += b.vy; b.a += b.va;
      ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.a); ctx.fillStyle = b.c; ctx.globalAlpha = Math.max(0, 1 - b.life / 180);
      ctx.fillRect(-b.r, -b.r / 2, b.r * 2, b.r); ctx.restore();
    }
    raf = bits.length ? requestAnimationFrame(draw) : 0;
    if (!raf) ctx.clearRect(0, 0, innerWidth, innerHeight);
  }

  /* ---------- Ctrl+K command menu ---------- */
  const box = $('[data-palette-box]'), input = $('[data-palette-input]'), list = $('[data-palette-list]');
  const P = T.palette, langs = $$('.langs a');
  const commands = [
    ...['farm', 'sites', 'odds', 'install', 'faq'].map(id => ({label: `${P.go}: ${P[id]}`, hint: '#' + id, run: () => location.hash = id})),
    {label: P.theme, hint: 'T', run: toggleTheme},
    ...langs.filter(a => !a.hasAttribute('aria-current')).map(a => ({label: `${P.lang}: ${a.textContent}`, hint: a.hreflang, run: () => { store.set('sgb-lang', a.hreflang); location.href = a.href; }})),
    {label: P.copyInstall, hint: 'git clone', run: () => copy($('#pane-farm pre').textContent)},
    {label: P.roll, hint: '🎟', run: () => { location.hash = 'odds'; roll(); }},
    {label: P.wiki, hint: '↗', run: () => open('https://github.com/PalmaLuv/SteamGiftBot/wiki', '_blank', 'noopener')},
    {label: P.github, hint: '↗', run: () => open('https://github.com/PalmaLuv/SteamGiftBot', '_blank', 'noopener')},
    {label: P.portfolio, hint: '↗', run: () => open('https://palmaluv.github.io/palma.github.io/', '_blank', 'noopener')},
    {label: P.confetti, hint: '🎉', run: () => confetti(160)},
  ];
  let shown = [], active = 0, lastFocus = null;
  function renderList() {
    const q = input.value.trim().toLowerCase();
    shown = commands.filter(c => !q || c.label.toLowerCase().includes(q) || c.hint.toLowerCase().includes(q));
    active = Math.min(active, Math.max(0, shown.length - 1));
    list.innerHTML = '';
    if (!shown.length) { const li = document.createElement('li'); li.textContent = P.empty; list.appendChild(li); return; }
    shown.forEach((c, i) => {
      const li = document.createElement('li'); li.setAttribute('role', 'option'); li.setAttribute('aria-selected', i === active);
      li.innerHTML = '<span></span><small></small>'; li.firstChild.textContent = c.label; li.lastChild.textContent = c.hint;
      li.addEventListener('click', () => runCommand(i)); li.addEventListener('mousemove', () => { if (active !== i) { active = i; renderList(); } });
      list.appendChild(li);
    });
  }
  function openPalette() { lastFocus = document.activeElement; box.hidden = false; input.value = ''; active = 0; renderList(); input.focus(); }
  function closePalette() { box.hidden = true; lastFocus?.focus?.(); }
  function runCommand(i) { const c = shown[i]; if (!c) return; closePalette(); c.run(); }
  $('[data-palette]').addEventListener('click', openPalette);
  box.addEventListener('click', e => { if (e.target === box) closePalette(); });
  input.addEventListener('input', () => { active = 0; renderList(); });
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); active = (active + 1) % Math.max(1, shown.length); renderList(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = (active - 1 + shown.length) % Math.max(1, shown.length); renderList(); }
    else if (e.key === 'Enter') { e.preventDefault(); runCommand(active); }
  });

  /* ---------- keys: Ctrl+K, Esc, Konami ---------- */
  const konami = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];
  let progress = 0;
  addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); box.hidden ? openPalette() : closePalette(); return; }
    if (e.key === 'Escape' && !box.hidden) { closePalette(); return; }
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    progress = key === konami[progress] ? progress + 1 : key === konami[0] ? 1 : 0;
    if (progress === konami.length) { progress = 0; confetti(220); toast(T.konami); }
  });
})();
