"""Rapport HTML autonome : meilleures opportunités, classement, courbes, portefeuilles,
décisions de la directrice d'investissement."""
import html
import json
from pathlib import Path

from . import config
from .config import display
from .engine import metrics

COLORS = {"hyeres": "#e8892b", "grenoble": "#2a78d6", "station": "#2f9e62", "renovation": "#9b59b6"}
esc = lambda s: html.escape(str(s if s is not None else ""))
eur = lambda x: f"{x:,.0f}\u00a0€".replace(",", "\u202f")


def _chart(series, width=760, height=280, pad=56):
    allv = [v for s in series.values() for v in s]
    if not allv or max(len(s) for s in series.values()) < 2:
        return "<p class=muted>Pas encore assez de semaines pour tracer les courbes.</p>"
    lo, hi = min(allv), max(allv)
    hi = hi if hi > lo else lo + 1e-9
    n = max(len(s) for s in series.values())
    x = lambda i: pad + i * (width - 2 * pad) / (n - 1)
    y = lambda v: height - pad - (v - lo) * (height - 2 * pad) / (hi - lo)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Performance des agents">']
    for frac in (0, 0.5, 1):
        v = lo + frac * (hi - lo)
        parts.append(f'<line x1="{pad}" x2="{width-pad}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                     f'<text x="{pad-6}" y="{y(v)+4:.1f}" text-anchor="end">{(v-1):+.1%}</text>')
    for k, s in series.items():
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(s))
        dash = ' stroke-dasharray="5 4"' if k == "fonds" else ""
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{COLORS.get(k, "currentColor")}" stroke-width="2"{dash}/>')
    parts.append("</svg>")
    return "".join(parts)


def _opp_rows(opps, with_agent=False):
    rows = []
    for k, o in opps:
        titre = esc(o.get("titre"))
        if str(o.get("url", "")).startswith("http"):
            titre = f'<a href="{esc(o["url"])}" target="_blank" rel="noopener">{titre}</a>'
        agent = f"<td><span class=dot style='background:{COLORS[k]}'></span>{esc(config.AGENTS[k]['name'])}</td>" if with_agent else ""
        if not o.get("valide"):
            rows.append(f"<tr class=muted>{agent}<td>{titre}</td><td colspan=6>Écartée : {esc(o.get('motif'))}</td></tr>")
            continue
        plaf = " *" if o.get("loyer_plafonne") else ""
        rows.append(
            f"<tr>{agent}<td>{titre}<div class=muted>{esc(o.get('commune'))} · {o['surface_m2']:.0f} m² · DPE {esc(o.get('dpe'))}</div></td>"
            f"<td>{eur(o['prix'])}<div class=muted>+ travaux {eur(o['travaux_estimes'])}</div></td>"
            f"<td>{eur(o['prix_m2'])}/m²<div class=muted>marché {eur(o['mediane_m2'])}/m²</div></td>"
            f"<td>{o['marge']:+.0%}</td><td>{o['rendement_net']:.1%}{plaf}</td><td><b>{o['score']}</b></td></tr>")
    return "".join(rows)


def build(state_dir, local=False):
    state_dir = Path(state_dir)
    state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    agents = state["agents"]
    curves = {k: a["nav"] for k, a in agents.items()}
    n = min(len(a["curve"]) for a in agents.values())
    fund = [sum(a["curve"][i] for a in agents.values()) for i in range(n)]
    curves["fonds"] = [v / fund[0] for v in fund] if fund else []
    fm = metrics(curves["fonds"])

    head = "<tr><th>Annonce</th><th>Prix</th><th>Prix au m²</th><th>Marge</th><th>Rendement net</th><th>Score</th></tr>"
    toutes = [(k, o) for k, a in agents.items() for o in a["opportunites"]]
    best = sorted([x for x in toutes if x[1].get("valide")], key=lambda x: x[1]["score"], reverse=True)[:8]

    rows = []
    ranked = sorted(agents, key=lambda k: agents[k]["nav"][-1] if agents[k]["nav"] else 1, reverse=True)
    for i, k in enumerate(ranked, 1):
        a = agents[k]
        m = metrics(a["nav"])
        rows.append(f"<tr><td>{i}</td><td><span class=dot style='background:{COLORS[k]}'></span>{esc(display(k))}</td>"
                    f"<td>{eur(a['curve'][-1] if a['curve'] else 0)}</td><td>{a['budget']:.0%}</td>"
                    f"<td>{m['rendement_total']:+.2%}</td><td>{len(a['biens'])}</td><td>{eur(a['cash'])}</td>"
                    f"<td>{eur(a['loyers_cumules'])}</td></tr>")

    cards = []
    for k, a in agents.items():
        biens = "".join(
            f"<li>{esc(b['titre'])} ({esc(b.get('commune'))}) : payé {eur(b['cout_total'])}, "
            f"valeur {eur(b.get('valeur_actuelle', b['valeur_estimee']))}, loyer {eur(b['loyer_retenu'])}/mois"
            f" <span class=muted>· acheté {esc(b['achat_date'])}</span></li>" for b in a["biens"]) or "<li class=muted>Aucun bien pour le moment</li>"
        opps = _opp_rows([(k, o) for o in a["opportunites"]])
        cards.append(
            f"<div class=card><h3><span class=dot style='background:{COLORS[k]}'></span>{config.AGENTS[k]['emoji']} {esc(display(k))}</h3>"
            f"<p class=muted>{esc(config.AGENTS[k]['zone'])}</p><p>{esc(a['analyse'] or '-')}</p>"
            + (f"<div class=wrap><table>{head}{opps}</table></div>" if opps else "")
            + f"<p><b>Portefeuille</b></p><ul>{biens}</ul>"
            f"<p class=muted>Retour de {esc(config.MANAGER['name'])} : {esc(a['feedback'] or '-')}</p></div>")

    reviews = "".join(
        f"<details><summary>Tour {r['round']} · {esc(r['date'])}</summary><p>{esc(r['commentary'])}</p>"
        f"<p><b>Coup de cœur :</b> {esc(r.get('coup_de_coeur'))}</p><p class=muted>"
        + ", ".join(f"{esc(display(k))} {w:.0%}" for k, w in r["budgets"].items())
        + "</p></details>" for r in reversed(state["reviews"]))
    legend = " ".join(f"<span><span class=dot style='background:{COLORS.get(k, 'currentColor')}'></span>"
                      f"{esc(display(k) if k in config.AGENTS else 'Enveloppe totale (pointillés)')}</span>" for k in curves)
    total = fund[-1] if fund else config.INITIAL_CAPITAL
    nb_biens = sum(len(a["biens"]) for a in agents.values())
    bouton = ('<p><button id=tour>Lancer un tour</button> <span id=etat class=muted></span></p><script>'
              'const b=document.getElementById("tour"),e=document.getElementById("etat");'
              'b.onclick=async()=>{const r=await fetch("/api/tour",{method:"POST"});'
              'e.textContent=r.ok?"Tour lancé, recharge la page dans quelques minutes.":(await r.json()).error;};</script>') if local else ""
    page = f"""<!doctype html><html lang=fr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Agents immobiliers</title>
<style>
:root{{--bg:#fafaf8;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2e2dc;--card:#fff;--link:#1f5fae}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--fg:#ececea;--muted:#9a9a94;--line:#2e2e2b;--card:#1f1f1d;--link:#7fb0ef}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:900px;margin:auto}} h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:28px 0 8px}}
h3{{font-size:15px;margin:0 0 4px}} .muted{{color:var(--muted)}} a{{color:var(--link)}} .muted td,div.muted{{font-size:13px}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}} td,th{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}}
.kpis{{display:flex;gap:24px;flex-wrap:wrap;margin:16px 0}} .kpis b{{display:block;font-size:20px}}
svg{{width:100%;height:auto}} svg text{{fill:var(--muted);font-size:11px}} .grid{{stroke:var(--line)}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;font-size:13px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin:10px 0}}
details{{border-bottom:1px solid var(--line);padding:8px 0}} .wrap{{overflow-x:auto}} button{{font:inherit;padding:6px 12px}}
</style></head><body><main>
<h1>{config.MANAGER['emoji']} Agents immobiliers IA</h1><p class=muted>Investissement fictif · tour {state['round']} · {esc(state['dates'][-1] if state['dates'] else '')}</p>
{bouton}
<div class=kpis><div>Valeur de l'enveloppe<b>{eur(total)}</b></div><div>Rendement<b>{fm['rendement_total']:+.2%}</b></div>
<div>Biens achetés<b>{nb_biens}</b></div><div>Revues de {esc(config.MANAGER['name'])}<b>{len(state['reviews'])}</b></div></div>
<h2>Meilleures opportunités du moment</h2>
<p class=muted>Marge = valeur au prix médian du secteur (DVF, moins 5 % de frais de revente) rapportée au coût total (prix + 8 % de notaire + travaux).
Rendement net = loyer retenu × 12 × 75 % / coût total. * loyer annoncé plafonné par le code. Vérifie toujours l'annonce avant de te déplacer.</p>
<div class=wrap><table><tr><th>Agent</th>{head[4:]}{_opp_rows(best, True) or '<tr><td colspan=7 class=muted>Aucune pour le moment</td></tr>'}</table></div>
<h2>Classement</h2><div class=wrap><table><tr><th>#</th><th>Agent</th><th>Valeur</th><th>Part</th><th>Rendement</th><th>Biens</th><th>Trésorerie</th><th>Loyers nets</th></tr>{''.join(rows)}</table></div>
<h2>Performance (base 0 %)</h2><div class=legend>{legend}</div>{_chart(curves)}
<h2>Les agents</h2>{''.join(cards)}
<h2>Décisions de {esc(config.MANAGER['name'])}, la directrice d'investissement</h2>{reviews or '<p class=muted>Aucune revue pour le moment.</p>'}
</main></body></html>"""
    out = state_dir / "rapport.html"
    out.write_text(page, encoding="utf-8")
    return out
