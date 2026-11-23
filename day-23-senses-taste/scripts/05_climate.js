// Paste into the browser console on https://open-meteo.com, then:  await runPt("Gigondas", 44.167, 5.006, 196)
// Points = area-weighted centroids of the vines (Saint-Joseph split into thirds north to south); elevation = vines' median.
// Temperature: ERA5-Land (models=era5_land). Precipitation: ERA5 (era5_land returns null for precipitation).
// The free API rate-limits 34-year daily requests: wait ~90 s between points.
window.R ??= {};
window.runPt = async (name, lat, lon, elev) => {
  const base = `https://archive-api.open-meteo.com/v1/archive?latitude=${lat}&longitude=${lon}&start_date=1991-01-01&end_date=2024-12-31&timezone=Europe%2FParis&elevation=${elev}`;
  const d = await fetch(base + `&daily=temperature_2m_mean,temperature_2m_max,temperature_2m_min&models=era5_land`).then(r => r.json());
  if (!d.daily) return JSON.stringify(d);
  const p = await fetch(base + `&daily=precipitation_sum&models=era5`).then(r => r.json());
  if (!p.daily) return JSON.stringify(p);
  const t = d.daily.time, tm = d.daily.temperature_2m_mean, tx = d.daily.temperature_2m_max, tn = d.daily.temperature_2m_min, pr = p.daily.precipitation_sum;
  const yr = {};
  t.forEach((s, i) => {
    const y = +s.slice(0, 4), m = +s.slice(5, 7);
    const o = yr[y] ??= { hi: 0, gdd: 0, rain: 0, gsrain: 0, frost: 0, julTx: 0, jn: 0, hot: 0, julTn: 0 };
    o.rain += pr[i] || 0;
    if (m >= 4 && m <= 9) { o.hi += Math.max(0, ((tm[i] - 10) + (tx[i] - 10)) / 2); o.gsrain += pr[i] || 0; }  // Huglin, Apr-Sep
    if (m >= 4 && m <= 10) o.gdd += Math.max(0, tm[i] - 10);                                               // Winkler GDD, Apr-Oct
    if ((m == 4 || m == 5) && tn[i] < 0) o.frost++;
    if (m >= 6 && m <= 8 && tx[i] >= 35) o.hot++;
    if (m == 7) { o.julTx += tx[i]; o.julTn += tn[i]; o.jn++; }
  });
  const agg = (a, b) => {
    const ys = Object.keys(yr).map(Number).filter(y => y >= a && y <= b);
    const f = k => ys.reduce((s, y) => s + (k == 'julTx' ? yr[y].julTx / yr[y].jn : k == 'julTn' ? yr[y].julTn / yr[y].jn : k == 'hi' ? yr[y].hi * 1.04 : yr[y][k]), 0) / ys.length;
    return { huglin: Math.round(f('hi')), gdd10: Math.round(f('gdd')), rain_yr: Math.round(f('rain')), rain_apr_sep: Math.round(f('gsrain')),
             spring_frost_days: +f('frost').toFixed(1), jul_tmax: +f('julTx').toFixed(1), jul_tmin: +f('julTn').toFixed(1), days35_summer: +f('hot').toFixed(1) };
  };
  R[name] = { elev_used: d.elevation, n1991_2020: agg(1991, 2020), r2015_2024: agg(2015, 2024),
              hi_by_year: Object.fromEntries(Object.entries(yr).map(([y, o]) => [y, Math.round(o.hi * 1.04)])),
              rain_by_year: Object.fromEntries(Object.entries(yr).map(([y, o]) => [y, Math.round(o.rain)])) };
  return JSON.stringify(R[name].n1991_2020);
};
// Points used: Gigondas 44.167 5.006 (196 m); SJ north 45.387 4.736, SJ centre 45.235 4.781, SJ south 45.083 4.813 (289 m)
