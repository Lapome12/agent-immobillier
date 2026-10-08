// Agents immobiliers : tableau de bord + discussion avec les agents.
// Les données viennent de data/*.json, publiées par le workflow GitHub après chaque tour.

const KEY_STORAGE = "immo-anthropic-key";
const CHAT_MODEL = "claude-opus-5-5";
const COLORS = { hyeres: "var(--hyeres)", grenoble: "var(--grenoble)", station: "var(--station)", renovation: "var(--renovation)", manager: "var(--manager)" };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const pct = (x, d = 2) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)} %`;
const money = (x) => `${Math.round(x).toLocaleString("fr-FR")} €`;

let agents, state, journal = "";
// Version Artifact claude.ai : les données sont intégrées à la page et la discussion
// passe par la capacité « sample » (le compte Claude de la personne, sans clé API).
const embedded = document.getElementById("immo-data");
let samplePromise = null;
function getSample() {
  if (!window.claude?.use) return Promise.resolve(null);
  return (samplePromise ??= window.claude.use("sample").catch(() => null));
}
const histories = {}; // historique de discussion par agent (en mémoire)

function metrics(curve) {
  if (!curve || curve.length < 2) return { ret: 0, mdd: 0 };
  let peak = curve[0], mdd = 0;
  for (const v of curve) { peak = Math.max(peak, v); mdd = Math.max(mdd, 1 - v / peak); }
  return { ret: curve.at(-1) / curve[0] - 1, mdd };
}

function ranking() {
  return Object.keys(state.agents).sort((a, b) => (state.agents[b].nav.at(-1) ?? 1) - (state.agents[a].nav.at(-1) ?? 1));
}

function link(o) {
  const t = esc(o.titre);
  return /^https?:/.test(o.url || "") ? `<a href="${esc(o.url)}" target="_blank" rel="noopener">${t}</a>` : t;
}

// ---------- rendu ----------

function renderHeader() {
  const date = state.dates.at(-1) || "";
  $("subtitle").textContent = `Semaine ${state.round} · dernier tour ${date} · investissement fictif`;
  const m = location.hostname.match(/^([^.]+)\.github\.io$/);
  const repo = location.pathname.split("/").filter(Boolean)[0];
  if (embedded) $("key-btn").classList.add("hidden");
  if (localInfo) return renderLocalControls();
  if (m && repo) $("run-link").href = `https://github.com/${m[1]}/${repo}/actions/workflows/immobilier.yml`;
  else $("run-link").classList.add("hidden");
}

function renderKpis() {
  const keys = Object.keys(state.agents);
  const n = Math.min(...keys.map((k) => state.agents[k].curve.length));
  const fund = Array.from({ length: n }, (_, i) => keys.reduce((a, k) => a + state.agents[k].curve[i], 0));
  const fm = metrics(fund);
  const leader = agents.agents[ranking()[0]];
  const biens = keys.reduce((a, k) => a + state.agents[k].biens.length, 0);
  const loyers = keys.reduce((a, k) => a + (state.agents[k].loyers_cumules || 0), 0);
  $("kpis").innerHTML = [
    ["Valeur de l'enveloppe", money(fund.at(-1) ?? 0)],
    ["Rendement", pct(fm.ret)],
    ["Biens achetés", biens],
    ["Loyers nets encaissés", money(loyers)],
    ["En tête", `${leader.emoji} ${esc(leader.name)}`],
  ].map(([l, v]) => `<div class="kpi"><span class="muted small">${l}</span><b>${v}</b></div>`).join("");
  return fund;
}

function oppRow(k, o) {
  const a = agents.agents[k];
  const agent = `<td><span class="dot" style="background:${COLORS[k]}"></span>${esc(a.name)}</td>`;
  return `<tr>${agent}<td>${link(o)}<span class="muted small">${esc(o.commune)} · ${Math.round(o.surface_m2)} m² · DPE ${esc(o.dpe)}</span></td>
    <td class="num">${money(o.prix)}<span class="muted small">+ travaux ${money(o.travaux_estimes)}</span></td>
    <td class="num">${money(o.prix_m2)}/m²<span class="muted small">marché ${money(o.mediane_m2)}/m²</span></td>
    <td class="num ${o.marge >= 0 ? "up" : "down"}">${pct(o.marge, 0)}</td>
    <td class="num">${(o.rendement_net * 100).toFixed(1)} %${o.loyer_plafonne ? " *" : ""}</td>
    <td class="score">${o.score}</td></tr>`;
}

function renderBest() {
  const all = Object.entries(state.agents).flatMap(([k, a]) => a.opportunites.filter((o) => o.valide).map((o) => [k, o]));
  all.sort((x, y) => y[1].score - x[1].score);
  $("best").innerHTML = all.length ? `<table><tr><th>Agent</th><th>Annonce</th><th>Prix</th><th>Prix au m²</th><th>Marge</th><th>Rendement net</th><th>Score</th></tr>
    ${all.slice(0, 10).map(([k, o]) => oppRow(k, o)).join("")}</table>` : `<p class="muted" style="padding:12px">Aucune opportunité pour le moment.</p>`;
}

function renderAgents() {
  const order = ranking();
  const lastReview = state.reviews.at(-1);
  const manager = `
    <button class="agent" style="--c:${COLORS.manager}" data-agent="manager">
      <div class="agent-top"><div class="avatar">${agents.manager.emoji}</div>
        <div><b>${esc(agents.manager.name)}</b><div class="muted small">${esc(agents.manager.role)}</div></div>
        <span class="rank">${state.reviews.length} revue(s)</span></div>
      <p class="quote">${esc(agents.manager.persona)}</p>
      <p class="quote">${lastReview ? "« " + esc(lastReview.commentary) + " »" : `Pas encore de revue : la première a lieu à la semaine ${agents.manager_every || 4}.`}</p>
    </button>`;
  const cards = order.map((k, i) => {
    const a = agents.agents[k], t = state.agents[k], m = metrics(t.nav);
    const biens = t.biens.map((b) => `<span class="chip">${esc(b.commune)} · ${Math.round(b.surface_m2)} m²</span>`).join("") || `<span class="chip">aucun bien</span>`;
    return `
      <button class="agent" style="--c:${COLORS[k]}" data-agent="${k}">
        <div class="agent-top"><div class="avatar">${a.emoji}</div>
          <div><b>${esc(a.name)}</b><div class="muted small">${esc(a.role)}</div></div>
          <span class="rank">#${i + 1}</span></div>
        <div class="stats">
          <div><span>Valeur</span>${money(t.curve.at(-1) ?? 0)}</div>
          <div><span>Rendement</span><b class="${m.ret >= 0 ? "up" : "down"}">${pct(m.ret)}</b></div>
          <div><span>Trésorerie</span>${money(t.cash)}</div>
        </div>
        <div class="pos">${biens}<span class="chip">part ${Math.round(t.budget * 100)} %</span></div>
        <p class="quote">${esc(t.analyse || a.persona)}</p>
      </button>`;
  }).join("");
  $("agents").innerHTML = manager + cards;
  document.querySelectorAll(".agent").forEach((el) => el.addEventListener("click", () => openChat(el.dataset.agent)));
}

function renderChart(fund) {
  const series = Object.fromEntries(Object.keys(state.agents).map((k) => [k, state.agents[k].nav]));
  if (fund.length) series.fonds = fund.map((v) => v / fund[0]);
  const all = Object.values(series).flat();
  const n = Math.max(...Object.values(series).map((s) => s.length));
  $("legend").innerHTML = Object.keys(series).map((k) =>
    `<span><span class="dot" style="background:${COLORS[k] || "var(--fg)"}"></span>${k === "fonds" ? "Enveloppe totale (pointillés)" : esc(agents.agents[k].name)}</span>`).join("");
  if (n < 2) { $("chart").innerHTML = `<p class="muted">Les courbes apparaîtront après la deuxième semaine.</p>`; return; }
  const W = 1000, H = 320, L = 60, P = 20;
  let lo = Math.min(...all), hi = Math.max(...all); if (hi === lo) hi = lo + 1e-6;
  const x = (i) => L + (i * (W - L - P)) / (n - 1), y = (v) => H - P - ((v - lo) * (H - 2 * P)) / (hi - lo);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Performance comparée">`;
  for (const f of [0, 0.25, 0.5, 0.75, 1]) {
    const v = lo + f * (hi - lo);
    svg += `<line class="grid" x1="${L}" x2="${W - P}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${pct(v - 1, 1)}</text>`;
  }
  svg += `<text x="${L}" y="${H - 2}">${esc(state.dates[0] || "")}</text><text x="${W - P}" y="${H - 2}" text-anchor="end">${esc(state.dates.at(-1) || "")}</text>`;
  for (const [k, s] of Object.entries(series)) {
    const pts = s.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    svg += `<polyline points="${pts}" fill="none" stroke="${COLORS[k] || "var(--fg)"}" stroke-width="2.2" ${k === "fonds" ? 'stroke-dasharray="6 5"' : ""}/>`;
  }
  $("chart").innerHTML = svg + "</svg>";
}

function renderTabs() {
  const biens = Object.entries(state.agents).flatMap(([k, a]) => a.biens.map((b) => [k, b]));
  $("tab-biens").innerHTML = biens.length ? `<div class="table-wrap"><table><tr><th>Agent</th><th>Bien</th><th>Coût total</th><th>Valeur actuelle</th><th>Plus-value</th><th>Loyer</th></tr>
    ${biens.map(([k, b]) => {
      const v = b.valeur_actuelle ?? b.valeur_estimee;
      return `<tr><td><span class="dot" style="background:${COLORS[k]}"></span>${esc(agents.agents[k].name)}</td>
        <td>${link(b)}<span class="muted small">${esc(b.commune)} · ${Math.round(b.surface_m2)} m² · acheté ${esc(b.achat_date)}</span></td>
        <td class="num">${money(b.cout_total)}</td><td class="num">${money(v)}</td>
        <td class="num ${v >= b.cout_total ? "up" : "down"}">${pct(v / b.cout_total - 1, 0)}</td>
        <td class="num">${money(b.loyer_retenu)}/mois</td></tr>`;
    }).join("")}</table></div>` : `<p class="muted">Aucun bien acheté pour le moment.</p>`;
  $("tab-reviews").innerHTML = state.reviews.length ? [...state.reviews].reverse().map((r) => `
    <div class="review"><b>Semaine ${r.round}</b> <span class="muted small">· ${esc(r.date)}</span>
      <p>${esc(r.commentary)}</p>
      ${r.coup_de_coeur ? `<p><b>Coup de cœur :</b> ${esc(r.coup_de_coeur)}</p>` : ""}
      <div class="pos">${Object.entries(r.budgets).map(([k, w]) => `<span class="chip">${agents.agents[k].emoji} ${esc(agents.agents[k].name)} ${Math.round(w * 100)} %</span>`).join("")}</div>
    </div>`).join("") : `<p class="muted">${esc(agents.manager.name)} fait sa première revue à la semaine ${agents.manager_every || 4}.</p>`;
  $("tab-journal").innerHTML = `<div class="journal">${esc(journal.split("\n## ").slice(-15).reverse().map((b, i) => (i < 14 ? "## " : "") + b).join("\n\n")) || "Journal vide."}</div>`;
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${b.dataset.tab}`));
  }));
}

// ---------- discussion ----------

function leaderboardText() {
  return ranking().map((k, i) => {
    const a = agents.agents[k], t = state.agents[k], m = metrics(t.nav);
    return `${i + 1}. ${a.name} (${a.role}) : valeur ${money(t.curve.at(-1) ?? 0)}, rendement ${pct(m.ret)}, ${t.biens.length} bien(s), trésorerie ${money(t.cash)}, part de l'enveloppe ${Math.round(t.budget * 100)} %`;
  }).join("\n");
}

function oppText(o) {
  return `${o.titre} (${o.commune}, ${Math.round(o.surface_m2)} m², ${money(o.prix)}, ${o.valide ? `marge ${pct(o.marge, 0)}, rendement net ${(o.rendement_net * 100).toFixed(1)} %, score ${o.score}` : `écartée : ${o.motif}`}) ${o.url}`;
}

function systemPrompt(key) {
  const common = `Nous sommes dans une équipe de 4 agents immobiliers IA en compétition, chacun sur un secteur (Hyères, Grenoble, stations de ski, biens à rénover), et une directrice d'investissement IA qui leur répartit une enveloppe. Les annonces et les prix de référence (DVF) sont réels ; les achats et les loyers sont fictifs.
Semaine actuelle : ${state.round}, dernier tour : ${state.dates.at(-1) || "aucun"}.
Classement :
${leaderboardText()}

Tu discutes maintenant avec Eliott, le propriétaire de l'enveloppe. Réponds en français, dans ton personnage, de façon concise et concrète, en t'appuyant sur les données ci-dessous. Tu ne peux pas acheter depuis cette discussion : les décisions se prennent pendant les tours hebdomadaires. Rappelle si besoin qu'un vrai achat demande de visiter le bien et de vérifier les diagnostics et les documents de copropriété.`;
  if (key === "manager") {
    const reviews = state.reviews.slice(-5).map((r) => `Semaine ${r.round} (${r.date}) : ${r.commentary} Coup de cœur : ${r.coup_de_coeur || "-"}`).join("\n") || "aucune";
    return `Tu es ${agents.manager.name}, ${agents.manager.role} de l'équipe. Ta personnalité : ${agents.manager.persona}
${common}

Tes dernières revues :
${reviews}

Dernières analyses et opportunités des agents :
${Object.keys(state.agents).map((k) => `${agents.agents[k].name} : ${state.agents[k].analyse || "-"}\n  ${state.agents[k].opportunites.map(oppText).join("\n  ") || "aucune"}`).join("\n")}`;
  }
  const a = agents.agents[key], t = state.agents[key];
  const biens = t.biens.map((b) => `${b.titre} (${b.commune}) acheté ${money(b.cout_total)}, valeur ${money(b.valeur_actuelle ?? b.valeur_estimee)}, loyer ${money(b.loyer_retenu)}/mois`).join("\n") || "aucun";
  return `Tu es ${a.name}, ${a.role}. Ta personnalité : ${a.persona}
Ton secteur : ${a.zone}. Ta stratégie : ${a.strategie}.
${common}

Tes biens :
${biens}
Tes dernières opportunités :
${t.opportunites.map(oppText).join("\n") || "aucune"}
Ta dernière analyse : ${t.analyse || "-"}
Ta note personnelle : ${t.notes || "-"}
Dernier message de ${agents.manager.name} (ta directrice) : ${t.feedback || "-"}`;
}

let current = null;

function agentMeta(key) { return key === "manager" ? agents.manager : agents.agents[key]; }

function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  $("chat-log").appendChild(div);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return div;
}

function openChat(key) {
  current = key;
  const a = agentMeta(key);
  $("chat-avatar").textContent = a.emoji;
  $("chat-avatar").style.setProperty("--c", COLORS[key]);
  $("chat-name").textContent = a.name;
  $("chat-role").textContent = a.role;
  $("chat-log").innerHTML = "";
  histories[key] ??= [];
  if (!histories[key].length) addMsg("agent", `Bonjour, je suis ${a.name}. Que veux-tu savoir ?`);
  for (const m of histories[key]) addMsg(m.role === "user" ? "user" : "agent", m.content);
  $("chat").classList.remove("hidden");
  $("chat-input").focus();
}

function getKey() { try { return localStorage.getItem(KEY_STORAGE) || ""; } catch { return ""; } }
function setKey(v) { try { v ? localStorage.setItem(KEY_STORAGE, v) : localStorage.removeItem(KEY_STORAGE); } catch {} }

let Anthropic = null;
async function client() {
  if (!Anthropic) Anthropic = (await import("https://esm.sh/@anthropic-ai/sdk")).default;
  // La clé appartient à l'utilisateur et reste dans son navigateur.
  return new Anthropic({ apiKey: getKey(), dangerouslyAllowBrowser: true });
}

async function sendWithSample(sample, key, history, out) {
  // Pas de rôle système avec « sample » : les consignes de l'agent ouvrent la conversation.
  const turns = history.map((m, i) => ({
    role: m.role,
    content: i === 0 ? `${systemPrompt(key)}\n\n---\nMessage d'Eliott, le propriétaire de l'enveloppe :\n${m.content}` : m.content,
  }));
  const res = await sample(turns, { cache: false, onText: ({ text }) => { out.textContent = text; $("chat-log").scrollTop = $("chat-log").scrollHeight; } });
  return res.text;
}

async function sendLocal(key, history) {
  const r = await fetch("api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ system: systemPrompt(key), messages: history }) });
  const out = await r.json();
  if (!r.ok) throw new Error(out.error || "le modèle local n'a pas répondu");
  return out.text;
}

async function send(text) {
  if (localInfo) {
    const key = current, history = histories[key];
    history.push({ role: "user", content: text });
    addMsg("user", text);
    const out = addMsg("agent", "…");
    $("chat-send").disabled = true;
    try {
      const reply = await sendLocal(key, history);
      out.textContent = reply;
      history.push({ role: "assistant", content: reply });
    } catch (e) {
      history.pop();
      out.remove();
      addMsg("error", `Erreur : ${e.message}`);
    } finally {
      $("chat-send").disabled = false;
    }
    return;
  }
  const sample = await getSample();
  if (sample) {
    const key = current, history = histories[key];
    history.push({ role: "user", content: text });
    addMsg("user", text);
    const out = addMsg("agent", "…");
    $("chat-send").disabled = true;
    try {
      const reply = await sendWithSample(sample, key, history, out);
      out.textContent = reply;
      history.push({ role: "assistant", content: reply });
    } catch (e) {
      history.pop();
      out.remove();
      addMsg("error", e?.code === "not_granted" ? "La discussion a besoin de ton accord : autorise-la dans les permissions de la page."
        : e?.code === "rate_limited" ? "Trop de messages d'un coup : réessaie dans un instant." : `Erreur : ${e?.message || e}`);
    } finally {
      $("chat-send").disabled = false;
    }
    return;
  }
  if (!getKey()) {
    addMsg("error", "La discussion sur ce site demande une clé API (bouton « Clé API »). Sans clé, pose ta question à l'agent directement dans ton projet Claude.");
    return;
  }
  const key = current;
  const history = histories[key];
  history.push({ role: "user", content: text });
  addMsg("user", text);
  const out = addMsg("agent", "…");
  $("chat-send").disabled = true;
  try {
    const c = await client();
    const stream = c.beta.messages.stream({
      model: CHAT_MODEL,
      max_tokens: 4000,
      system: systemPrompt(key),
      messages: history,
      output_config: { effort: "low" },
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
    });
    let acc = "";
    stream.on("text", (d) => { acc += d; out.textContent = acc; $("chat-log").scrollTop = $("chat-log").scrollHeight; });
    const msg = await stream.finalMessage();
    if (msg.stop_reason === "refusal") throw new Error("L'agent a refusé de répondre à cette question.");
    const reply = msg.content.filter((b) => b.type === "text").map((b) => b.text).join("") || acc;
    out.textContent = reply;
    history.push({ role: "assistant", content: reply });
  } catch (e) {
    history.pop();
    out.remove();
    const status = e?.status;
    addMsg("error", status === 401 ? "Clé API invalide : vérifie-la avec le bouton « Clé API »." : `Erreur : ${e?.message || e}`);
  } finally {
    $("chat-send").disabled = false;
  }
}

function wireUi() {
  $("chat-close").onclick = () => $("chat").classList.add("hidden");
  $("chat-form").onsubmit = (e) => {
    e.preventDefault();
    const v = $("chat-input").value.trim();
    if (!v) return;
    $("chat-input").value = "";
    send(v);
  };
  $("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("chat-form").requestSubmit(); }
  });
  $("key-btn").onclick = () => { $("key-input").value = getKey(); $("key-dialog").showModal(); };
  $("key-dialog").addEventListener("close", () => {
    const r = $("key-dialog").returnValue;
    if (r === "save") setKey($("key-input").value.trim());
    if (r === "clear") setKey("");
  });
}

// ---------- version locale (python local.py) ----------

let localInfo = null;

function renderLocalControls() {
  $("key-btn").classList.add("hidden");
  const btn = $("run-link");
  btn.classList.remove("hidden");
  btn.removeAttribute("href");
  btn.removeAttribute("target");
  btn.setAttribute("role", "button");
  btn.textContent = localInfo.running ? "Tour en cours…" : "Lancer un tour";
  btn.onclick = async () => {
    if (localInfo.running) return;
    const r = await fetch("api/tour", { method: "POST" });
    if (r.ok || r.status === 409) { localInfo.running = true; btn.textContent = "Tour en cours…"; waitForRound(); }
  };
  const tail = localInfo.error ? ` · ⚠ ${localInfo.error}` : ` · modèle local ${localInfo.model}${localInfo.heure ? ` · tour auto le ${localInfo.jour} à ${localInfo.heure}` : ""}`;
  $("subtitle").textContent += tail;
}

async function waitForRound() {
  while (true) {
    await new Promise((r) => setTimeout(r, 3000));
    try { localInfo = await fetch("api/info", { cache: "no-store" }).then((r) => r.json()); } catch { continue; }
    if (!localInfo.running) return load();
  }
}

async function main() {
  wireUi();
  try { localInfo = await fetch("api/info", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)); } catch { localInfo = null; }
  if (localInfo?.running) waitForRound();
  load();
}

async function load() {
  try {
    if (embedded) {
      ({ agents, state, journal } = JSON.parse(embedded.textContent));
    } else {
    [agents, state] = await Promise.all(["data/agents.json", "data/state.json"].map((u) => fetch(u, { cache: "no-store" }).then((r) => {
      if (!r.ok) throw new Error(`${u} introuvable`);
      return r.json();
    })));
    journal = await fetch("data/journal.md", { cache: "no-store" }).then((r) => (r.ok ? r.text() : "")).catch(() => "");
    }
  } catch (e) {
    $("subtitle").textContent = localInfo
      ? "Aucun tour pour l'instant : clique sur « Lancer un tour » (quelques minutes avec un modèle local)."
      : "Aucune donnée pour l'instant : lance un premier tour depuis l'onglet Actions de GitHub.";
    if (localInfo) renderLocalControls();
    return;
  }
  renderHeader();
  const fund = renderKpis();
  renderBest();
  renderAgents();
  renderChart(fund);
  renderTabs();
}

main();
