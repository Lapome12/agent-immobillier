// Agents immobiliers : tableau de bord + discussion avec les agents.
// Les données viennent de data/*.json, publiées par le workflow GitHub après chaque tour.

const KEY_STORAGE = "immo-anthropic-key";
const CHAT_MODEL = "claude-opus-5-5";
const COLORS = { hyeres: "var(--hyeres)", grenoble: "var(--grenoble)", station: "var(--station)", renovation: "var(--renovation)", manager: "var(--manager)" };
const LIBELLES = { chere: "La plus chère", pas_chere: "La moins chère", bon_plan: "Bon plan", choix_agent: "Choix de l'agent" };
const VERDICTS = { "validée": "good", "à revoir": "warn", "rejetée": "bad" };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const pct = (x, d = 0) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)} %`;
const money = (x) => `${Math.round(x).toLocaleString("fr-FR")} €`;
const avg = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

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

function ranking() {
  return Object.keys(state.agents).sort((a, b) => (avg(state.agents[b].notes_tours) ?? -1) - (avg(state.agents[a].notes_tours) ?? -1));
}

function link(o) {
  const t = esc(o.titre);
  return /^https?:/.test(o.url || "") ? `<a href="${esc(o.url)}" target="_blank" rel="noopener">${t}</a>` : t;
}

// ---------- rendu ----------

function renderHeader() {
  const date = state.dates.at(-1) || "";
  $("subtitle").textContent = `Semaine ${state.round} · dernier tour ${date} · budget max ${money(agents.budget_max || 150000)} par bien`;
  const m = location.hostname.match(/^([^.]+)\.github\.io$/);
  const repo = location.pathname.split("/").filter(Boolean)[0];
  if (embedded) $("key-btn").classList.add("hidden");
  if (localInfo) return renderLocalControls();
  if (m && repo) $("run-link").href = `https://github.com/${m[1]}/${repo}/actions/workflows/immobilier.yml`;
  else $("run-link").classList.add("hidden");
}

function renderKpis() {
  const props = Object.values(state.agents).flatMap((a) => a.propositions);
  const notes = props.map((p) => p.note).filter((n) => n != null);
  const leader = agents.agents[ranking()[0]];
  const hasNotes = Object.values(state.agents).some((a) => a.notes_tours.length);
  $("kpis").innerHTML = [
    ["Propositions de la semaine", props.length],
    ["Validées par " + esc(agents.manager.name), props.filter((p) => p.verdict === "validée").length],
    ["Note moyenne de l'équipe", notes.length ? `${avg(notes).toFixed(1)}/10` : "-"],
    ["En tête", hasNotes ? `${leader.emoji} ${esc(leader.name)}` : "-"],
  ].map(([l, v]) => `<div class="kpi"><span class="muted small">${l}</span><b>${v}</b></div>`).join("");
}

function renderCoupDeCoeur() {
  const r = state.reviews.at(-1);
  $("coup").innerHTML = r ? `<div class="review"><b>${agents.manager.emoji} Coup de cœur d'${esc(agents.manager.name)}</b>
    <p>${esc(r.coup_de_coeur)}</p><p class="muted small">${esc(r.commentary)}</p></div>` : "";
}

function propRow(p) {
  const verdict = p.verdict ? `<span class="chip ${VERDICTS[p.verdict] || ""}">${esc(p.verdict)}</span>` : "";
  const note = p.note != null ? `<b class="score">${Math.round(p.note)}/10</b>${verdict}` : `<span class="muted small">pas encore notée</span>`;
  const m2 = p.prix_m2 ? `${money(p.prix_m2)}/m²<span class="muted small">ventes DVF ${money(p.mediane_m2)}/m²${p.prix_m2_constate ? `<br>selon ${esc(agents.manager.name)} ${money(p.prix_m2_constate)}/m²` : ""}</span>` : "-";
  const avis = [p.avis_quartier, p.correction].filter(Boolean).map(esc).join(" ");
  return `<tr>
    <td><span class="cat cat-${esc(p.categorie)}">${LIBELLES[p.categorie] || esc(p.categorie)}</span></td>
    <td>${link(p)}<span class="muted small">${esc(p.commune)}${p.quartier ? " · " + esc(p.quartier) : ""} · ${Math.round(p.surface_m2 || 0)} m² · DPE ${esc(p.dpe)}</span>
      ${p.pourquoi ? `<span class="small">${esc(p.pourquoi)}</span>` : ""}${p.motif ? `<span class="small down">⚠ ${esc(p.motif)}</span>` : ""}</td>
    <td class="num">${money(p.prix || 0)}${p.travaux_estimes ? `<span class="muted small">+ travaux ${money(p.travaux_estimes)}</span>` : ""}</td>
    <td class="num">${m2}</td>
    <td class="num">${p.rendement_net != null ? (p.rendement_net * 100).toFixed(1) + " %" : "-"}${p.loyer_retenu ? `<span class="muted small">${money(p.loyer_retenu)}/mois</span>` : ""}</td>
    <td>${note}</td>
    <td class="small">${avis || "-"}</td></tr>`;
}

function renderPropositions() {
  $("propositions").innerHTML = ranking().map((k) => {
    const a = agents.agents[k], t = state.agents[k];
    const rows = t.propositions.map(propRow).join("");
    return `<div class="block" style="--c:${COLORS[k]}">
      <div class="block-head"><div class="avatar">${a.emoji}</div><div><b>${esc(a.name)}</b><div class="muted small">${esc(a.zone)}</div></div></div>
      ${rows ? `<div class="table-wrap"><table><tr><th>Catégorie</th><th>Annonce</th><th>Prix</th><th>Prix au m²</th><th>Rendement net</th><th>Note</th><th>Avis et correction d'${esc(agents.manager.name)}</th></tr>${rows}</table></div>`
        : `<p class="muted">Aucune proposition cette semaine.</p>`}
      ${t.feedback ? `<p class="small"><b>Retour d'${esc(agents.manager.name)} :</b> ${esc(t.feedback)}</p>` : ""}
    </div>`;
  }).join("");
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
      <p class="quote">${lastReview ? "« " + esc(lastReview.commentary) + " »" : "Pas encore de revue."}</p>
    </button>`;
  const cards = order.map((k, i) => {
    const a = agents.agents[k], t = state.agents[k];
    const m = avg(t.notes_tours);
    return `
      <button class="agent" style="--c:${COLORS[k]}" data-agent="${k}">
        <div class="agent-top"><div class="avatar">${a.emoji}</div>
          <div><b>${esc(a.name)}</b><div class="muted small">${esc(a.role)}</div></div>
          <span class="rank">#${i + 1}</span></div>
        <div class="stats">
          <div><span>Note moyenne</span>${m != null ? m.toFixed(1) + "/10" : "-"}</div>
          <div><span>Cette semaine</span>${t.notes_tours.length ? t.notes_tours.at(-1).toFixed(1) + "/10" : "-"}</div>
          <div><span>Validées</span>${t.propositions.filter((p) => p.verdict === "validée").length}/${t.propositions.length}</div>
        </div>
        <p class="quote">${esc(t.analyse || a.persona)}</p>
      </button>`;
  }).join("");
  $("agents").innerHTML = manager + cards;
  document.querySelectorAll(".agent").forEach((el) => el.addEventListener("click", () => openChat(el.dataset.agent)));
}

function renderChart() {
  const series = Object.fromEntries(Object.keys(state.agents).map((k) => [k, state.agents[k].notes_tours]));
  const n = Math.max(...Object.values(series).map((s) => s.length));
  $("legend").innerHTML = Object.keys(series).map((k) =>
    `<span><span class="dot" style="background:${COLORS[k]}"></span>${esc(agents.agents[k].name)}</span>`).join("");
  if (n < 2) { $("chart").innerHTML = `<p class="muted">Les courbes des notes apparaîtront après la deuxième semaine.</p>`; return; }
  const W = 1000, H = 300, L = 50, P = 20, lo = 0, hi = 10;
  const x = (i) => L + (i * (W - L - P)) / (n - 1), y = (v) => H - P - ((v - lo) * (H - 2 * P)) / (hi - lo);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Note moyenne par semaine">`;
  for (const v of [0, 2.5, 5, 7.5, 10]) svg += `<line class="grid" x1="${L}" x2="${W - P}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
  for (const [k, s] of Object.entries(series)) {
    if (!s.length) continue;
    const pts = s.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    svg += `<polyline points="${pts}" fill="none" stroke="${COLORS[k]}" stroke-width="2.2"/>`;
    svg += `<circle cx="${x(s.length - 1)}" cy="${y(s.at(-1))}" r="4" fill="${COLORS[k]}"/>`;
  }
  $("chart").innerHTML = svg + "</svg>";
}

function renderTabs() {
  $("tab-reviews").innerHTML = state.reviews.length ? [...state.reviews].reverse().map((r) => `
    <div class="review"><b>Semaine ${r.round}</b> <span class="muted small">· ${esc(r.date)}</span>
      <p>${esc(r.commentary)}</p>
      ${r.coup_de_coeur ? `<p><b>Coup de cœur :</b> ${esc(r.coup_de_coeur)}</p>` : ""}
      <div class="pos">${Object.entries(r.notes || {}).map(([k, n]) => `<span class="chip">${agents.agents[k].emoji} ${esc(agents.agents[k].name)} ${n.toFixed(1)}/10</span>`).join("")}</div>
    </div>`).join("") : `<p class="muted">Pas encore de revue.</p>`;
  $("tab-journal").innerHTML = `<div class="journal">${esc(journal.split("\n## ").slice(-15).reverse().map((b, i) => (i < 14 ? "## " : "") + b).join("\n\n")) || "Journal vide."}</div>`;
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${b.dataset.tab}`));
  }));
}

// ---------- discussion ----------

function leaderboardText() {
  return ranking().map((k, i) => {
    const a = agents.agents[k], t = state.agents[k], m = avg(t.notes_tours);
    return `${i + 1}. ${a.name} (${a.role}) : note moyenne ${m != null ? m.toFixed(1) : "-"}/10`;
  }).join("\n");
}

function propText(p, i) {
  return `${i}. [${LIBELLES[p.categorie] || p.categorie}] ${p.titre} (${p.commune}, ${p.quartier || "-"}, ${Math.round(p.surface_m2 || 0)} m², ${money(p.prix || 0)}, ${p.prix_m2 ? money(p.prix_m2) + "/m² contre " + money(p.mediane_m2) + "/m² en DVF" : ""}) ${p.url}`
    + (p.note != null ? ` · note d'Hélène ${p.note}/10, ${p.verdict} : ${p.avis_quartier || ""} ${p.correction || ""}` : "");
}

function systemPrompt(key) {
  const common = `Nous sommes dans une équipe de 4 agents de recherche immobilière IA en compétition, chacun sur un secteur (Hyères, Grenoble, stations de ski, biens à rénover), et une directrice d'investissement IA qui vérifie et note leurs propositions. Les agents n'achètent rien : chacun propose chaque semaine 5 biens en vente (la plus chère, la moins chère, un bon plan, 2 à son choix), avec un budget max de ${money(agents.budget_max || 150000)} par bien, dans un but d'investissement pour Eliott.
Semaine actuelle : ${state.round}, dernier tour : ${state.dates.at(-1) || "aucun"}.
Classement :
${leaderboardText()}

Tu discutes maintenant avec Eliott. Réponds en français, dans ton personnage, de façon concise et concrète, en t'appuyant sur les données ci-dessous. Rappelle si besoin qu'avant une offre il faut visiter le bien et vérifier les diagnostics et les documents de copropriété.`;
  if (key === "manager") {
    const reviews = state.reviews.slice(-5).map((r) => `Semaine ${r.round} (${r.date}) : ${r.commentary} Coup de cœur : ${r.coup_de_coeur || "-"}`).join("\n") || "aucune";
    return `Tu es ${agents.manager.name}, ${agents.manager.role} de l'équipe. Ta personnalité : ${agents.manager.persona}
${common}

Tes dernières revues :
${reviews}

Propositions de la semaine et tes corrections :
${Object.keys(state.agents).map((k) => `${agents.agents[k].name} : ${state.agents[k].analyse || "-"}\n  ${state.agents[k].propositions.map(propText).join("\n  ") || "aucune"}`).join("\n")}`;
  }
  const a = agents.agents[key], t = state.agents[key];
  return `Tu es ${a.name}, ${a.role}. Ta personnalité : ${a.persona}
Ton secteur : ${a.zone}. Ta stratégie : ${a.strategie}.
${common}

Tes propositions de la semaine (avec les corrections d'Hélène) :
${t.propositions.map(propText).join("\n") || "aucune"}
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
    content: i === 0 ? `${systemPrompt(key)}\n\n---\nMessage d'Eliott :\n${m.content}` : m.content,
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
  renderKpis();
  renderCoupDeCoeur();
  renderPropositions();
  renderAgents();
  renderChart();
  renderTabs();
}

main();
