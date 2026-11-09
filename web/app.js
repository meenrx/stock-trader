"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 2) => n == null || isNaN(n) ? "-" : Number(n).toLocaleString("th-TH", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (n, d = 1) => n == null ? "-" : (n > 0 ? "+" : "") + fmt(n, d) + "%";
const cls = n => n > 0 ? "up" : n < 0 ? "down" : "";
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { } },
};
const BADGE = { "ซื้อ": "b-buy", "รอจังหวะ": "b-watch", "หลีกเลี่ยง": "b-avoid" };

const STATIC = typeof window.staticApi === "function";
if (STATIC) document.documentElement.classList.add("static");
async function api(url, opts) {
  if (STATIC) return window.staticApi(url, opts);
  const r = await fetch(url, opts);
  if (r.status === 401) { location.href = "login"; throw new Error("ต้องใส่ PIN"); }
  const j = await r.json().catch(() => ({ error: "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้" }));
  if (!r.ok) throw new Error(j.error || "ผิดพลาด " + r.status);
  return j;
}
const post = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

/** เรียก API แบบงานเบื้องหลังจนกว่าจะเสร็จ — render จะถูกเรียกทุกครั้งที่ได้ผล */
async function poll(url, render, firstUrl) {
  let j = await api(firstUrl || url);
  for (; ;) {
    render(j);
    if (j.state !== "running") return j;
    await sleep(2500);
    j = await api(url);
  }
}

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 3200);
}
function setStatus(el, j, label) {
  const when = j.result?.time ? new Date(j.result.time).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" }) : "";
  if (j.state === "running") el.innerHTML = `<span class="loader"></span><span>${label}… ${j.result ? "(แสดงผลเดิมระหว่างรอ)" : "ครั้งแรกอาจใช้ 1–2 นาที"}</span>`;
  else if (j.state === "error") el.innerHTML = `<span class="down">ผิดพลาด: ${esc(j.error)}</span>`;
  else el.textContent = when ? `ข้อมูล ณ ${when}${STATIC ? " · อัปเดตอัตโนมัติทุกวันหลังตลาดปิด" : ""}` : "";
}

// ------------------------------------------------------------ กราฟ SVG
function sparkline(vals, w = 84, h = 28) {
  if (!vals || vals.length < 2) return "";
  const lo = Math.min(...vals), hi = Math.max(...vals), r = hi - lo || 1;
  const pts = vals.map((v, i) => `${(i * w / (vals.length - 1)).toFixed(1)},${(h - 2 - (v - lo) / r * (h - 4)).toFixed(1)}`).join(" ");
  const c = vals.at(-1) >= vals[0] ? "var(--up)" : "var(--down)";
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" points="${pts}"/></svg>`;
}

/** series: [{v:[...], color, width, dash}], hlines: [{y, color, label}] */
function lineChart({ dates, series, hlines = [], W = 380, H = 210, money = false }) {
  const pad = { l: 4, r: money ? 62 : 50, t: 8, b: 20 };
  const all = series.flatMap(s => s.v.filter(x => x != null)).concat(hlines.map(h => h.y));
  if (!all.length) return "";
  let lo = Math.min(...all), hi = Math.max(...all); const m = (hi - lo) * .05 || 1; lo -= m; hi += m;
  const n = dates.length, X = i => pad.l + i * (W - pad.l - pad.r) / Math.max(1, n - 1);
  const Y = v => pad.t + (hi - v) / (hi - lo) * (H - pad.t - pad.b);
  let g = "";
  for (let k = 0; k <= 4; k++) {
    const v = lo + (hi - lo) * k / 4, y = Y(v).toFixed(1);
    g += `<line class="grid-l" x1="${pad.l}" x2="${W - pad.r}" y1="${y}" y2="${y}"/><text class="ax" x="${W - pad.r + 6}" y="${+y + 4}">${money ? fmt(v, 0) : fmt(v, v < 10 ? 2 : v < 1000 ? 1 : 0)}</text>`;
  }
  const ticks = [0, Math.floor(n / 2), n - 1];
  ticks.forEach((i, k) => g += `<text class="ax" x="${X(i)}" y="${H - 5}" text-anchor="${["start", "middle", "end"][k]}">${dates[i]?.slice(0, 7) || ""}</text>`);
  hlines.forEach(h => {
    const y = Y(h.y).toFixed(1);
    g += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y}" y2="${y}" stroke="${h.color}" stroke-width="1.3" stroke-dasharray="5 4"/>` +
      `<text x="${W - pad.r - 4}" y="${+y - 4}" text-anchor="end" font-size="10" fill="${h.color}">${h.label}</text>`;
  });
  series.forEach(s => {
    let d = "", pen = false;
    s.v.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; });
    g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 1.5}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""} stroke-linejoin="round"/>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
}

// ------------------------------------------------------------ เส้นทางหน้า
const VIEWS = { home: showHome, scan: showScan, search: showSearch, stock: showStock, news: showNews, paper: showPaper, bt: showBt, set: showSet };
function route() {
  const [name, arg] = (location.hash.slice(1) || "home").split("/");
  const v = VIEWS[name] ? name : "home";
  $$(".view").forEach(s => s.classList.toggle("on", s.id === "v-" + v));
  const tab = v === "stock" || v === "search" ? "scan" : v;
  $$("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.tab === tab));
  window.scrollTo(0, 0);
  VIEWS[v](arg && decodeURIComponent(arg));
}
window.addEventListener("hashchange", route);

// ------------------------------------------------------------ ภาพรวม (แดชบอร์ด)
let homeReq = 0;
const chgCls = v => v > 0.05 ? "p" : v < -0.05 ? "n" : "z";
const chgTxt = (v, d = 2) => v == null ? "-" : (v > 0 ? "+" : "") + fmt(v, d) + "%";
const SECTOR_TH = {
  "Financial Services": "การเงิน", "Industrials": "อุตสาหกรรม", "Real Estate": "อสังหาริมทรัพย์",
  "Consumer Cyclical": "สินค้าฟุ่มเฟือย", "Consumer Defensive": "สินค้าจำเป็น", "Technology": "เทคโนโลยี",
  "Utilities": "สาธารณูปโภค", "Energy": "พลังงาน", "Healthcare": "การแพทย์", "Basic Materials": "วัตถุดิบ",
  "Communication Services": "สื่อสาร",
};
const cardH = (title, href, label) => `<div class="card-h"><h2>${title}</h2>${href ? `<a href="${href}">${label || "ดูทั้งหมด"} →</a>` : ""}</div>`;

/** กราฟเส้นพร้อมเส้นกากบาท + tooltip เมื่อชี้/แตะ */
function hoverChart(el, { dates, series, fmtTip, money = false, H = 230 }) {
  const W = Math.max(300, Math.round(el.clientWidth || 640));      // วาดเท่าความกว้างจริง ตัวอักษรไม่ถูกย่อ/ขยาย
  el.innerHTML = `<div class="chart-wrap chart">${lineChart({ dates, series, W, H, money })}<div class="tip"></div></div>`;
  const svg = el.querySelector("svg"), tip = el.querySelector(".tip"), wrap = el.querySelector(".chart-wrap");
  const pad = { l: 4, r: money ? 62 : 50, t: 8, b: 20 };
  const all = series.flatMap(x => x.v.filter(v => v != null));
  let lo = Math.min(...all), hi = Math.max(...all); const m = (hi - lo) * .05 || 1; lo -= m; hi += m;
  const X = i => pad.l + i * (W - pad.l - pad.r) / Math.max(1, dates.length - 1);
  const Y = v => pad.t + (hi - v) / (hi - lo) * (H - pad.t - pad.b);
  const ns = "http://www.w3.org/2000/svg";
  const vl = document.createElementNS(ns, "line");
  vl.setAttribute("stroke", "var(--faint)"); vl.setAttribute("stroke-width", "1"); vl.setAttribute("y1", pad.t); vl.setAttribute("y2", H - pad.b);
  vl.style.opacity = 0; svg.appendChild(vl);
  const dots = series.map(x => {
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("r", "4"); c.setAttribute("fill", x.color); c.setAttribute("stroke", "var(--surface)"); c.setAttribute("stroke-width", "2");
    c.style.opacity = 0; svg.appendChild(c); return c;
  });
  const move = e => {
    const r = svg.getBoundingClientRect(), sx = (e.clientX - r.left) / r.width * W;
    const i = Math.max(0, Math.min(dates.length - 1, Math.round((sx - pad.l) / (W - pad.l - pad.r) * (dates.length - 1))));
    vl.setAttribute("x1", X(i)); vl.setAttribute("x2", X(i)); vl.style.opacity = 1;
    series.forEach((x, k) => { const v = x.v[i]; dots[k].style.opacity = v == null ? 0 : 1; if (v != null) { dots[k].setAttribute("cx", X(i)); dots[k].setAttribute("cy", Y(v)); } });
    tip.innerHTML = fmtTip(i); tip.classList.add("on");
    const px = X(i) / W * r.width;
    tip.style.left = Math.max(70, Math.min(r.width - 70, px)) + "px";
    tip.style.top = (Math.min(...series.map(x => x.v[i]).filter(v => v != null).map(Y)) / H * r.height) + "px";
  };
  const out = () => { vl.style.opacity = 0; dots.forEach(d => d.style.opacity = 0); tip.classList.remove("on"); };
  svg.addEventListener("pointermove", move); svg.addEventListener("pointerdown", move);
  svg.addEventListener("pointerleave", out);
  wrap.style.touchAction = "pan-y";
}

function heatColor(v) {
  const p = Math.min(100, Math.abs(v) / 4 * 100);
  const base = v >= 0 ? "var(--upfill)" : "var(--downfill)";
  return { bg: `color-mix(in srgb, ${base} ${Math.round(p * .85)}%, var(--mid))`, light: p > 60 };
}

function renderHome(scan, news, paper, bt) {
  const rows = scan.rows || [], liq = rows.filter(r => r.liquid);
  const reg = Object.values(scan.regimes || {})[0] || {};
  const cnt = { "ซื้อ": 0, "รอจังหวะ": 0, "หลีกเลี่ยง": 0 };
  liq.forEach(r => cnt[r.status]++);
  const above = liq.filter(r => r.a200).length, breadth = liq.length ? above / liq.length * 100 : 0;
  const since = Date.now() - 24 * 3600e3;
  const n24 = (news?.items || []).filter(n => new Date(n.d) >= since);
  const pos = n24.filter(n => n.sen > 0).length, neg = n24.filter(n => n.sen < 0).length;
  const regCls = reg.strong ? "good" : reg.ok ? "warn" : "bad";
  const regWord = reg.strong ? "▲ ขาขึ้น" : reg.ok ? "■ ฟื้นตัว" : "▼ ขาลง";
  const dist = reg.close && reg.sma200 ? (reg.close / reg.sma200 - 1) * 100 : null;
  const out = [];

  // ---- KPI
  out.push(`<a class="card kpi" href="#scan"><div class="k">สภาพตลาด <span class="pill ${regCls}">${regWord}</span></div>
    <div class="v">${dist == null ? "-" : chgTxt(dist, 1)}</div><div class="s">SET50 เทียบเส้น 200 วัน</div></a>`);
  out.push(`<a class="card kpi" href="#scan"><div class="k">สัญญาณซื้อวันนี้</div>
    <div class="v">${cnt["ซื้อ"]} <span class="small mut" style="font-weight:500">ตัว</span></div><div class="s">รอจังหวะอีก ${cnt["รอจังหวะ"]} ตัว</div></a>`);
  out.push(`<div class="card kpi"><div class="k">หุ้นอยู่ในขาขึ้น</div>
    <div class="v">${fmt(breadth, 0)}%</div><div class="meter"><i style="width:${breadth}%"></i></div>
    <div class="s">${above} จาก ${liq.length} ตัวที่ซื้อขายคล่อง อยู่เหนือเส้น 200 วัน</div></div>`);
  out.push(`<a class="card kpi" href="#news"><div class="k">ข่าวหุ้น 24 ชม.</div>
    <div class="v">${fmt(n24.length, 0)} <span class="small mut" style="font-weight:500">ข่าว</span></div>
    <div class="s"><span class="up">● บวก ${pos}</span> · <span class="down">● ลบ ${neg}</span></div></a>`);

  // ---- กราฟตลาด + สถานะหุ้น
  out.push(`<section class="card w8">${cardH(`${esc(scan.bench?.name || "SET50")} ย้อนหลัง 1 ปี`)}
    <div id="mkt-chart"></div>
    <div class="legend"><span><i style="background:var(--accent)"></i>ราคา</span><span><i style="background:var(--c4)"></i>เส้นค่าเฉลี่ย 200 วัน</span>
    <span>${esc(reg.text || "")}</span></div></section>`);
  const tot = liq.length || 1, seg = [["ซื้อ", "var(--upfill)"], ["รอจังหวะ", "#fab219"], ["หลีกเลี่ยง", "var(--avoid)"]];
  out.push(`<section class="card w4">${cardH("สถานะหุ้นที่ซื้อขายคล่อง", "#scan")}
    <div class="big-num num">${fmt(liq.length, 0)} <span class="small mut" style="font-weight:500">ตัว (≥ 5 ล้านบาท/วัน)</span></div>
    <div class="stack">${seg.map(([k, c]) => cnt[k] ? `<i style="width:${cnt[k] / tot * 100}%;background:${c}" title="${k} ${cnt[k]} ตัว"></i>` : "").join("")}</div>
    <div class="legend-row">${seg.map(([k, c]) => `<span><i style="background:${c}"></i>${k} <b class="num">${cnt[k]}</b> <span class="mut">(${fmt(cnt[k] / tot * 100, 0)}%)</span></span>`).join("")}</div>
    <p class="small mut" style="margin:12px 0 0">สแกนทั้งตลาด ${fmt(rows.length, 0)} ตัว · ที่เหลือซื้อขายน้อยเกินไป ระบบจึงไม่แนะนำ</p></section>`);

  // ---- สัญญาณซื้อ + พอร์ต
  const buys = rows.filter(r => r.status === "ซื้อ").slice(0, 8);
  out.push(`<section class="card w7">${cardH("สัญญาณซื้อล่าสุด", "#scan")}
    ${buys.length ? `<div style="overflow-x:auto"><table class="dt"><thead><tr><th>หุ้น</th><th class="r">ราคา</th><th class="r hide-sm">วันนี้</th><th class="r">Stop</th><th class="r">เป้า</th><th class="r">คะแนน</th></tr></thead><tbody>
    ${buys.map(r => `<tr data-go="#stock/${encodeURIComponent(r.symbol)}"><td><div class="tk">${esc(r.ticker)}</div><div class="sub">${esc(r.signals[0] || r.name)}</div></td>
      <td class="r">${fmt(r.close)}</td><td class="r hide-sm"><span class="chg ${chgCls(r.chg1)}">${chgTxt(r.chg1)}</span></td>
      <td class="r down">${fmt(r.plan.stop)}</td><td class="r up">${fmt(r.plan.target)}</td><td class="r"><b>${fmt(r.score, 0)}</b></td></tr>`).join("")}
    </tbody></table></div>` : `<div class="empty">วันนี้ไม่มีหุ้นผ่านทุกเงื่อนไข — ไม่ซื้อก็ไม่เป็นไร</div>`}</section>`);
  const pp = paper || { positions: [], total: 0, gain_pct: 0, cash: 0, alerts: [] };
  out.push(`<section class="card w5">${cardH("พอร์ตจำลอง", "#paper", "จัดการ")}
    <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap"><div class="big-num num">${fmt(pp.total, 0)}</div>
    <span class="chg ${chgCls(pp.gain_pct)}">${chgTxt(pp.gain_pct)}</span></div>
    <div class="small mut">เงินสด ${fmt(pp.cash, 0)} · ถือ ${pp.positions.length} ตัว</div>
    <div style="margin-top:8px">${pp.positions.slice(0, 4).map(x => `<a class="mv" href="#stock/${encodeURIComponent(x.ticker)}"><b>${esc(x.ticker.replace(".BK", ""))}</b>
      <span class="small mut num">Stop ${fmt(x.stop)}</span><span class="chg ${chgCls(x.chg_pct)}">${chgTxt(x.chg_pct)}</span></a>`).join("")
      || `<p class="small mut">ยังไม่มีหุ้นในพอร์ตจำลอง — เปิดหน้าหุ้นแล้วกด "ซื้อในพอร์ตจำลอง" เพื่อฝึกเทรด</p>`}</div>
    ${pp.alerts.map(a => `<div class="alert sell">⚠ ${esc(a)}</div>`).join("")}</section>`);

  // ---- แผนที่ตลาด + หุ้นขึ้น/ลงแรง
  const heat = [...liq].sort((a, b) => b.value20_m - a.value20_m).slice(0, 40);
  out.push(`<section class="card w8">${cardH("แผนที่ตลาดวันนี้ <span class='small mut' style='font-weight:500'>(40 ตัวที่ซื้อขายมากสุด)</span>")}
    <div class="heat">${heat.map(r => { const h = heatColor(r.chg1); return `<a href="#stock/${encodeURIComponent(r.symbol)}" class="${h.light ? "light" : ""}" style="background:${h.bg}"
      title="${esc(r.ticker)} · ${fmt(r.close)} · ${chgTxt(r.chg1)} · ซื้อขาย ${fmt(r.value20_m, 0)} ล้าน/วัน"><b>${esc(r.ticker)}</b><span>${chgTxt(r.chg1)}</span></a>`; }).join("")}</div>
    <div class="heat-scale"><span>−4%</span><div class="bar"></div><span>+4%</span><span style="margin-left:auto">แตะเพื่อดูรายละเอียด</span></div></section>`);
  const g = [...liq].sort((a, b) => b.chg1 - a.chg1);
  const mvRow = r => `<a class="mv" href="#stock/${encodeURIComponent(r.symbol)}"><b>${esc(r.ticker)}</b><span class="small mut num">${fmt(r.close)}</span><span class="chg ${chgCls(r.chg1)}">${chgTxt(r.chg1)}</span></a>`;
  out.push(`<section class="card w4">${cardH("ขึ้น/ลงแรงวันนี้")}
    <div class="movers"><div><div class="eyebrow up" style="margin-bottom:2px">▲ ขึ้นมากสุด</div>${g.slice(0, 6).map(mvRow).join("")}</div>
    <div><div class="eyebrow down" style="margin-bottom:2px">▼ ลงมากสุด</div>${g.slice(-6).reverse().map(mvRow).join("")}</div></div>
    <p class="small mut" style="margin:8px 0 0">เฉพาะหุ้นที่ซื้อขาย ≥ 5 ล้านบาท/วัน</p></section>`);

  // ---- ใกล้จุดซื้อ + ข่าว
  const near = rows.filter(r => r.status === "รอจังหวะ" && r.plan.breakout_level)
    .map(r => ({ r, gap: (r.plan.breakout_level / r.close - 1) * 100 })).filter(x => x.gap >= 0 && x.gap <= 4)
    .sort((a, b) => a.gap - b.gap).slice(0, 8);
  out.push(`<section class="card w5">${cardH("ใกล้ทะลุจุดซื้อ", "#scan")}
    ${near.length ? near.map(({ r, gap }) => `<a class="near" href="#stock/${encodeURIComponent(r.symbol)}"><span class="tk">${esc(r.ticker)}</span>
      <span class="gauge" title="ห่างจุดเบรก ${fmt(gap, 1)}%"><i style="width:${Math.max(4, 100 - gap / 4 * 100)}%"></i></span>
      <span class="small num" style="width:118px;text-align:right">${fmt(r.close)} → <b>${fmt(r.plan.breakout_level)}</b></span>
      <span class="small mut num" style="width:44px;text-align:right">${fmt(gap, 1)}%</span></a>`).join("")
      : `<p class="small mut">ยังไม่มีหุ้นที่ห่างจุดเบรกไม่เกิน 4%</p>`}
    <p class="small mut" style="margin:8px 0 0">หุ้นแนวโน้มดีที่ราคาใกล้ไฮ 55 วัน — ถ้าทะลุพร้อมวอลุ่มคือจุดซื้อ (บอท Telegram จะเตือน)</p></section>`);
  const tn = (news?.items || []).filter(n => n.sym.length).slice(0, 7);
  out.push(`<section class="card w7">${cardH("ข่าวหุ้นล่าสุด", "#news")}
    ${tn.map(n => `<a class="mini-news" href="${esc(n.l)}" target="_blank" rel="noopener">${esc(n.t)}
      <div class="meta"><span class="sen ${n.sen > 0 ? "p" : n.sen < 0 ? "n" : "z"}"></span>${esc(n.s)} · ${ago(n.d)}
      ${n.sym.slice(0, 4).map(s => `<span class="tag">${esc(s)}</span>`).join("")}</div></a>`).join("") || `<p class="small mut">ยังไม่มีข่าว</p>`}</section>`);

  // ---- กลุ่มอุตสาหกรรม + ผลย้อนหลัง
  const sec = {};
  liq.forEach(r => { const k = SECTOR_TH[r.sector]; if (!k) return; (sec[k] ||= []).push(r.roc21); });
  const secRows = Object.entries(sec).filter(([, v]) => v.length >= 3)
    .map(([k, v]) => [k, v.reduce((a, b) => a + b, 0) / v.length, v.length]).sort((a, b) => b[1] - a[1]);
  const smax = Math.max(3, ...secRows.map(x => Math.abs(x[1])));
  out.push(`<section class="card w6">${cardH("กลุ่มอุตสาหกรรม <span class='small mut' style='font-weight:500'>(ผลตอบแทนเฉลี่ย 1 เดือน)</span>")}
    ${secRows.map(([k, v, n]) => `<div class="hbar" title="${k}: ${chgTxt(v, 1)} (เฉลี่ยจาก ${n} หุ้น)"><span class="name">${k}</span>
      <div class="track"><div class="mid"></div><div class="f" style="background:${v >= 0 ? "var(--upfill)" : "var(--downfill)"};${v >= 0 ? "left:50%" : "right:50%"};width:${Math.abs(v) / smax * 50}%"></div></div>
      <span class="num small" style="text-align:right">${chgTxt(v, 1)}</span></div>`).join("") || `<p class="small mut">ยังไม่มีข้อมูลกลุ่ม</p>`}</section>`);
  if (bt?.metrics) {
    const m = bt.metrics, worse = m["ผลตอบแทนรวม%"] < (m["ดัชนีอ้างอิง(ซื้อถือ)%"] ?? -1e9);
    out.push(`<section class="card w6">${cardH("ผลทดสอบกลยุทธ์ย้อนหลัง", "#bt", "รายละเอียด")}
      <div class="grid">${kv([["กลยุทธ์นี้", `<span class="${cls(m["ผลตอบแทนรวม%"])}">${pct(m["ผลตอบแทนรวม%"])}</span>`],
        ["ซื้อ SET50 ถือไว้", `<span class="${cls(m["ดัชนีอ้างอิง(ซื้อถือ)%"])}">${pct(m["ดัชนีอ้างอิง(ซื้อถือ)%"])}</span>`],
        ["ขาดทุนสูงสุด (กลยุทธ์)", `<span class="down">${pct(m["ขาดทุนสูงสุดจากจุดสูงสุด(MaxDD)%"])}</span>`],
        ["ขาดทุนสูงสุด (SET50)", `<span class="down">${pct(m["ดัชนีอ้างอิง MaxDD%"])}</span>`]])}</div>
      <div id="bt-mini" style="margin-top:10px"></div>
      <div class="legend"><span><i style="background:var(--accent)"></i>กลยุทธ์</span><span><i style="background:var(--faint)"></i>ซื้อ SET50 ถือไว้</span></div>
      ${worse ? `<p class="warn small" style="margin-bottom:0">ย้อนหลัง ${esc(m["เริ่ม"].slice(0, 4))}–${esc(m["สิ้นสุด"].slice(0, 4))} กลยุทธ์นี้แพ้การซื้อดัชนีถือไว้ — ใช้คัดกรองหุ้นและคุมความเสี่ยง ไม่ใช่ระบบทำกำไรอัตโนมัติ</p>` : ""}</section>`);
  }
  $("#dash").innerHTML = out.join("");

  if (scan.bench) {
    const b = scan.bench;
    hoverChart($("#mkt-chart"), {
      dates: b.d, series: [{ v: b.sma200, color: "var(--c4)", width: 1.5 }, { v: b.c, color: "var(--accent)", width: 2 }],
      fmtTip: i => `${new Date(b.d[i]).toLocaleDateString("th-TH", { day: "numeric", month: "short", year: "2-digit" })} · <b>${fmt(b.c[i])}</b>` + (b.sma200[i] ? ` · เส้น 200 วัน ${fmt(b.sma200[i])}` : ""),
    });
  }
  if (bt?.eq) {
    hoverChart($("#bt-mini"), {
      dates: bt.eq.d, money: true, H: 170,
      series: [{ v: bt.eq.b || [], color: "var(--faint)", width: 1.3, dash: "4 3" }, { v: bt.eq.v, color: "var(--accent)", width: 2 }],
      fmtTip: i => `${bt.eq.d[i].slice(0, 7)} · กลยุทธ์ <b>${fmt(bt.eq.v[i], 0)}</b>` + (bt.eq.b?.[i] ? ` · SET50 ${fmt(bt.eq.b[i], 0)}` : ""),
    });
  }
}

async function showHome() {
  const my = ++homeReq;
  $("#home-date").textContent = new Date().toLocaleDateString("th-TH", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  if (!$("#dash").innerHTML) $("#dash").innerHTML = Array.from({ length: 8 }, (_, i) =>
    `<div class="card skeleton ${i < 4 ? "kpi" : i % 2 ? "w4" : "w8"}"></div>`).join("");
  try {
    const opt = p => p.catch(() => null);
    const [scanJ, newsJ, paper, btJ] = await Promise.all([
      poll("api/scan?list=set", j => { if (my === homeReq) setStatus($("#home-status"), j, "กำลังวิเคราะห์หุ้นทั้งตลาด"); }),
      opt(api("api/news")), opt(api("api/paper?update=0")), opt(api("api/backtest?list=set&years=10"))]);
    if (my !== homeReq) return;
    if (!scanJ.result) throw new Error(scanJ.error || "ยังไม่มีข้อมูล");
    scanData = scanJ.result;
    if (newsJ?.result) newsData = newsJ.result;
    renderHome(scanJ.result, newsJ?.result, paper, btJ?.result);
    const t = d => new Date(d).toLocaleString("th-TH", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    $("#home-status").textContent = `ราคา ณ ${t(scanJ.result.time)}` + (newsJ?.result ? ` · ข่าว ณ ${t(newsJ.result.time)}` : "") + " · อัปเดตอัตโนมัติ";
  } catch (e) { $("#home-status").innerHTML = `<span class="down">${esc(e.message)}</span>`; }
}
$("#dash").addEventListener("click", e => {
  const tr = e.target.closest("[data-go]");
  if (tr) location.hash = tr.dataset.go;
});

// ------------------------------------------------------------ หุ้นเด่น
let scanLimit = 80;
let scanList = STATIC ? "set" : store.get("list", "set"), scanFilter = store.get("filter", "ซื้อ"), scanData = null, scanBusy = false;

function regimeHtml(regimes) {
  return Object.entries(regimes || {}).map(([k, v]) => {
    const c = v.strong ? "var(--up)" : v.ok ? "var(--watch)" : "var(--down)";
    const nm = k.endsWith(".BK") ? "ตลาดหุ้นไทย (SET50)" : "ตลาดอเมริกา (S&P 500)";
    return `<div class="card regime"><span class="dot" style="background:${c}"></span><div><div class="small mut">${nm}</div><b>${esc(v.text)}</b></div></div>`;
  }).join("");
}

function renderScan() {
  const box = $("#scan-rows");
  if (!scanData) { box.innerHTML = ""; return; }
  $("#scan-regime").innerHTML = regimeHtml(scanData.regimes);
  const rows = scanData.rows || [];
  const counts = { "ซื้อ": 0, "รอจังหวะ": 0, "หลีกเลี่ยง": 0 };
  rows.forEach(r => counts[r.status]++);
  $("#scan-filter").innerHTML = ["ซื้อ", "รอจังหวะ", "หลีกเลี่ยง", "ทั้งหมด"].map(f =>
    `<button class="chip ${f === scanFilter ? "on" : ""}" data-f="${f}">${f}<b>${f === "ทั้งหมด" ? rows.length : counts[f]}</b></button>`).join("");
  const q = ($("#scan-q").value || "").trim().toUpperCase();
  let sel = scanFilter === "ทั้งหมด" ? rows : rows.filter(r => r.status === scanFilter);
  if (q) sel = rows.filter(r => r.ticker.includes(q) || (r.name || "").toUpperCase().includes(q));   // ค้นหาทุกสถานะ
  const more = sel.length - scanLimit;
  sel = sel.slice(0, scanLimit);
  if (!sel.length) {
    box.innerHTML = `<div class="empty">${scanFilter === "ซื้อ" ? "วันนี้ยังไม่มีหุ้นที่ผ่านทุกเงื่อนไข<br><span class='small'>การไม่ซื้อก็เป็นการตัดสินใจที่ดีได้ — ดูกลุ่ม \"รอจังหวะ\" แทน</span>" : "ไม่มีรายการ"}</div>`;
    return;
  }
  box.innerHTML = sel.map(r => `
    <a class="item" href="#stock/${encodeURIComponent(r.symbol)}">
      <div class="main">
        <div class="tk">${esc(r.ticker)} <span class="badge ${BADGE[r.status]}">${r.status}</span></div>
        <div class="nm">${esc(r.name || r.sector)} · ซื้อขาย ${fmt(r.value20_m, r.value20_m < 10 ? 1 : 0)} ล้าน/วัน</div>
        <div class="how">${esc(r.how)}</div>
        ${r.signals.length ? `<div class="small up">● ${esc(r.signals.join(" · "))}</div>` : ""}
      </div>
      <div class="side">
        <div class="px num">${fmt(r.close)}</div>
        <div class="small num ${cls(r.roc126)}">6ด ${pct(r.roc126)}</div>
        ${sparkline(r.spark)}
        <span class="score num">${fmt(r.score, 0)}</span>
      </div>
    </a>`).join("") + (more > 0 ? `<button class="btn block" id="scan-more">แสดงเพิ่ม (อีก ${more} ตัว)</button>` : "");
}

async function loadScan(force) {
  if (scanBusy && !force) return;
  scanBusy = true;
  const btn = $("#scan-refresh"); btn.classList.add("spin");
  const base = `api/scan?list=${scanList}`;
  const myList = scanList;
  try {
    await poll(base, j => {
      if (myList !== scanList) return;
      setStatus($("#scan-status"), j, "กำลังดึงราคาและวิเคราะห์หุ้น");
      if (j.result) { scanData = j.result; renderScan(); }
    }, force ? base + "&refresh=1" : base);
  } catch (e) { $("#scan-status").innerHTML = `<span class="down">${esc(e.message)}</span>`; }
  finally { scanBusy = false; btn.classList.remove("spin"); }
}

function showScan() {
  $$("#scan-list button").forEach(b => b.classList.toggle("on", b.dataset.v === scanList));
  if (!scanData || scanData.list !== scanList) { scanData = null; renderScan(); }
  loadScan(false);
}
$("#scan-list").addEventListener("click", e => {
  const v = e.target.dataset.v; if (!v || v === scanList) return;
  scanList = v; store.set("list", v); scanBusy = false; showScan();
});
$("#scan-filter").addEventListener("click", e => {
  const f = e.target.closest("[data-f]")?.dataset.f; if (!f) return;
  scanFilter = f; store.set("filter", f); scanLimit = 80; renderScan();
});
$("#scan-q").addEventListener("input", () => { scanLimit = 80; renderScan(); });
$("#scan-rows").addEventListener("click", e => { if (e.target.id === "scan-more") { scanLimit += 150; renderScan(); } });
$("#scan-refresh").addEventListener("click", () => { scanBusy = false; loadScan(true); toast(STATIC ? "กำลังโหลดข้อมูลล่าสุด…" : "กำลังโหลดราคาล่าสุด…"); });

// ------------------------------------------------------------ ค้นหา
let tickerList = [];
function showSearch() {
  const rec = store.get("recent", []);
  $("#recent").innerHTML = rec.map(t => `<a class="chip" href="#stock/${encodeURIComponent(t)}">${esc(t.replace(".BK", ""))}</a>`).join("");
  if (!tickerList.length) api("api/settings").then(j => {
    tickerList = [...(j.lists.set || []), ...(j.lists.us || [])];
    $("#tickers").innerHTML = tickerList.map(t => `<option value="${esc(t.replace(".BK", ""))}">`).join("");
  }).catch(() => { });
  setTimeout(() => $("#search-in").focus(), 50);
}
$("#search-form").addEventListener("submit", e => {
  e.preventDefault();
  const t = $("#search-in").value.trim().toUpperCase();
  if (t) { $("#search-in").value = ""; location.hash = "#stock/" + encodeURIComponent(t); }
});

// ------------------------------------------------------------ หุ้นรายตัว
let stockReq = 0, chartRange = store.get("range", 125);
async function showStock(t) {
  const my = ++stockReq;
  $("#stock-title").textContent = t.replace(".BK", "");
  const body = $("#stock-body");
  body.innerHTML = `<div class="status"><span class="loader"></span>กำลังวิเคราะห์ ${esc(t)}…</div>`;
  const rec = [t, ...store.get("recent", []).filter(x => x !== t)].slice(0, 10); store.set("recent", rec);
  try {
    const j = await poll(`api/analyze?t=${encodeURIComponent(t)}`, j => {
      if (my !== stockReq) return;
      if (j.state === "running") body.innerHTML = `<div class="status"><span class="loader"></span>กำลังวิเคราะห์ ${esc(t)}… (ครั้งแรกของวันอาจใช้ 1–2 นาที)</div>`;
    });
    if (my !== stockReq) return;
    if (j.state === "error") { body.innerHTML = `<div class="card down">${esc(j.error)}</div>`; return; }
    renderStock(j.result);
  } catch (e) { body.innerHTML = `<div class="card down">${esc(e.message)}</div>`; }
}

function stockChart(a) {
  const c = a.chart, n = Math.min(chartRange, c.d.length), s = c.d.length - n, cut = v => v.slice(s);
  const p = a.row.plan;
  return lineChart({
    dates: cut(c.d),
    series: [
      { v: cut(c.sma200), color: "var(--c4)", width: 1.3 },
      { v: cut(c.sma50), color: "var(--c2)", width: 1.3 },
      { v: cut(c.ema20), color: "var(--c3)", width: 1.2, dash: "3 3" },
      { v: cut(c.c), color: "var(--fg)", width: 1.8 },
    ],
    hlines: [{ y: p.stop, color: "var(--down)", label: "Stop " + fmt(p.stop) }, { y: p.target, color: "var(--up)", label: "เป้า " + fmt(p.target) }],
  });
}

function kv(pairs) { pairs = pairs.filter(p => p); if (pairs.length % 2) pairs.push(["", ""]); return pairs.map(([k, v]) => `<div><div class="k">${k}</div><div class="v">${v}</div></div>`).join(""); }

function renderStock(a) {
  const r = a.row, p = r.plan, i = a.ind;
  $("#stock-title").textContent = r.ticker;
  const td = r.tech_detail, max = { "แนวโน้ม": 30, "โมเมนตัม": 25, "วอลุ่ม": 10, "ความผันผวน": 10 };
  const bars = Object.entries(td).map(([k, v]) => [k, v, max[k]]).concat([["พื้นฐาน", r.fund, 25]])
    .map(([k, v, m]) => `<div class="bar"><span>${k}</span><div class="track"><div class="fill" style="width:${Math.max(0, v / m * 100)}%"></div></div><span class="num small">${fmt(v, 0)}/${m}</span></div>`).join("");
  const fd = r.fund_detail || {};
  const btm = a.bt;
  $("#stock-body").innerHTML = `
    <div class="card">
      <div class="small mut">${esc(r.name)} · ${esc(r.sector)}</div>
      <div class="hero">
        <div><div class="price num">${fmt(r.close)}</div><div class="small num ${cls(r.roc126)}">6 เดือน ${pct(r.roc126)} · ห่างจากไฮ 52 สัปดาห์ ${pct(r.from_high)}</div></div>
        <div style="text-align:right"><span class="badge ${BADGE[r.status]}">${r.status}</span><div class="price num" style="font-size:24px;margin-top:4px">${fmt(r.score, 0)}<span class="small mut">/100</span></div></div>
      </div>
      <div class="how-box">${esc(r.how)}${r.signals.length ? `<div class="small up" style="margin-top:4px">● ${esc(r.signals.join(" · "))}</div>` : ""}</div>
      <div class="bars">${bars}</div>
    </div>
    <div class="card chart">
      <div class="range" id="range">${[[63, "3 เดือน"], [125, "6 เดือน"], [250, "1 ปี"]].map(([v, l]) => `<button class="chip ${v === chartRange ? "on" : ""}" data-r="${v}">${l}</button>`).join("")}</div>
      <div id="chart">${stockChart(a)}</div>
      <div class="legend"><span><i style="background:var(--fg)"></i>ราคา</span><span><i style="background:var(--c3)"></i>EMA20</span><span><i style="background:var(--c2)"></i>SMA50</span><span><i style="background:var(--c4)"></i>SMA200</span></div>
    </div>
    <div class="card">
      <h2>แผนเทรด <span class="small mut">(ทุน ${fmt(a.capital, 0)} · เสี่ยง ${fmt(a.risk * 100, 1)}% ต่อไม้)</span></h2>
      <div class="grid g3">${kv([
        ["ราคาเข้า", fmt(p.entry)], ["ตัดขาดทุน (Stop)", `<span class="down">${fmt(p.stop)}</span> <span class="small mut">${p.stop_pct}%</span>`],
        ["เป้าแรก (2R)", `<span class="up">${fmt(p.target)}</span> <span class="small mut">+${p.target_pct}%</span>`],
        ["จำนวนหุ้น", fmt(p.shares, 0)], ["เงินที่ใช้", p.ccy === "$" ? `$${fmt(p.cost, 0)} <span class="small mut">≈ ${fmt(p.cost_thb, 0)} ฿</span>` : fmt(p.cost, 0) + " ฿"], ["เสียได้สูงสุด", fmt(p.max_loss, 0) + " ฿"],
        ["จุดเบรกเอาต์", fmt(p.breakout_level)], ["โซนย่อซื้อ", `${fmt(p.pullback_zone[0])}–${fmt(p.pullback_zone[1])}`],
        ["มูลค่าซื้อขาย/วัน", fmt(r.value20_m, 0) + " ล้าน"],
      ])}</div>
      ${r.symbol.endsWith(".BK") ? `<p class="small mut" style="margin:10px 0 0">ราคาปัดตามช่วงราคา (tick) ของตลาดแล้ว — ใช้ส่งคำสั่งใน Streaming ได้ทันที: ซื้อ Limit ${fmt(p.entry)} · ตั้ง Stop ${fmt(p.stop)} · ขายทำกำไร ${fmt(p.target)}</p>` : ""}
      <button class="btn primary block" id="paper-buy" style="margin-top:12px">ซื้อในพอร์ตจำลอง</button>
    </div>
    <div class="card"><h2>อินดิเคเตอร์</h2><div class="grid g3">${kv([
        ["RSI (14)", fmt(i.RSI, 1)], ["MACD Histogram", `<span class="${cls(i.MACD_hist)}">${fmt(i.MACD_hist, 3)}</span>`], ["ADX (แรงแนวโน้ม)", fmt(i.ADX, 1)],
        ["SMA50", fmt(i.SMA50)], ["SMA200", fmt(i.SMA200)], ["ATR", `${fmt(i.ATR)} <span class="small mut">${fmt(i.ATR_pct * 100, 1)}%</span>`],
        ["Stochastic %K", fmt(i.STO_K, 0)], ["วอลุ่มเทียบเฉลี่ย", fmt(i.VolRatio, 2) + " เท่า"], ["กรอบ Bollinger", `${fmt(i.BB_lo)}–${fmt(i.BB_up)}`],
      ])}</div></div>
    <div class="card"><h2>ปัจจัยพื้นฐาน</h2>
      ${fd.note ? `<p class="mut small">${esc(fd.note)}</p>` : `<div class="grid g3">${kv(Object.entries(fd).map(([k, v]) => [k, fmt(v, 2)]).concat(
        r.analyst_upside != null ? [["เป้านักวิเคราะห์", `<span class="${cls(r.analyst_upside)}">${pct(r.analyst_upside)}</span> <span class="small mut">${esc(r.analyst_rec || "")}</span>`]] : []))}</div>`}
    </div>
    <div class="card" id="stock-news"><h2>ข่าวล่าสุดของ ${esc(r.ticker)}</h2><div class="status"><span class="loader"></span>กำลังโหลดข่าว…</div></div>
    ${btm ? `<div class="card"><h2>ถ้าใช้กลยุทธ์นี้กับหุ้นตัวนี้ในอดีต</h2>
      <p class="small mut">ตั้งแต่ ${esc(btm["เริ่ม"])} · ลงเต็มพอร์ตทุกไม้</p>
      <div class="grid">${kv([
        ["ผลตอบแทนกลยุทธ์", `<span class="${cls(btm["ผลตอบแทนรวม%"])}">${pct(btm["ผลตอบแทนรวม%"])}</span>`],
        ["ซื้อแล้วถือเฉย ๆ", `<span class="${cls(btm["ซื้อแล้วถือเฉย ๆ%"])}">${pct(btm["ซื้อแล้วถือเฉย ๆ%"])}</span>`],
        ["ขาดทุนสูงสุด (MaxDD)", pct(btm["ขาดทุนสูงสุดจากจุดสูงสุด(MaxDD)%"])], ["จำนวนเทรด / ชนะ", `${btm["จำนวนเทรด"] ?? 0} / ${btm["อัตราชนะ%"] ?? 0}%`],
      ])}</div></div>` : ""}
    <p class="small mut" style="text-align:center">ข้อมูล ณ ${new Date(a.time).toLocaleString("th-TH")} · ไม่ใช่คำแนะนำการลงทุน</p>`;
  (async () => {
    try {
      if (!newsData) { const j = await api("api/news"); if (j.result) newsData = j.result; }
      const items = (newsData?.items || []).filter(n => n.sym.includes(r.ticker)).slice(0, 12);
      const box = $("#stock-news"); if (!box) return;
      box.innerHTML = `<h2>ข่าวล่าสุดของ ${esc(r.ticker)} <span class="small mut">(${items.length})</span></h2>` +
        (items.length ? newsHtml(items) : `<p class="mut small">ยังไม่พบข่าวที่พูดถึง ${esc(r.ticker)} ใน 7 วันที่ผ่านมา</p>`);
    } catch { }
  })();
  $("#range").addEventListener("click", e => {
    const v = +e.target.dataset.r; if (!v) return;
    chartRange = v; store.set("range", v);
    $$("#range .chip").forEach(b => b.classList.toggle("on", +b.dataset.r === v));
    $("#chart").innerHTML = stockChart(a);
  });
  $("#paper-buy").addEventListener("click", async e => {
    const b = e.target; b.disabled = true; b.textContent = "กำลังซื้อ…";
    try { const res = await post("api/paper/buy", { ticker: r.symbol }); toast(res.msg); b.textContent = "ซื้อแล้ว ✓"; }
    catch (err) { toast(err.message); b.disabled = false; b.textContent = "ซื้อในพอร์ตจำลอง"; }
  });
}

// ------------------------------------------------------------ ข่าว
let newsData = null, newsFilter = store.get("newsf", "ทั้งหมด"), newsLimit = 60, newsBusy = false;
function ago(iso) {
  const m = Math.max(0, (Date.now() - new Date(iso)) / 60000);
  return m < 60 ? `${Math.round(m)} นาทีที่แล้ว` : m < 1440 ? `${Math.round(m / 60)} ชม.ที่แล้ว` : `${Math.round(m / 1440)} วันที่แล้ว`;
}
function newsHtml(items) {
  return items.map(n => `<div class="news">
    <a class="nt" href="${esc(n.l)}" target="_blank" rel="noopener">${esc(n.t)}</a>
    ${n.x ? `<div class="x">${esc(n.x)}</div>` : ""}
    <div class="meta"><span class="sen ${n.sen > 0 ? "p" : n.sen < 0 ? "n" : "z"}" title="${n.sen > 0 ? "โทนบวก" : n.sen < 0 ? "โทนลบ" : "กลาง ๆ"}"></span>${esc(n.s)} · ${ago(n.d)}</div>
    ${n.sym.length ? `<div class="tags">${n.sym.map(s => `<a class="tag" href="#stock/${encodeURIComponent(s)}">${esc(s)}</a>`).join("")}</div>` : ""}
  </div>`).join("");
}
async function newsFocus(kind) {
  if (kind === "หุ้นสัญญาณซื้อ" || kind === "หุ้นรอจังหวะ") {
    if (!scanData) { const j = await api(`api/scan?list=set`); scanData = j.result; }
    const st = kind === "หุ้นสัญญาณซื้อ" ? "ซื้อ" : "รอจังหวะ";
    return new Set((scanData?.rows || []).filter(r => r.status === st).map(r => r.ticker));
  }
  if (kind === "พอร์ตจำลอง") {
    const p = await api("api/paper?update=0");
    return new Set(p.positions.map(x => x.ticker.replace(".BK", "")));
  }
  return null;
}
async function renderNews() {
  if (!newsData) return;
  const kinds = ["ทั้งหมด", "หุ้นสัญญาณซื้อ", "หุ้นรอจังหวะ", "พอร์ตจำลอง", "ระบุชื่อหุ้น", "ข่าวดี", "ข่าวร้าย"];
  $("#news-filter").innerHTML = kinds.map(k => `<button class="chip ${k === newsFilter ? "on" : ""}" data-k="${k}">${k}</button>`).join("");
  let items = newsData.items;
  const focus = await newsFocus(newsFilter);
  if (focus) items = items.filter(n => n.sym.some(s => focus.has(s)));
  if (newsFilter === "ระบุชื่อหุ้น") items = items.filter(n => n.sym.length);
  if (newsFilter === "ข่าวดี") items = items.filter(n => n.sen > 0);
  if (newsFilter === "ข่าวร้าย") items = items.filter(n => n.sen < 0);
  const q = ($("#news-q").value || "").trim();
  if (q) { const Q = q.toUpperCase(); items = items.filter(n => n.sym.includes(Q) || n.t.toUpperCase().includes(Q)); }
  const more = items.length - newsLimit;
  $("#news-list").innerHTML = (items.length ? newsHtml(items.slice(0, newsLimit)) : `<div class="empty">ไม่มีข่าวตามเงื่อนไขนี้</div>`)
    + (more > 0 ? `<button class="btn block" id="news-more">แสดงเพิ่ม (อีก ${more} ข่าว)</button>` : "");
}
async function showNews(_, force = false) {
  if (newsBusy) return;
  newsBusy = true; $("#news-refresh").classList.add("spin");
  try {
    await poll("api/news", j => {
      const n = j.result?.items?.length || 0;
      setStatus($("#news-status"), j, "กำลังรวบรวมข่าว");
      if (j.state !== "running" && j.result) $("#news-status").textContent =
        `${fmt(n, 0)} ข่าว ย้อนหลัง 7 วัน จาก ${Object.keys(j.result.sources || {}).length}+ แหล่ง · อัปเดต ${ago(j.result.time)}`;
      if (j.result) { newsData = j.result; renderNews(); }
    }, force ? "api/news?refresh=1" : "api/news");
  } catch (e) { $("#news-status").innerHTML = `<span class="down">${esc(e.message)}</span>`; }
  finally { newsBusy = false; $("#news-refresh").classList.remove("spin"); }
}
$("#news-refresh").addEventListener("click", () => showNews(null, true));
$("#news-filter").addEventListener("click", e => {
  const k = e.target.closest("[data-k]")?.dataset.k; if (!k) return;
  newsFilter = k; store.set("newsf", k); newsLimit = 60; renderNews();
});
$("#news-q").addEventListener("input", () => { newsLimit = 60; renderNews(); });
$("#news-list").addEventListener("click", e => { if (e.target.id === "news-more") { newsLimit += 100; renderNews(); } });

// ------------------------------------------------------------ พอร์ตจำลอง
async function showPaper(_, update = true) {
  const body = $("#paper-body");
  if (!body.innerHTML) body.innerHTML = `<div class="status"><span class="loader"></span>กำลังอัปเดตราคา…</div>`;
  $("#paper-refresh").classList.add("spin");
  try {
    const p = await api("api/paper?update=" + (update ? 1 : 0));
    body.innerHTML = `
      <div class="card">
        <div class="small mut">มูลค่าพอร์ต</div>
        <div class="hero"><div class="price num">${fmt(p.total, 0)}</div><div class="num ${cls(p.gain_pct)}" style="font-weight:700">${pct(p.gain_pct, 2)}</div></div>
        <div class="grid" style="margin-top:10px">${kv([["เงินสด", fmt(p.cash, 0)], ["เงินต้น", fmt(p.start, 0)]])}</div>
      </div>
      <div class="card"><h2>หุ้นที่ถืออยู่ (${p.positions.length})</h2>
        ${p.positions.length ? p.positions.map(x => `
          <div class="pos"><div>
              <a href="#stock/${encodeURIComponent(x.ticker)}" style="color:inherit;font-weight:700">${esc(x.ticker.replace(".BK", ""))}</a>
              <div class="small mut num">${fmt(x.shares, 0)} หุ้น · ทุน ${fmt(x.entry)} · ซื้อ ${esc(x.date)}</div>
              <div class="small num">Stop <span class="down">${fmt(x.stop)}</span></div>
              ${x.alert ? `<div class="alert ${x.alert[0]}">${esc(x.alert[1])}</div>` : ""}
            </div>
            <div style="text-align:right">
              <div class="num" style="font-weight:600">${fmt(x.last)}</div>
              <div class="small num ${cls(x.chg_pct)}">${pct(x.chg_pct, 2)} (${fmt(x.pnl, 0)})</div>
              <button class="btn small" data-sell="${esc(x.ticker)}" style="margin-top:6px;padding:5px 12px">ขาย</button>
            </div></div>`).join("") : `<div class="empty">ยังไม่มีหุ้นในพอร์ต<br><span class="small">เปิดหน้าหุ้นแล้วกด "ซื้อในพอร์ตจำลอง"</span></div>`}
      </div>
      ${p.history.length ? `<div class="card"><h2>ประวัติ</h2><table class="t"><tr><th>วันที่</th><th>รายการ</th><th class="r">ราคา</th><th class="r">กำไร</th></tr>
        ${p.history.map(h => `<tr><td>${esc(h.date)}</td><td>${h.side === "BUY" ? "ซื้อ" : "ขาย"} ${esc(h.ticker.replace(".BK", ""))} ${fmt(h.shares, 0)}</td><td class="r">${fmt(h.price)}</td><td class="r ${cls(h.pnl)}">${h.pnl != null ? fmt(h.pnl, 0) : ""}</td></tr>`).join("")}</table></div>` : ""}
      <button class="btn danger block" id="paper-reset">เริ่มพอร์ตจำลองใหม่</button>`;
  } catch (e) { body.innerHTML = `<div class="card down">${esc(e.message)}</div>`; }
  finally { $("#paper-refresh").classList.remove("spin"); }
}
$("#paper-refresh").addEventListener("click", () => showPaper(null, true));
$("#paper-body").addEventListener("click", async e => {
  const t = e.target.dataset.sell;
  if (t) {
    if (!confirm(`ขาย ${t.replace(".BK", "")} ทั้งหมดที่ราคาล่าสุด?`)) return;
    e.target.disabled = true;
    try { toast((await post("api/paper/sell", { ticker: t })).msg); showPaper(null, false); }
    catch (err) { toast(err.message); e.target.disabled = false; }
  }
  if (e.target.id === "paper-reset" && confirm("ล้างพอร์ตจำลองทั้งหมดและเริ่มใหม่ด้วยเงินทุนตามที่ตั้งค่าไว้?")) {
    toast((await post("api/paper/reset")).msg); showPaper(null, false);
  }
});

// ------------------------------------------------------------ ทดสอบย้อนหลัง
let btList = "set", btReq = 0;
async function showBt(_, force = false) {
  $$("#bt-list button").forEach(b => b.classList.toggle("on", b.dataset.v === btList));
  const my = ++btReq, base = `api/backtest?list=${btList}&years=${$("#bt-years").value}`;
  $("#bt-body").innerHTML = "";
  try {
    await poll(base, j => {
      if (my !== btReq) return;
      setStatus($("#bt-status"), j, "กำลังทดสอบย้อนหลัง");
      if (j.result) renderBt(j.result);
    }, force ? base + "&refresh=1" : base);
  } catch (e) { $("#bt-status").innerHTML = `<span class="down">${esc(e.message)}</span>`; }
}
function renderBt(r) {
  const m = r.metrics, yr = m["รายปี%"] || {};
  const ymax = Math.max(5, ...Object.values(yr).map(Math.abs));
  const bName = r.list === "set" ? "SET50 (TDEX)" : "S&P 500";
  $("#bt-body").innerHTML = `
    <div class="card">
      <div class="small mut">${esc(m["เริ่ม"])} ถึง ${esc(m["สิ้นสุด"])} · หุ้น ${r.n_stocks} ตัว · ทุน ${fmt(m["เงินต้น"], 0)}</div>
      <div class="grid" style="margin-top:10px">${kv([
        ["กลยุทธ์ (รวม)", `<span class="${cls(m["ผลตอบแทนรวม%"])}">${pct(m["ผลตอบแทนรวม%"])}</span>`],
        [`ซื้อ ${bName} ถือไว้`, `<span class="${cls(m["ดัชนีอ้างอิง(ซื้อถือ)%"])}">${pct(m["ดัชนีอ้างอิง(ซื้อถือ)%"])}</span>`],
        ["ผลตอบแทนต่อปี", pct(m["ผลตอบแทนต่อปี(CAGR)%"])], ["มูลค่าสุดท้าย", fmt(m["มูลค่าสุดท้าย"], 0)],
        ["ขาดทุนสูงสุด (กลยุทธ์)", `<span class="down">${pct(m["ขาดทุนสูงสุดจากจุดสูงสุด(MaxDD)%"])}</span>`],
        ["ขาดทุนสูงสุด (ดัชนี)", `<span class="down">${pct(m["ดัชนีอ้างอิง MaxDD%"])}</span>`],
        ["จำนวนเทรด", fmt(m["จำนวนเทรด"], 0)], ["อัตราชนะ", fmt(m["อัตราชนะ%"], 1) + "%"],
        ["ชนะเฉลี่ย / แพ้เฉลี่ย", `<span class="up">${pct(m["กำไรเฉลี่ยไม้ชนะ%"])}</span> / <span class="down">${pct(m["ขาดทุนเฉลี่ยไม้แพ้%"])}</span>`],
        ["Profit Factor", fmt(m["Profit Factor"], 2)], ["Sharpe", fmt(m["Sharpe"], 2)], ["ถือเฉลี่ย", fmt(m["ถือเฉลี่ย(วัน)"], 0) + " วัน"],
      ])}</div>
    </div>
    <div class="card chart"><h2>มูลค่าพอร์ต</h2>
      ${lineChart({ dates: r.eq.d, money: true, series: [{ v: r.eq.b || [], color: "var(--mut)", width: 1.3, dash: "4 3" }, { v: r.eq.v, color: "var(--accent)", width: 2 }] })}
      <div class="legend"><span><i style="background:var(--accent)"></i>กลยุทธ์</span><span><i style="background:var(--mut)"></i>ซื้อ ${bName} ถือไว้</span></div>
    </div>
    <div class="card"><h2>ผลตอบแทนรายปี</h2>
      ${Object.entries(yr).map(([y, v]) => `<div class="yr"><span>${y}</span><div class="track"><div class="mid"></div>
        <div class="f" style="background:${v >= 0 ? "var(--up)" : "var(--down)"};${v >= 0 ? `left:50%` : `right:50%`};width:${Math.abs(v) / ymax * 50}%"></div></div>
        <span class="num r ${cls(v)}" style="text-align:right">${pct(v)}</span></div>`).join("")}
    </div>
    <div class="card"><h2>เทรดล่าสุด</h2><table class="t"><tr><th>หุ้น</th><th>ช่วง</th><th class="r">ผล</th><th>เหตุผลขาย</th></tr>
      ${r.trades.map((t, k) => `<tr ${k >= 15 ? 'class="more" hidden' : ''}><td><b>${esc(t.ticker.replace(".BK", ""))}</b></td><td class="small">${esc(t.entry_date.slice(2))}<br>${esc(t.exit_date.slice(2))}</td>
        <td class="r ${cls(t.ret_pct)}">${pct(t.ret_pct)}</td><td class="small">${esc(t.reason)}</td></tr>`).join("")}</table>${r.trades.length > 15 ? `<button class="btn block" style="margin-top:8px" onclick="this.previousElementSibling.querySelectorAll('.more').forEach(x=>x.hidden=false);this.remove()">ดูเพิ่ม</button>` : ""}</div>
    ${m["ผลตอบแทนรวม%"] < (m["ดัชนีอ้างอิง(ซื้อถือ)%"] ?? -1e9) ? `<p class="warn small"><b>ผลย้อนหลังของกลยุทธ์นี้แพ้การซื้อ ${bName} แล้วถือไว้เฉย ๆ</b> — ใช้เป็นเครื่องมือคัดกรองหุ้นและคุมความเสี่ยง ไม่ใช่ระบบทำกำไรอัตโนมัติ</p>` : ""}
    <p class="warn small">ทดสอบด้วยรายชื่อหุ้นปัจจุบัน (หุ้นที่เคยล้มหายไปไม่ถูกนับ) และใช้เฉพาะสัญญาณเทคนิค ผลจริงมักแย่กว่านี้</p>
    <button class="btn block" id="bt-rerun">คำนวณใหม่ด้วยข้อมูลล่าสุด</button>`;
  $("#bt-rerun").onclick = () => showBt(null, true);
}
$("#bt-list").addEventListener("click", e => { const v = e.target.dataset.v; if (v && v !== btList) { btList = v; showBt(); } });
$("#bt-years").addEventListener("change", () => showBt());

// ------------------------------------------------------------ ตั้งค่า
function telegramCard(c) {
  const when = t => t ? new Date(t).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" }) : "-";
  return `<div class="card"><h2>แจ้งเตือนผ่าน Telegram</h2>
    ${c.bot ? `<a class="btn primary block" href="https://t.me/${esc(c.bot)}" target="_blank" rel="noopener">เปิดบอท @${esc(c.bot)}</a>` : ""}
    <ul class="small" style="margin-top:10px">
      <li>ทุกวันหลังตลาดปิด: สรุปหุ้นที่มีสัญญาณซื้อ พร้อมจุด Stop/เป้า/จำนวนหุ้น</li>
      <li>ระหว่างวัน: เตือนเมื่อหุ้นที่ถือชน Stop และเมื่อหุ้น "รอจังหวะ" ทะลุจุดซื้อ</li>
      <li>บอกบอทเมื่อซื้อขายจริงใน KS เพื่อให้บอทเฝ้าจุดขายให้:<br>
        <code>/buy GULF 300 61.25</code> · <code>/sell GULF</code> · <code>/port</code> · <code>/stock PTT</code> · <code>/help</code></li>
    </ul>
    <p class="mut small">บอทตอบกลับภายในประมาณ 30 นาทีช่วงตลาดเปิด (นอกเวลาตลาดอาจนานถึง 3 ชั่วโมง)</p>
    <p class="mut small">ข้อมูลหุ้นไทยอัปเดต ${when(c.updated_set)} · หุ้นอเมริกา ${when(c.updated_us)}</p></div>`;
}
async function showSet() {
  try {
    const [s, c] = await Promise.all([api("api/settings"), api("api/connect")]);
    const f = $("#set-form"), v = s.settings;
    f.CAPITAL.value = v.CAPITAL; f.RISK_PER_TRADE.value = +(v.RISK_PER_TRADE * 100).toFixed(2);
    f.MAX_POSITION_PCT.value = +(v.MAX_POSITION_PCT * 100).toFixed(1); f.MAX_POSITIONS.value = v.MAX_POSITIONS;
    $("#connect").innerHTML = c.local ? `<div class="card"><h2>เปิดบนมือถือ</h2>
      <div class="qr">${c.qr}<div class="small">
        <p style="margin-top:0">1. ต่อมือถือเข้า WiFi เดียวกับคอมพิวเตอร์นี้<br>2. สแกน QR ด้วยกล้องมือถือ<br>3. กด "แชร์ → เพิ่มไปยังหน้าจอโฮม" เพื่อใช้เหมือนแอป</p>
        <p class="mut">หรือพิมพ์ <b class="num">${esc(c.url.split("/?")[0])}</b><br>PIN: <b class="num" style="font-size:18px;letter-spacing:.15em">${esc(c.pin)}</b></p>
      </div></div></div>` : c.static ? telegramCard(c) : "";
  } catch (e) { toast(e.message); }
}
$("#set-form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target;
  try {
    await post("api/settings", {
      CAPITAL: +f.CAPITAL.value, RISK_PER_TRADE: +f.RISK_PER_TRADE.value / 100,
      MAX_POSITION_PCT: +f.MAX_POSITION_PCT.value / 100, MAX_POSITIONS: +f.MAX_POSITIONS.value,
    });
    scanData = null; toast("บันทึกแล้ว — ผลสแกนจะคำนวณใหม่ตามเงินทุนนี้");
  } catch (err) { toast(err.message); }
});

route();
