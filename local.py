"""Agents immobiliers, version 100 % locale.

Hélène (la directrice d'investissement) et les 5 agents tournent avec un modèle Ollama installé
sur ton ordinateur. Sans accès au web, les agents travaillent sur les annonces que tu déposes
dans annonces/<agent>/ (copier-coller du texte de l'annonce + son lien). Ce script :
  - joue automatiquement un tour chaque semaine, le jour et à l'heure choisis (lundi 8h par défaut),
    et rattrape le tour si l'ordinateur était éteint à ce moment-là ;
  - sert le tableau de bord sur http://localhost:8001, avec un bouton « Lancer un tour »
    et la discussion avec chaque agent (sans clé API, via Ollama).

Usage : python local.py [--jour lundi] [--heure 08:00] [--modele qwen3:8b] [--port 8001] [--marche simule]
"""
import argparse
import json
import mimetypes
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from immo import config
from immo.brains import OllamaBrain
from immo.engine import Fonds
from immo.report import build

ROOT = Path(__file__).parent
SITE = ROOT / "site"
STATE_DIR = ROOT / "runs" / "local"
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


class Arene:
    """Joue les tours (un seul à la fois) et garde la trace de ce qui se passe."""

    def __init__(self, brain, jour, heure, simulated=False):
        self.brain, self.jour, self.heure, self.simulated = brain, jour, heure, simulated
        self.lock = threading.Lock()
        self.running, self.last_error = False, ""
        self.last_run_file = STATE_DIR / "dernier_tour.txt"

    def last_run_week(self):
        try:
            return self.last_run_file.read_text().strip()
        except OSError:
            return ""

    def play_round(self):
        if not self.lock.acquire(blocking=False):
            return False
        self.running, self.last_error = True, ""
        try:
            from immo.marche import MarcheDVF, MarcheSimule

            print(f"[{datetime.now():%H:%M}] Tour en cours avec {self.brain.model}…")
            if self.simulated:  # marché fictif, qui avance d'une semaine à chaque tour
                f = STATE_DIR / "state.json"
                rounds = json.loads(f.read_text(encoding="utf-8"))["round"] if f.exists() else 0
                marche = MarcheSimule(semaine=rounds)
            else:
                marche = MarcheDVF(cache_dir=ROOT / "cache" / "dvf")
            fonds = Fonds(self.brain, marche, STATE_DIR, ROOT / "annonces")
            fonds.step()
            build(STATE_DIR, local=True)
            if fonds.failures == len(config.AGENTS):
                self.last_error = "Aucun agent n'a répondu : " + fonds.errors[0]
            self.last_run_file.write_text(datetime.now().strftime("%G-%V"))
            print(f"[{datetime.now():%H:%M}] Tour terminé.\n" + fonds.leaderboard_text())
        except Exception as e:
            self.last_error = str(e)
            traceback.print_exc()
        finally:
            self.running = False
            self.lock.release()
        return True

    def scheduler(self):
        """Chaque minute : si on a passé le jour et l'heure prévus cette semaine et que le tour
        de la semaine n'a pas été joué, on le joue (ça rattrape aussi un ordinateur éteint)."""
        while True:
            now = datetime.now()
            jour = JOURS.index(self.jour)
            passe = now.weekday() > jour or (now.weekday() == jour and now.strftime("%H:%M") >= self.heure)
            if passe and self.last_run_week() != now.strftime("%G-%V"):
                self.play_round()
            time.sleep(60)


def make_handler(arene):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/info":
                return self._send(200, {"mode": "local", "model": arene.brain.model, "running": arene.running,
                                        "error": arene.last_error, "jour": arene.jour, "heure": arene.heure})
            if path == "/data/agents.json":
                return self._send(200, {"manager": config.MANAGER, "agents": config.AGENTS, "model": arene.brain.model,
                                        "manager_every": config.MANAGER_EVERY})
            if path == "/rapport.html" and (STATE_DIR / "state.json").exists():
                return self._send(200, build(STATE_DIR, local=True).read_bytes(), "text/html; charset=utf-8")
            if path.startswith("/data/"):
                f = STATE_DIR / path[len("/data/"):]
            else:
                f = SITE / (path.lstrip("/") or "index.html")
            f = f.resolve()
            if not (f.is_relative_to(SITE.resolve()) or f.is_relative_to(STATE_DIR.resolve())) or not f.is_file():
                return self._send(404, {"error": "introuvable"})
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or f.suffix == ".js":
                ctype = ("text/javascript" if f.suffix == ".js" else ctype) + "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype)

        def do_POST(self):
            if self.path == "/api/tour":
                if arene.running:
                    return self._send(409, {"error": "Un tour est déjà en cours."})
                threading.Thread(target=arene.play_round, daemon=True).start()
                return self._send(202, {"ok": True})
            if self.path == "/api/chat":
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                try:
                    return self._send(200, {"text": arene.brain.chat(body.get("system", ""), body.get("messages", []))})
                except Exception as e:
                    return self._send(502, {"error": str(e)})
            self._send(404, {"error": "introuvable"})

    return Handler


def check_ollama(brain):
    try:
        models = brain.installed_models()
    except OSError:
        print("⚠ Ollama ne répond pas. Ouvre l'application Ollama puis relance ce script.")
        return False
    if not any(m == brain.model or m.split(":")[0] == brain.model for m in models):
        print(f"⚠ Le modèle {brain.model} n'est pas installé. Dans un terminal : ollama pull {brain.model}")
        print(f"  Modèles installés : {', '.join(models) or 'aucun'}")
        return False
    return True


def main():
    p = argparse.ArgumentParser(description="Agents immobiliers en local avec Ollama")
    p.add_argument("--jour", choices=JOURS, default="lundi", help="jour du tour hebdomadaire (défaut lundi)")
    p.add_argument("--heure", default="08:00", help="heure du tour hebdomadaire (défaut 08:00)")
    p.add_argument("--modele", default=config.OLLAMA_MODEL, help=f"modèle Ollama (défaut {config.OLLAMA_MODEL})")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--sans-planning", action="store_true", help="pas de tour automatique, seulement le bouton")
    p.add_argument("--sans-navigateur", action="store_true")
    p.add_argument("--revue-tous-les", type=int, default=config.MANAGER_EVERY,
                   help=f"Hélène corrige les propositions tous les N tours (défaut {config.MANAGER_EVERY})")
    p.add_argument("--marche", choices=["reel", "simule"], default="reel",
                   help="reel : vrais prix DVF · simule : marché et annonces fictifs, pour tester hors ligne")
    a = p.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    config.MANAGER_EVERY = max(1, a.revue_tous_les)
    brain = OllamaBrain(model=a.modele)
    check_ollama(brain)
    arene = Arene(brain, a.jour, a.heure, simulated=a.marche == "simule")
    if not a.sans_planning:
        threading.Thread(target=arene.scheduler, daemon=True).start()
        print(f"Tour automatique chaque {a.jour} à {a.heure} (garde cette fenêtre ouverte).")
    url = f"http://localhost:{a.port}"
    server = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(arene))
    print(f"Tableau de bord : {url}   (Ctrl+C pour arrêter)")
    if not a.sans_navigateur:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Arrêt.")


if __name__ == "__main__":
    main()
