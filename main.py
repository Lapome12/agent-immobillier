"""Point d'entrée : python main.py {sim,live,report,export} [options]"""
import argparse
import shutil
import sys
from pathlib import Path

from immo import config
from immo.brains import make_brain
from immo.engine import Fonds
from immo.marche import MarcheDVF, MarcheSimule
from immo.report import build


def main():
    p = argparse.ArgumentParser(description="4 agents immobiliers IA en compétition + 1 directrice d'investissement (argent fictif).")
    p.add_argument("mode", choices=["sim", "live", "report", "export"],
                   help="sim : marché et annonces simulés · live : un tour sur les vrais prix DVF et de vraies annonces "
                        "(à lancer chaque semaine) · report : régénère le rapport · export : prépare le site (dossier --out)")
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
    if a.mode == "export":
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        if not (Path(state_dir) / "state.json").exists():  # aucun tour joué pour le moment
            (out / "index.html").write_text("<!doctype html><meta charset=utf-8><title>Agents immobiliers</title>"
                                            "<p style='font:16px system-ui;padding:24px'>Aucun tour joué pour le moment.</p>",
                                            encoding="utf-8")
        else:
            shutil.copy(build(state_dir), out / "index.html")
        print(out / "index.html")
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
            print(f"Semaine {i + 1}/{a.rounds} ({marche.label()}) · enveloppe {fonds.total_equity():,.0f} €".replace(",", " "))
            marche.advance()
        fonds.encaisser_loyers()
        fonds.mark()
        fonds.save()

    print("\nClassement :\n" + fonds.leaderboard_text())
    print(f"\nRapport : {build(state_dir)}\nJournal : {fonds.journal_file}")


if __name__ == "__main__":
    main()
