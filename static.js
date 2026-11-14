/* โหมดเว็บแบบไม่มีเซิร์ฟเวอร์ (GitHub Pages)
   จำลอง API เดิมด้วยไฟล์ข้อมูลที่คำนวณไว้ล่วงหน้า (data/*.json)
   ส่วนพอร์ตจำลองและการตั้งค่า เก็บในเครื่องของแต่ละคน (localStorage) */
(function () {
  "use strict";
  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { } },
  };
  let metaP = null;
  const cache = new Map();

  function meta(fresh) {
    if (!metaP || fresh) metaP = fetch("data/meta.json?t=" + Date.now()).then(r => {
      if (!r.ok) throw new Error("ยังไม่มีข้อมูล — ระบบจะสร้างให้หลังตลาดปิด");
      return r.json();
    });
    return metaP;
  }
  async function getJSON(path, fresh) {
    const m = await meta(fresh);
    const key = path + "?v=" + encodeURIComponent(m.time);
    if (!fresh && cache.has(key)) return structuredClone(cache.get(key));
    const r = await fetch(key, { cache: fresh ? "reload" : "default" });
    if (!r.ok) throw new Error("NOTFOUND");
    const j = await r.json();
    cache.set(key, j);
    return structuredClone(j);
  }
  async function settings() {
    const m = await meta();
    return Object.assign({}, m.defaults, ls.get("settings", {}));
  }
  async function norm(t) {
    t = String(t || "").trim().toUpperCase();
    if (t.includes(".") || t.startsWith("^")) return t;
    const m = await meta();
    return (m.lists.us || []).includes(t) ? t : t + ".BK";
  }
  const isTh = t => t.endsWith(".BK");

  /** คำนวณจำนวนหุ้นใหม่ตามเงินทุน/ความเสี่ยงที่ผู้ใช้ตั้งไว้ในเครื่องนี้ */
  async function replan(plan, sym, strong) {
    const m = await meta(), s = await settings();
    const fx = isTh(sym) ? 1 : (m.fx_usd_thb || 33);
    const cap = s.CAPITAL * (strong === false ? 0.5 : 1) / fx;
    const risk = plan.entry - plan.stop;
    const lot = isTh(sym) ? m.lot_th : 1;
    let sh = Math.min(cap * s.RISK_PER_TRADE / risk, cap * s.MAX_POSITION_PCT / plan.entry);
    sh = Math.max(0, Math.floor(sh / lot) * lot);
    return Object.assign(plan, {
      shares: sh, cost: Math.round(sh * plan.entry), max_loss: Math.round(sh * risk * fx),
      cost_thb: Math.round(sh * plan.entry * fx), fx,
    });
  }

  // ---------------------------------------------------------- พอร์ตจำลอง (เก็บในเครื่อง)
  async function paperLoad() {
    const s = await settings();
    return ls.get("paper", { cash: s.CAPITAL, start: s.CAPITAL, positions: {}, history: [] });
  }
  async function stock(sym, fresh) {
    try { return await getJSON(`data/stocks/s_${sym}.json`, fresh); }
    catch { throw new Error(`ไม่มีข้อมูล ${sym.replace(".BK", "")} — เว็บนี้มีเฉพาะหุ้นในรายชื่อที่ระบบติดตาม`); }
  }
  async function paperBuy(body) {
    const m = await meta(), s = await settings(), sym = await norm(body.ticker);
    const p = await paperLoad();
    if (p.positions[sym]) throw new Error(`มี ${sym.replace(".BK", "")} อยู่ในพอร์ตแล้ว`);
    const d = await stock(sym);
    const px = d.ind.Close, stop = px - m.stop_mult * d.ind.ATR, fx = isTh(sym) ? 1 : m.fx_usd_thb;
    const equity = p.cash + Object.values(p.positions).reduce((a, v) => a + v.shares * v.last * (v.fx || 1), 0);
    const lot = isTh(sym) ? m.lot_th : 1;
    let sh = body.shares || Math.min(equity * s.RISK_PER_TRADE / ((px - stop) * fx), equity * s.MAX_POSITION_PCT / (px * fx));
    sh = Math.floor(sh / lot) * lot;
    if (sh <= 0) throw new Error("จำนวนหุ้นตามเกณฑ์ความเสี่ยงไม่ถึง 1 lot (เพิ่มเงินทุนในหน้าตั้งค่า)");
    const cost = sh * px * fx * (1 + m.cost);
    if (cost > p.cash) throw new Error(`เงินสดไม่พอ (ต้องใช้ ${Math.round(cost).toLocaleString()} มี ${Math.round(p.cash).toLocaleString()})`);
    const today = d.chart.d.at(-1);
    p.cash -= cost;
    p.positions[sym] = { shares: sh, entry: px, stop: +stop.toFixed(2), risk: px - stop, high: px, last: px, date: today, fx };
    p.history.unshift({ date: today, side: "BUY", ticker: sym, shares: sh, price: px });
    ls.set("paper", p);
    return { msg: `ซื้อ ${sym.replace(".BK", "")} ${sh.toLocaleString()} หุ้น @ ${px.toFixed(2)}  Stop ${stop.toFixed(2)}` };
  }
  async function paperSell(body) {
    const m = await meta(), sym = await norm(body.ticker), p = await paperLoad();
    const pos = p.positions[sym];
    if (!pos) throw new Error("ไม่มีหุ้นนี้ในพอร์ต");
    const d = await stock(sym), px = d.ind.Close, fx = isTh(sym) ? 1 : m.fx_usd_thb;
    const pnl = pos.shares * (px * fx * (1 - m.cost) - pos.entry * (pos.fx || 1) * (1 + m.cost));
    p.cash += pos.shares * px * fx * (1 - m.cost);
    delete p.positions[sym];
    p.history.unshift({ date: d.chart.d.at(-1), side: "SELL", ticker: sym, shares: pos.shares, price: px, pnl: Math.round(pnl) });
    ls.set("paper", p);
    return { msg: `ขาย ${sym.replace(".BK", "")} @ ${px.toFixed(2)} กำไร/ขาดทุน ${Math.round(pnl).toLocaleString()}` };
  }
  async function paperStatus() {
    const m = await meta(), p = await paperLoad();
    const rows = [], alerts = [];
    let total = p.cash;
    for (const [sym, v] of Object.entries(p.positions)) {
      let alert = null;
      try {
        const d = await stock(sym), c = d.chart, i = d.ind;
        const since = c.d.map((x, k) => x >= v.date ? c.c[k] : null).filter(x => x != null);
        v.last = i.Close;
        v.high = Math.max(v.high, ...since);
        v.stop = +Math.max(v.stop, v.high - m.trail_mult * i.ATR).toFixed(2);
        if (i.Low <= v.stop) alert = ["sell", `ชน Stop ${v.stop} → ควรขาย`];
        else if (i.exit_trend) alert = ["sell", "หลุดเส้น 200 วัน → ควรขาย"];
        else if (v.last >= v.entry + m.target_r * (v.risk || m.stop_mult * i.ATR))
          alert = ["target", `ถึงเป้า ${m.target_r}R → ขายครึ่งหนึ่ง ที่เหลือถือตาม trailing stop`];
      } catch { }
      const fx = isTh(sym) ? 1 : m.fx_usd_thb;
      const value = v.shares * v.last * fx;
      total += value;
      rows.push({
        ticker: sym, shares: v.shares, entry: v.entry, last: v.last, stop: v.stop, date: v.date,
        value: Math.round(value), chg_pct: +((v.last / v.entry - 1) * 100).toFixed(2),
        pnl: Math.round(v.shares * (v.last * fx - v.entry * (v.fx || 1))), alert,
      });
      if (alert) alerts.push(`${sym.replace(".BK", "")}: ${alert[1]}`);
    }
    ls.set("paper", p);
    return {
      cash: Math.round(p.cash), total: Math.round(total), start: p.start,
      gain_pct: +((total / p.start - 1) * 100).toFixed(2), positions: rows, alerts, history: p.history.slice(0, 50),
    };
  }

  // ---------------------------------------------------------- ตัวจำลอง API
  const done = result => ({ state: "done", result });

  window.staticApi = async function (url, opts) {
    const u = new URL(url, location.href), q = u.searchParams;
    const path = u.pathname.replace(/^.*\/api\//, "");
    const body = opts?.body ? JSON.parse(opts.body) : {};
    const fresh = q.get("refresh") === "1";
    switch (path) {
      case "scan": {
        const lst = q.get("list") || "set";
        const d = await getJSON(`data/scan_${lst}.json`, fresh);
        const reg = Object.values(d.regimes || {})[0] || {};
        for (const r of d.rows) {
          await replan(r.plan, r.symbol, reg.strong);
          r.how = r.how.replace(/ \(ทุนตามเกณฑ์.*\)$/, "") +
            (r.plan.shares === 0 && r.status !== "หลีกเลี่ยง" ? " (ทุนตามเกณฑ์ความเสี่ยงไม่พอซื้อ 1 lot — เพิ่มทุนหรือข้าม)" : "");
        }
        return done(d);
      }
      case "analyze": {
        const sym = await norm(q.get("t"));
        let d;
        try { d = await getJSON(`data/stocks/s_${sym}.json`); }
        catch {
          const m = await meta(), s = sym.replace(".BK", "");
          const listed = (m.lists.set || []).includes(sym);
          return { state: "error", error: listed
            ? `${s} ซื้อขายน้อยกว่า 1 ล้านบาทต่อวัน ระบบจึงไม่ทำหน้าวิเคราะห์ (หุ้นสภาพคล่องต่ำ เสี่ยงซื้อแล้วขายไม่ออก ราคาเหวี่ยงแรง)`
            : `ไม่พบหุ้น ${s} ในตลาดหลักทรัพย์ฯ — ตรวจชื่อย่ออีกครั้ง` };
        }
        const s = await settings();
        await replan(d.row.plan, sym, d.regime?.strong);
        d.capital = s.CAPITAL; d.risk = s.RISK_PER_TRADE;
        return done(d);
      }
      case "backtest":
        return done(await getJSON(`data/backtest_${q.get("list") || "set"}_10.json`, fresh));
      case "settings": {
        const m = await meta();
        if (opts?.method === "POST") {
          ls.set("settings", body);
          const p = ls.get("paper", null);
          if (p && !Object.keys(p.positions).length && !p.history.length) ls.set("paper", null);
        }
        return { settings: await settings(), lists: m.lists };
      }
      case "connect": {
        const m = await meta();
        return { static: true, bot: m.bot, time: m.time, updated_set: m.updated_set, updated_us: m.updated_us };
      }
      case "news":
        return done(await getJSON("data/news.json", fresh));
      case "paper": return paperStatus();
      case "paper/buy": return paperBuy(body);
      case "paper/sell": return paperSell(body);
      case "paper/reset": {
        const s = await settings();
        ls.set("paper", { cash: s.CAPITAL, start: s.CAPITAL, positions: {}, history: [] });
        return { msg: `เริ่มพอร์ตจำลองใหม่ เงินทุน ${s.CAPITAL.toLocaleString()}` };
      }
    }
    throw new Error("ไม่รองรับในเว็บโหมดนี้");
  };
})();
