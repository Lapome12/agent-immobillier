"""Rapport HTML autonome (sans JavaScript) : les 5 propositions de chaque agent avec les
corrections d'Hélène, le classement et ses bilans. L'interface complète est dans site/."""
import html
import json
from pathlib import Path

from . import config
from .config import display

COLORS = {"hyeres": "#d9781c", "grenoble": "#2a78d6", "station": "#23915a", "giens": "#0f8f9c", "renovation": "#8e4fb3"}
LIBELLES = {"chere": "La plus chère", "pas_chere": "La moins chère", "bon_plan": "Bon plan", "choix_agent": "Choix de l'agent"}
esc = lambda s: html.escape(str(s if s is not None else ""))
eur = lambda x: f"{x:,.0f} €".replace(",", " ")


def _rows(props):
    out = []
    for p in props:
        titre = esc(p.get("titre"))
        if str(p.get("url", "")).startswith("http"):
            titre = f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">{titre}</a>'
        m2 = (f"{eur(p['prix_m2'])}/m²<div class=muted>DVF {eur(p['mediane_m2'])}/m²"
              + (f" · Hélène {eur(p['prix_m2_constate'])}/m²" if p.get("prix_m2_constate") else "") + "</div>") if p.get("prix_m2") else "-"
        note = f"<b>{p['note']:.0f}/10</b><div class=muted>{esc(p.get('verdict'))}</div>" if p.get("note") is not None else "-"
        alerte = f"<div class=warn>⚠ {esc(p['motif'])}</div>" if p.get("motif") else ""
        avis = " ".join(x for x in (esc(p.get("avis_quartier")), esc(p.get("correction"))) if x)
        out.append(f"<tr><td>{LIBELLES.get(p.get('categorie'), '')}</td>"
                   f"<td>{titre}<div class=muted>{esc(p.get('commune'))} · {esc(p.get('quartier'))} · {p.get('surface_m2', 0):.0f} m² · DPE {esc(p.get('dpe'))}</div>{alerte}</td>"
                   f"<td>{eur(p.get('prix', 0))}</td><td>{m2}</td><td>{note}</td><td class=small>{avis or '-'}</td></tr>")
    return "".join(out)


def build(state_dir, local=False):
    state_dir = Path(state_dir)
    state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    agents = state["agents"]
    moy = {k: (sum(a["notes_tours"]) / len(a["notes_tours"]) if a["notes_tours"] else 0) for k, a in agents.items()}
    rank = sorted(agents, key=lambda k: moy[k], reverse=True)
    classement = "".join(f"<tr><td>{i}</td><td><span class=dot style='background:{COLORS[k]}'></span>{esc(display(k))}</td>"
                         f"<td>{moy[k]:.1f}/10</td><td>{(agents[k]['notes_tours'] or ['-'])[-1]}</td></tr>"
                         for i, k in enumerate(rank, 1))
    head = "<tr><th>Catégorie</th><th>Annonce</th><th>Prix</th><th>Prix au m²</th><th>Note d'Hélène</th><th>Avis et correction</th></tr>"
    cards = "".join(
        f"<div class=card><h3><span class=dot style='background:{COLORS[k]}'></span>{config.AGENTS[k]['emoji']} {esc(display(k))}</h3>"
        f"<p>{esc(agents[k]['analyse'] or '-')}</p><div class=wrap><table>{head}{_rows(agents[k]['propositions'])}</table></div>"
        f"<p class=muted>Retour d'{esc(config.MANAGER['name'])} : {esc(agents[k]['feedback'] or '-')}</p></div>" for k in rank)
    reviews = "".join(
        f"<details{' open' if i == 0 else ''}><summary>Semaine {r['round']} · {esc(r['date'])}</summary><p>{esc(r['commentary'])}</p>"
        f"<p><b>Coup de cœur :</b> {esc(r.get('coup_de_coeur'))}</p></details>" for i, r in enumerate(reversed(state["reviews"])))
    bouton = ('<p><button id=tour>Lancer un tour</button> <span id=etat class=muted></span></p><script>'
              'const b=document.getElementById("tour"),e=document.getElementById("etat");'
              'b.onclick=async()=>{const r=await fetch("/api/tour",{method:"POST"});'
              'e.textContent=r.ok?"Tour lancé, recharge la page dans quelques minutes.":(await r.json()).error;};</script>') if local else ""
    page = f"""<!doctype html><html lang=fr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Agents immobiliers</title>
<style>
:root{{--bg:#fafaf8;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2e2dc;--card:#fff;--link:#1f5fae;--warn:#b5521b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--fg:#ececea;--muted:#9a9a94;--line:#2e2e2b;--card:#1f1f1d;--link:#7fb0ef;--warn:#f0955c}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:1000px;margin:auto}} h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:28px 0 8px}}
h3{{font-size:15px;margin:0 0 4px}} .muted{{color:var(--muted);font-size:13px}} .small{{font-size:13px}} a{{color:var(--link)}} .warn{{color:var(--warn);font-size:13px}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}} td,th{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin:10px 0}}
details{{border-bottom:1px solid var(--line);padding:8px 0}} .wrap{{overflow-x:auto}} button{{font:inherit;padding:6px 12px}}
</style></head><body><main>
<h1>{config.MANAGER['emoji']} Agents immobiliers IA</h1><p class=muted>Recherche d'investissements · budget max {eur(config.BUDGET_MAX)} par bien · semaine {state['round']} · {esc(state['dates'][-1] if state['dates'] else '')}</p>
{bouton}
<h2>Classement (note moyenne d'{esc(config.MANAGER['name'])})</h2><div class=wrap><table><tr><th>#</th><th>Agent</th><th>Moyenne</th><th>Dernière semaine</th></tr>{classement}</table></div>
<h2>Les propositions de la semaine</h2>{cards}
<h2>Bilans d'{esc(config.MANAGER['name'])}, la directrice d'investissement</h2>{reviews or '<p class=muted>Aucune revue pour le moment.</p>'}
</main></body></html>"""
    out = state_dir / "rapport.html"
    out.write_text(page, encoding="utf-8")
    return out
