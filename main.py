"""Point d'entrée : python main.py {sim,live,report,export,artifact} [options]"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from immo import config
from immo.brains import make_brain
from immo.engine import Fonds
from immo.marche import MarcheDVF, MarcheSimule
from immo.report import build


def agents_json():
    return {"manager": config.MANAGER, "agents": config.AGENTS, "model": config.MODEL, "manager_every": config.MANAGER_EVERY,
            "budget_max": config.BUDGET_MAX, "categories": config.CATEGORIES}


def export_site(state_dir, out):
    """Copie le site web et y ajoute les données de la partie (state.json, journal, agents)."""
    out, src = Path(out), Path(state_dir)
    shutil.copytree(Path(__file__).parent / "site", out, dirs_exist_ok=True)
    data = out / "data"
    data.mkdir(exist_ok=True)
    (data / "agents.json").write_text(json.dumps(agents_json(), ensure_ascii=False, indent=1), encoding="utf-8")
    for name in ("state.json", "journal.md"):
        if (src / name).exists():
            shutil.copy(src / name, data / name)
    if (src / "state.json").exists():
        shutil.copy(build(src), out / "rapport.html")
    return out


def build_artifact(state_dir, out):
    """Une seule page HTML autonome (pour un Artifact claude.ai) : site + données intégrées."""
    src, site = Path(state_dir), Path(__file__).parent / "site"
    data = {
        "agents": agents_json(),
        "state": json.loads((src / "state.json").read_text(encoding="utf-8")),
        "journal": (src / "journal.md").read_text(encoding="utf-8") if (src / "journal.md").exists() else "",
    }
    page = (site / "index.html").read_text(encoding="utf-8")
    head, body = page.split("<body>", 1)
    body = body.split("</body>", 1)[0]
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    fonts = "".join(line + "\n" for line in head.splitlines() if "fonts.g" in line)
    html = (f"<title>Agents immobiliers</title>\n{fonts}<style>\n{(site / 'style.css').read_text(encoding='utf-8')}</style>\n"
            + body.replace('<script type="module" src="app.js"></script>', "")
            + f'<script type="application/json" id="immo-data">{payload}</script>\n'
            + f'<script type="module">\n{(site / "app.js").read_text(encoding="utf-8")}</script>\n')
    Path(out).write_text(html, encoding="utf-8")
    return out


def main():
    p = argparse.ArgumentParser(description="4 agents de recherche immobilière IA en compétition + 1 directrice d'investissement.")
    p.add_argument("mode", choices=["sim", "live", "report", "export", "artifact"],
                   help="sim : marché et annonces simulés · live : un tour sur les vrais prix DVF et de vraies annonces "
                        "(à lancer chaque semaine) · report : régénère le rapport · export : prépare le site (dossier --out) · "
                        "artifact : une page unique à publier sur claude.ai")
    p.add_argument("--rounds", type=int, default=20, help="nombre de semaines (sim)")
    p.add_argument("--mock", action="store_true", help="stratégie simple à la place de Claude (gratuit, pour tester)")
    p.add_argument("--brain", choices=["auto", "api", "abonnement", "local"], default="auto",
                   help="api : clé ANTHROPIC_API_KEY · abonnement : ton abonnement Claude via Claude Code · "
                        "local : modèle Ollama sur ton ordinateur · auto (défaut) : la clé si elle existe, sinon l'abonnement")
    p.add_argument("--state-dir", help="dossier de sauvegarde (par défaut runs/<mode>)")
    p.add_argument("--out", default="_site", help="dossier de sortie du site (export)")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    state_dir = a.state_dir or f"runs/{a.mode if a.mode in ('sim', 'live') else 'live'}"

    if a.mode == "report":
        print(build(state_dir))
        return
    if a.mode == "artifact":
        print(build_artifact(state_dir, a.out if a.out != "_site" else "agents-immobiliers.html"))
        return
    if a.mode == "export":
        print(export_site(state_dir, a.out))
        return

    brain = make_brain("mock" if a.mock else {"abonnement": "code"}.get(a.brain, a.brain))
    if a.mode == "sim":
        marche = MarcheSimule(seed=a.seed)
    else:
        marche = MarcheDVF()

    fonds = Fonds(brain, marche, state_dir)
    if a.mode == "live":
        fonds.step()
        if fonds.failures == len(config.AGENTS):
            # Aucun agent n'a pu répondre (souvent un jeton invalide) : on échoue pour que
            # le workflow passe au rouge et ne sauvegarde pas un tour vide.
            print("\n".join(fonds.errors), file=sys.stderr)
            sys.exit("Tous les agents ont échoué")
    else:
        if fonds.state["round"]:
            sys.exit(f"{state_dir} contient déjà une partie : supprime-le ou choisis --state-dir.")
        for i in range(a.rounds):
            fonds.step()
            print(f"Semaine {i + 1}/{a.rounds} ({marche.label()})")
            marche.advance()

    print("\nClassement :\n" + fonds.leaderboard_text())
    print(f"\nRapport : {build(state_dir)}\nJournal : {fonds.journal_file}")


if __name__ == "__main__":
    main()
