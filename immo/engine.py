"""Orchestration : tours de prospection, vérification des chiffres, achats fictifs, classement,
revues de la directrice d'investissement, sauvegarde."""
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config
from .config import display
from .marche import toutes_communes, zone_de


def metrics(curve):
    """Statistiques d'une courbe de valeur (liste de valeurs, un point par semaine)."""
    if len(curve) < 2:
        return {"rendement_total": 0.0, "drawdown_max": 0.0, "sharpe": 0.0}
    rets = [b / a - 1 for a, b in zip(curve, curve[1:]) if a > 0]
    mean = sum(rets) / len(rets)
    std = math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets)) if len(rets) > 1 else 0.0
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak)
    return {
        "rendement_total": curve[-1] / curve[0] - 1,
        "drawdown_max": mdd,
        "sharpe": mean / std * math.sqrt(52) if std > 1e-12 else 0.0,
    }


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
            share = config.INITIAL_CAPITAL / len(config.AGENTS)
            self.state = {
                "round": 0, "dates": [], "reviews": [],
                "agents": {k: {"cash": share, "biens": [], "curve": [], "nav": [], "last_eq": None, "notes": "",
                               "feedback": "", "analyse": "", "budget": 1 / len(config.AGENTS),
                               "opportunites": [], "loyers_cumules": 0.0}
                           for k in config.AGENTS},
            }

    # ---------- valorisation ----------

    def valeur_bien(self, b):
        med = self.marche.mediane_m2(b["commune_insee"], b["type_bien"])
        return b["surface_m2"] * med * (1 - config.FRAIS_REVENTE)

    def equity(self, key):
        a = self.state["agents"][key]
        return a["cash"] + sum(self.valeur_bien(b) for b in a["biens"])

    def total_equity(self):
        return sum(self.equity(k) for k in config.AGENTS)

    # ---------- vérification d'une opportunité ----------

    def evaluer(self, key, o):
        """Recalcule les chiffres d'une opportunité avec les prix DVF et applique les garde-fous."""
        o = dict(o)
        motifs = []
        c = str(o.get("commune_insee", "")).strip()
        o["commune_insee"] = c
        t = str(o.get("type_bien", "")).lower()
        o["type_bien"] = "maison" if "maison" in t or "villa" in t or "chalet" in t else "appartement"
        if c not in config.AGENTS[key]["communes"]:
            motifs.append("commune hors zone")
        surface, prix = float(o.get("surface_m2") or 0), float(o.get("prix") or 0)
        travaux = max(0.0, float(o.get("travaux_estimes") or 0))
        if not (9 <= surface <= 1000) or prix <= 0:
            motifs.append("surface ou prix invalide")
        if not str(o.get("url", "")).startswith("http"):
            motifs.append("pas de lien vers l'annonce")
        if motifs:
            o.update(valide=False, motif=", ".join(motifs), score=0.0)
            return o
        med = self.marche.mediane_m2(c, o["type_bien"])
        ratio = prix / surface / med
        lo, hi = config.AGENTS[zone_de(c)]["loyer_m2"]
        loyer_annonce = max(0.0, float(o.get("loyer_mensuel_estime") or 0))
        loyer = min(loyer_annonce, hi * surface, config.RENDEMENT_BRUT_MAX * prix / 12)
        cout = prix * (1 + config.FRAIS_NOTAIRE) + travaux
        valeur = surface * med * (1 - config.FRAIS_REVENTE)
        marge = valeur / cout - 1
        rdt = loyer * 12 * (1 - config.CHARGES_LOCATIVES) / cout
        o.update(
            commune=toutes_communes().get(c, c), surface_m2=surface, prix=prix, travaux_estimes=travaux,
            loyer_retenu=round(loyer), loyer_plafonne=loyer < loyer_annonce - 1,
            prix_m2=round(prix / surface), mediane_m2=round(med), ecart_marche=ratio - 1,
            cout_total=round(cout), valeur_estimee=round(valeur), marge=marge, rendement_net=rdt,
            score=round(marge * 50 + rdt * 200, 1),
        )
        if ratio < config.PRIX_SUSPECT:
            o.update(valide=False, motif=f"prix suspect ({ratio:.0%} de la médiane du secteur)", score=0.0)
        else:
            o.update(valide=True, motif="")
        return o

    # ---------- classement ----------

    def leaderboard(self):
        rows = []
        for k, a in self.state["agents"].items():
            # Les performances se mesurent sur la valeur d'une part (nav), pour que les
            # transferts décidés par la directrice ne comptent pas comme gains ou pertes.
            curve = a["nav"] or [1.0]
            m = metrics(curve)
            recent = curve[-(config.MANAGER_EVERY + 1):]
            m["rendement_periode"] = recent[-1] / recent[0] - 1 if recent[0] > 0 else 0.0
            m["drawdown_max_total"] = m["drawdown_max"]
            m["drawdown_max"] = metrics(recent)["drawdown_max"]
            m["capital"] = a["curve"][-1] if a["curve"] else self.equity(k)
            m["biens"] = len(a["biens"])
            m["cash"] = a["cash"]
            rows.append((k, m))
        rows.sort(key=lambda r: r[1]["rendement_total"], reverse=True)
        return rows

    def leaderboard_text(self):
        eur = lambda x: f"{x:,.0f} €".replace(",", " ")
        return "\n".join(
            f"{i}. {display(k)} : valeur {eur(m['capital'])}, rendement {m['rendement_total']:+.2%}, "
            f"{m['biens']} bien(s), trésorerie {eur(m['cash'])}"
            for i, (k, m) in enumerate(self.leaderboard(), 1))

    # ---------- agents ----------

    def _prompt(self, key):
        ag, st = config.AGENTS[key], self.state["agents"][key]
        eq = self.equity(key)
        marche = {}
        for c, nom in ag["communes"].items():
            s = self.marche.stats(c)
            marche[c] = {"nom": nom, **s, "ventes_recentes": self.marche.ventes_recentes(c, 3)}
        biens = [{"titre": b["titre"], "commune": toutes_communes().get(b["commune_insee"]), "cout_total": round(b["cout_total"]),
                  "valeur_estimee": round(self.valeur_bien(b)), "loyer": b["loyer_retenu"]} for b in st["biens"]]
        data = {
            "date": self.marche.label(),
            "tresorerie": round(st["cash"]),
            "valeur_du_compte": round(eq),
            "cout_max_par_bien": round(min(st["cash"], config.MAX_PART_PAR_BIEN * eq)),
            "portefeuille": biens,
            "marche": marche,
        }
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

    def _acheter(self, key, o):
        st = self.state["agents"][key]
        eq = self.equity(key)
        if not o["valide"]:
            return f"achat refusé : {o['motif']}"
        if o["cout_total"] > st["cash"]:
            return "achat refusé : trésorerie insuffisante"
        if o["cout_total"] > config.MAX_PART_PAR_BIEN * eq:
            return f"achat refusé : bien trop cher pour le compte (max {config.MAX_PART_PAR_BIEN:.0%})"
        if any(b["url"] == o["url"] for a in self.state["agents"].values() for b in a["biens"]):
            return "achat refusé : bien déjà acheté"
        semaines_travaux = math.ceil(o["travaux_estimes"] / config.TRAVAUX_PAR_MOIS * 52 / 12)
        st["cash"] -= o["cout_total"]
        st["biens"].append({**o, "achat_round": self.state["round"], "achat_date": self.marche.label(),
                            "loyer_des_round": self.state["round"] + 1 + semaines_travaux})
        return None

    def prospection(self):
        with ThreadPoolExecutor(max_workers=len(config.AGENTS)) as pool:
            results = list(pool.map(self._run_agent, config.AGENTS))
        self.errors = [f"{key} : {err}" for key, _, err in results if err]
        self.failures = len(self.errors)
        log = [f"\n## Tour {self.state['round']} : {self.marche.label()}\n"]
        for key, d, err in results:
            name = display(key)
            if err:
                log.append(f"**{name}** : {err}\n")
                continue
            st = self.state["agents"][key]
            opps = [self.evaluer(key, o.model_dump()) for o in d.opportunites[:config.MAX_OPPORTUNITES]]
            st["opportunites"], st["analyse"], st["notes"] = opps, d.analyse_marche, d.note_pour_plus_tard
            for o in opps:
                o["round"], o["date"] = self.state["round"], self.marche.label()
            lignes = "".join(
                f"  - {o.get('titre', '?')} : " + f"{o['prix']:,.0f} €".replace(",", "\u202f")
                + (f", marge {o['marge']:+.0%}, rendement net {o['rendement_net']:.1%}, score {o['score']}"
                   if o["valide"] else f" (écartée : {o['motif']})") + f" {o.get('url', '')}\n"
                for o in opps)
            achat = ""
            if 0 <= d.achat < len(opps):
                refus = self._acheter(key, opps[d.achat])
                achat = f"  Achat : {opps[d.achat].get('titre')} ({refus or 'validé'}). {d.justification_achat}\n"
            log.append(f"**{name}** : {d.analyse_marche}\n{lignes}{achat}")
        self._journal("".join(log))

    # ---------- directrice d'investissement ----------

    def revue(self):
        board = self.leaderboard()
        context = {k: m for k, m in board}
        details = []
        for k, m in board:
            st = self.state["agents"][k]
            opps = "; ".join(f"{o.get('titre')} (score {o['score']}, marge {o.get('marge', 0):+.0%})"
                             for o in st["opportunites"] if o["valide"]) or "aucune retenue"
            biens = "; ".join(f"{b['titre']} acheté {b['cout_total']:,.0f} €, valeur {self.valeur_bien(b):,.0f} €"
                              for b in st["biens"]) or "aucun"
            details.append(f"- {k} ({display(k)}) : rendement période {m['rendement_periode']:+.2%}, "
                           f"rendement total {m['rendement_total']:+.2%}, part actuelle {st['budget']:.0%}, "
                           f"trésorerie {st['cash']:,.0f} €.\n  Biens : {biens}\n  Dernières opportunités : {opps}\n"
                           f"  Dernière analyse : {st['analyse'][:300]}")
        prompt = (f"Revue du tour {self.state['round']} ({self.marche.label()}).\n"
                  f"Valeur totale de l'enveloppe : {self.total_equity():,.0f} €.\n\n"
                  f"Performances (identifiants à utiliser : {', '.join(config.AGENTS)}) :\n" + "\n".join(details))
        try:
            d = self.brain.manager(prompt, context)
        except Exception as e:
            self._journal(f"\n### Revue de {config.MANAGER['name']} : erreur ({e}), répartition inchangée\n")
            return
        weights = {b.agent: b.weight for b in d.budgets if b.agent in config.AGENTS}
        for k in config.AGENTS:
            weights.setdefault(k, self.state["agents"][k]["budget"])
        weights = self._bound_weights(weights)
        self._reallouer(weights)
        for b in d.budgets:
            if b.agent in config.AGENTS:
                self.state["agents"][b.agent]["feedback"] = b.feedback
        self.state["reviews"].append({"round": self.state["round"], "date": self.marche.label(),
                                      "commentary": d.commentary, "coup_de_coeur": d.coup_de_coeur, "budgets": weights})
        alloc = ", ".join(f"{display(k)} {w:.0%}" for k, w in weights.items())
        self._journal(f"\n### Revue de {config.MANAGER['name']} (directrice d'investissement)\n{d.commentary}\n\n"
                      f"Coup de cœur : {d.coup_de_coeur}\n\nNouvelle répartition : {alloc}\n")

    def _reallouer(self, weights):
        """Les biens ne se revendent pas d'un claquement de doigts : seule la trésorerie circule.
        Les agents au-dessus de leur part cèdent du cash à ceux qui sont en dessous."""
        total = self.total_equity()
        agents = self.state["agents"]
        excess = {k: self.equity(k) - weights[k] * total for k in agents}
        pot = 0.0
        for k, e in excess.items():
            if e > 0:
                give = min(e, agents[k]["cash"])
                agents[k]["cash"] -= give
                pot += give
        besoins = {k: -e for k, e in excess.items() if e < 0}
        tot_besoin = sum(besoins.values())
        for k, b in besoins.items():
            agents[k]["cash"] += pot * b / tot_besoin if tot_besoin else 0
        if not besoins:  # personne en dessous : on rend le cash au prorata
            for k in agents:
                agents[k]["cash"] += pot / len(agents)
        for k in agents:
            agents[k]["budget"] = weights[k]
            agents[k]["last_eq"] = self.equity(k)

    @staticmethod
    def _bound_weights(weights):
        """Ramène les parts dans [min, max] avec une somme de 1."""
        w = {k: max(0.0, v) for k, v in weights.items()}
        s = sum(w.values()) or 1
        w = {k: v / s for k, v in w.items()}
        for _ in range(50):
            w = {k: min(config.MAX_AGENT_ALLOCATION, max(config.MIN_AGENT_ALLOCATION, v)) for k, v in w.items()}
            s = sum(w.values())
            if abs(s - 1) < 1e-9:
                break
            free = [k for k, v in w.items() if config.MIN_AGENT_ALLOCATION < v < config.MAX_AGENT_ALLOCATION] or list(w)
            adj = (1 - s) / len(free)
            for k in free:
                w[k] += adj
        return w

    # ---------- boucle ----------

    def encaisser_loyers(self):
        for a in self.state["agents"].values():
            for b in a["biens"]:
                if self.state["round"] >= b["loyer_des_round"]:
                    net = b["loyer_retenu"] * 12 / 52 * config.SEMAINES_PAR_TOUR * (1 - config.CHARGES_LOCATIVES)
                    a["cash"] += net
                    a["loyers_cumules"] += net

    def mark(self):
        self.state["dates"].append(self.marche.label())
        for k, a in self.state["agents"].items():
            eq = self.equity(k)
            prev = a["nav"][-1] if a["nav"] else 1.0
            a["nav"].append(prev * eq / a["last_eq"] if a["last_eq"] else 1.0)
            a["curve"].append(eq)
            a["last_eq"] = eq

    def step(self):
        """Un tour complet : loyers, valorisation, revue éventuelle, prospection et achats."""
        self.encaisser_loyers()
        self.mark()
        r = self.state["round"]
        if r > 0 and r % config.MANAGER_EVERY == 0:
            self.revue()
        self.prospection()
        self.state["round"] += 1
        self.save()

    def save(self):
        self.state["medianes"] = {c: self.marche.stats(c)["mediane_m2"] for c in toutes_communes()}
        for a in self.state["agents"].values():
            for b in a["biens"]:
                b["valeur_actuelle"] = round(self.valeur_bien(b))
        self.state_file.write_text(json.dumps(self.state, indent=1, ensure_ascii=False), encoding="utf-8")

    def _journal(self, text):
        with self.journal_file.open("a", encoding="utf-8") as f:
            f.write(text)
