"""Orchestration : tours de recherche, vérification des chiffres, corrections de la directrice
d'investissement, classement, sauvegarde. Aucun achat : les agents proposent, Hélène note."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config
from .config import display
from .marche import toutes_communes, zone_de

eur = lambda x: f"{x:,.0f} €".replace(",", " ")


def lire_annonces(dossier):
    """Annonces déposées à la main (fichiers .txt / .md), hors LISEZMOI."""
    d = Path(dossier)
    if not d.is_dir():
        return ""
    parts = [f"--- {f.name} ---\n{f.read_text(encoding='utf-8', errors='replace')[:6000]}"
             for f in sorted(d.iterdir()) if f.suffix in (".txt", ".md") and not f.name.startswith("LISEZMOI")]
    return "\n\n".join(parts)[:30000]


class Fonds:
    def __init__(self, brain, marche, state_dir, annonces_dir="annonces"):
        self.brain = brain
        self.marche = marche
        self.annonces_dir = Path(annonces_dir)
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.dir / "state.json"
        self.journal_file = self.dir / "journal.md"
        self.errors, self.failures = [], 0
        if self.state_file.exists():
            self.state = json.loads(self.state_file.read_text(encoding="utf-8"))
        else:
            self.state = {
                "round": 0, "dates": [], "reviews": [],
                "agents": {k: {"analyse": "", "notes": "", "feedback": "", "propositions": [], "notes_tours": []}
                           for k in config.AGENTS},
            }

    # ---------- vérification d'une proposition ----------

    def evaluer(self, key, o):
        """Recalcule les chiffres d'une proposition avec les prix DVF et signale ce qui cloche."""
        o = dict(o)
        motifs = []
        c = str(o.get("commune_insee", "")).strip()
        o["commune_insee"] = c
        o["commune"] = toutes_communes().get(c, c)
        t = str(o.get("type_bien", "")).lower()
        o["type_bien"] = "maison" if "maison" in t or "villa" in t or "chalet" in t else "appartement"
        o["categorie"] = o.get("categorie") if o.get("categorie") in config.CATEGORIES else "choix_agent"
        if c not in config.AGENTS[key]["communes"]:
            motifs.append("commune hors zone")
        surface, prix = float(o.get("surface_m2") or 0), float(o.get("prix") or 0)
        travaux = max(0.0, float(o.get("travaux_estimes") or 0))
        if not (9 <= surface <= 1000) or prix <= 0:
            motifs.append("surface ou prix invalide")
        if prix > config.BUDGET_MAX:
            motifs.append(f"hors budget ({eur(prix)} > {eur(config.BUDGET_MAX)})")
        if not str(o.get("url", "")).startswith("http"):
            motifs.append("pas de lien vers l'annonce")
        if c not in toutes_communes() or surface <= 0 or prix <= 0:
            o.update(valide=False, motif=", ".join(motifs), surface_m2=surface, prix=prix, travaux_estimes=travaux)
            return o
        med = self.marche.mediane_m2(c, o["type_bien"])
        ratio = prix / surface / med
        lo, hi = config.AGENTS[zone_de(c)]["loyer_m2"]
        loyer_annonce = max(0.0, float(o.get("loyer_mensuel_estime") or 0))
        loyer = min(loyer_annonce, hi * surface, config.RENDEMENT_BRUT_MAX * prix / 12)
        cout = prix * (1 + config.FRAIS_NOTAIRE) + travaux
        valeur = surface * med * (1 - config.FRAIS_REVENTE)
        if ratio < config.PRIX_SUSPECT:
            motifs.append(f"prix suspect ({ratio:.0%} de la médiane du secteur)")
        o.update(
            surface_m2=surface, prix=prix, travaux_estimes=travaux,
            loyer_retenu=round(loyer), loyer_plafonne=loyer < loyer_annonce - 1,
            prix_m2=round(prix / surface), mediane_m2=round(med), ecart_marche=ratio - 1,
            cout_total=round(cout), valeur_estimee=round(valeur), marge=valeur / cout - 1,
            rendement_net=loyer * 12 * (1 - config.CHARGES_LOCATIVES) / cout,
            valide=not motifs, motif=", ".join(motifs),
        )
        return o

    # ---------- classement ----------

    def leaderboard(self):
        """Classement à la note moyenne donnée par Hélène sur toutes les semaines."""
        rows = []
        for k, a in self.state["agents"].items():
            notes = a["notes_tours"]
            rows.append((k, {"note_moyenne": sum(notes) / len(notes) if notes else 0.0,
                             "derniere_note": notes[-1] if notes else None, "tours": len(notes)}))
        rows.sort(key=lambda r: r[1]["note_moyenne"], reverse=True)
        return rows

    def leaderboard_text(self):
        if not any(m["tours"] for _, m in self.leaderboard()):
            return "pas encore de notes"
        return "\n".join(
            f"{i}. {display(k)} : note moyenne {m['note_moyenne']:.1f}/10"
            + (f" (dernière semaine {m['derniere_note']:.1f}/10)" if m["derniere_note"] is not None else "")
            for i, (k, m) in enumerate(self.leaderboard(), 1))

    # ---------- agents ----------

    def _prompt(self, key):
        ag, st = config.AGENTS[key], self.state["agents"][key]
        marche = {}
        for c, nom in ag["communes"].items():
            s = self.marche.stats(c)
            marche[c] = {"nom": nom, **s, "ventes_recentes": self.marche.ventes_recentes(c, 3)}
        precedentes = [{"titre": p.get("titre"), "url": p.get("url"), "note": p.get("note"), "verdict": p.get("verdict"),
                        "correction": p.get("correction")} for p in st["propositions"]]
        data = {"date": self.marche.label(), "budget_max": config.BUDGET_MAX, "marche": marche,
                "tes_propositions_precedentes": precedentes}
        sim = self.marche.annonces_simulees(key)
        if sim:
            data["annonces_simulees"] = sim
        fournies = lire_annonces(self.annonces_dir / key)
        return (f"Tour {self.state['round']} ({self.marche.label()}).\n\n"
                f"Classement actuel :\n{self.leaderboard_text()}\n\n"
                f"Message de {config.MANAGER['name']} : {st['feedback'] or 'aucun pour le moment'}\n"
                f"Ta note du tour précédent : {st['notes'] or 'aucune'}\n\n"
                + (f"Annonces déposées par Eliott (à étudier en priorité) :\n{fournies}\n\n" if fournies else "")
                + f"DONNÉES_JSON:{json.dumps(data, ensure_ascii=False)}")

    def _run_agent(self, key):
        try:
            return key, self.brain.agent(key, self._prompt(key)), None
        except Exception as e:  # un agent en panne ne bloque pas les autres
            return key, None, f"erreur : {e}"

    def prospection(self):
        with ThreadPoolExecutor(max_workers=len(config.AGENTS)) as pool:
            results = list(pool.map(self._run_agent, config.AGENTS))
        self.errors = [f"{key} : {err}" for key, _, err in results if err]
        self.failures = len(self.errors)
        log = [f"\n## Semaine {self.state['round']} : {self.marche.label()}\n"]
        for key, d, err in results:
            name = display(key)
            st = self.state["agents"][key]
            if err:
                log.append(f"**{name}** : {err} (propositions de la semaine précédente conservées)\n")
                continue
            props = [self.evaluer(key, o.model_dump()) for o in d.propositions[:len(config.ORDRE)]]
            for p in props:
                p["round"], p["date"] = self.state["round"], self.marche.label()
            st["propositions"], st["analyse"], st["notes"] = props, d.analyse_marche, d.note_pour_plus_tard
            lignes = "".join(
                f"  - [{p['categorie']}] {p.get('titre', '?')} : " + eur(p["prix"])
                + (f", {eur(p['prix_m2'])}/m² (marché {eur(p['mediane_m2'])}/m²)" if p.get("prix_m2") else "")
                + (f" ⚠ {p['motif']}" if p.get("motif") else "") + f" {p.get('url', '')}\n"
                for p in props)
            log.append(f"**{name}** : {d.analyse_marche}\n{lignes}")
        self._journal("".join(log))

    # ---------- directrice d'investissement ----------

    def revue(self):
        props = {k: [{"numero": i, **{f: p.get(f) for f in (
                    "categorie", "titre", "url", "commune", "quartier", "type_bien", "surface_m2", "prix", "travaux_estimes",
                    "loyer_retenu", "dpe", "pourquoi", "risques", "prix_m2", "mediane_m2", "ecart_marche", "rendement_net",
                    "valide", "motif")}} for i, p in enumerate(a["propositions"])]
                 for k, a in self.state["agents"].items() if a["propositions"]}
        if not props:
            return
        analyses = "\n".join(f"- {k} ({display(k)}) : {a['analyse']}" for k, a in self.state["agents"].items())
        prompt = (f"Revue de la semaine {self.state['round']} ({self.marche.label()}).\n"
                  f"Classement avant cette revue :\n{self.leaderboard_text()}\n\n"
                  f"Analyses des agents :\n{analyses}\n\n"
                  f"Propositions à corriger (identifiants d'agents : {', '.join(props)}, numéros 0 à 4) :\n"
                  f"DONNÉES_JSON:{json.dumps({'propositions': props}, ensure_ascii=False)}")
        try:
            d = self.brain.manager(prompt, props)
        except Exception as e:
            self._journal(f"\n### Revue d'{config.MANAGER['name']} : erreur ({e})\n")
            return
        champs = ("note", "verdict", "prix_m2_constate", "source_prix", "avis_quartier", "correction")
        for c in d.corrections:
            plist = self.state["agents"].get(c.agent, {}).get("propositions", [])
            if 0 <= c.numero < len(plist):
                c.note = max(0.0, min(10.0, c.note))
                plist[c.numero].update({f: getattr(c, f) for f in champs})
        notes_semaine = {}
        for k, a in self.state["agents"].items():
            notes = [p["note"] for p in a["propositions"] if p.get("round") == self.state["round"] and p.get("note") is not None]
            if notes:
                notes_semaine[k] = round(sum(notes) / len(notes), 2)
                a["notes_tours"].append(notes_semaine[k])
        for f in d.feedbacks:
            if f.agent in self.state["agents"]:
                self.state["agents"][f.agent]["feedback"] = f.feedback
        self.state["reviews"].append({"round": self.state["round"], "date": self.marche.label(), "commentary": d.commentary,
                                      "coup_de_coeur": d.coup_de_coeur, "notes": notes_semaine})
        lignes = "".join(f"- {display(k)} : {n:.1f}/10\n" for k, n in notes_semaine.items())
        detail = "".join(f"  - {c.agent} n°{c.numero} : {c.note:.0f}/10, {c.verdict}. {c.correction}\n" for c in d.corrections)
        self._journal(f"\n### Revue d'{config.MANAGER['name']} (directrice d'investissement)\n{d.commentary}\n\n"
                      f"Coup de cœur : {d.coup_de_coeur}\n\nNotes de la semaine :\n{lignes}{detail}")

    # ---------- boucle ----------

    def step(self):
        """Un tour complet : recherche des agents, puis corrections d'Hélène."""
        self.state["dates"].append(self.marche.label())
        self.prospection()
        if self.state["round"] % config.MANAGER_EVERY == 0:
            self.revue()
        self.state["round"] += 1
        self.save()

    def save(self):
        self.state["medianes"] = {c: self.marche.stats(c)["mediane_m2"] for c in toutes_communes()}
        self.state_file.write_text(json.dumps(self.state, indent=1, ensure_ascii=False), encoding="utf-8")

    def _journal(self, text):
        with self.journal_file.open("a", encoding="utf-8") as f:
            f.write(text)
