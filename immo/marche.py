"""Prix du marché : vraies ventes (DVF, data.gouv.fr) ou marché simulé pour tester hors ligne.

DVF (Demandes de valeurs foncières) recense toutes les ventes immobilières en France, publiées
par l'État. On s'en sert pour calculer le prix médian au m² de chaque commune et vérifier que les
prix annoncés par les agents tiennent la route."""
import csv
import io
import random
import statistics
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config

TYPES = ("appartement", "maison")


def toutes_communes():
    out = {}
    for a in config.AGENTS.values():
        out.update(a["communes"])
    return out


def zone_de(insee):
    """Clé de l'agent « géographique » qui couvre cette commune (pour la fourchette de loyers)."""
    for k, a in config.AGENTS.items():
        if k != "renovation" and insee in a["communes"]:
            return k
    return "renovation"


class Marche:
    """Interface commune : prix médian au m² par commune et type de bien."""

    def mediane_m2(self, insee, type_bien):
        s = self.stats(insee)
        t = s["par_type"].get(type_bien)
        if t and t["ventes"] >= 5:
            return t["mediane_m2"]
        return s["mediane_m2"]

    def stats(self, insee):
        raise NotImplementedError

    def ventes_recentes(self, insee, n=5):
        return []

    def annonces_simulees(self, key):
        return []

    def label(self):
        raise NotImplementedError

    def advance(self):
        return True


class MarcheDVF(Marche):
    """Ventes réelles : fichiers geo-dvf par commune (data.gouv.fr), mis en cache dans cache/dvf/."""

    URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/communes/{dep}/{insee}.csv"

    def __init__(self, cache_dir="cache/dvf", annees=4):
        self.cache = Path(cache_dir)
        self.ventes = {}
        an = date.today().year
        for insee in toutes_communes():
            rows = []
            for y in range(an - annees, an + 1):
                rows += self._ventes(insee, y)
            self.ventes[insee] = sorted(rows, key=lambda r: r["date"])
        vides = [toutes_communes()[i] for i, v in self.ventes.items() if not v]
        if len(vides) == len(self.ventes):
            raise RuntimeError("Impossible de télécharger les ventes DVF (réseau ?)")
        if vides:
            print(f"Aucune vente DVF trouvée pour : {', '.join(vides)}")
        self._stats = {}

    def _telecharger(self, insee, annee):
        f = self.cache / str(annee) / f"{insee}.csv"
        # les années passées ne changent plus ; l'année en cours est retéléchargée chaque mois
        if f.exists() and (annee < date.today().year - 1 or
                           datetime.now().timestamp() - f.stat().st_mtime < 30 * 86400):
            return f.read_text(encoding="utf-8")
        url = self.URL.format(annee=annee, dep=insee[:2], insee=insee)
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                text = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:  # année pas (encore) publiée
                return ""
            raise
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        return text

    def _ventes(self, insee, annee):
        """Ventes simples d'un seul logement (une maison ou un appartement, avec ou sans dépendance)."""
        text = self._telecharger(insee, annee)
        if not text:
            return []
        mutations = {}
        for row in csv.DictReader(io.StringIO(text)):
            if row.get("nature_mutation") != "Vente":
                continue
            mutations.setdefault(row["id_mutation"], []).append(row)
        out = []
        for rows in mutations.values():
            logements = [r for r in rows if r.get("type_local") in ("Appartement", "Maison")]
            autres = [r for r in rows if r.get("type_local") not in ("Appartement", "Maison", "Dépendance", "")]
            if len(logements) != 1 or autres:
                continue
            r = logements[0]
            try:
                prix = float(r["valeur_fonciere"])
                surface = float(r["surface_reelle_bati"])
            except (TypeError, ValueError):
                continue
            if surface < 9 or prix < 10_000:
                continue
            m2 = prix / surface
            if not 300 <= m2 <= 40_000:
                continue
            out.append({"date": r["date_mutation"], "type": r["type_local"].lower(), "prix": prix,
                        "surface": surface, "pieces": r.get("nombre_pieces_principales") or "",
                        "prix_m2": m2, "adresse": f"{r.get('adresse_numero', '')} {r.get('adresse_nom_voie', '')}".strip()})
        return out

    def stats(self, insee):
        if insee in self._stats:
            return self._stats[insee]
        ventes = self.ventes.get(insee, [])
        if not ventes:
            s = {"mediane_m2": self._mediane_zone(insee), "ventes_12m": 0, "evolution_1an": 0.0,
                 "par_type": {}, "derniere_vente": None}
            self._stats[insee] = s
            return s
        fin = datetime.strptime(ventes[-1]["date"], "%Y-%m-%d").date()
        d1 = (fin - timedelta(days=365)).isoformat()
        d2 = (fin - timedelta(days=730)).isoformat()
        recent = [v for v in ventes if v["date"] > d1]
        avant = [v for v in ventes if d2 < v["date"] <= d1]
        med = lambda vs: statistics.median(v["prix_m2"] for v in vs) if vs else 0.0
        par_type = {}
        for t in TYPES:
            vt = [v for v in recent if v["type"] == t]
            if len(vt) < 5:  # trop peu de ventes sur 12 mois : on élargit à 24 mois
                vt = [v for v in ventes if v["type"] == t and v["date"] > d2]
            if vt:
                par_type[t] = {"mediane_m2": round(med(vt)), "ventes": len(vt)}
        base = recent if len(recent) >= 5 else [v for v in ventes if v["date"] > d2] or ventes
        s = {
            "mediane_m2": round(med(base)),
            "ventes_12m": len(recent),
            "evolution_1an": (med(recent) / med(avant) - 1) if recent and avant else 0.0,
            "par_type": par_type,
            "derniere_vente": ventes[-1]["date"],
        }
        self._stats[insee] = s
        return s

    def _mediane_zone(self, insee):
        k = zone_de(insee)
        meds = [self.stats(c)["mediane_m2"] for c in config.AGENTS[k]["communes"] if c != insee and self.ventes.get(c)]
        return round(statistics.median(meds)) if meds else 3000

    def ventes_recentes(self, insee, n=5):
        return [{k: (round(v) if isinstance(v, float) else v) for k, v in s.items()}
                for s in self.ventes.get(insee, [])[-n:]]

    def label(self):
        return f"{datetime.now(timezone.utc):%Y-%m-%d}"


class MarcheSimule(Marche):
    """Marché fictif, sans réseau : prix médians qui évoluent doucement et annonces inventées
    (dont quelques bonnes affaires et quelques pièges), pour tester le système gratuitement."""

    BASE = {"83069": 4800, "38185": 2700, "38421": 2400, "38151": 2000, "38229": 3500,
            "38567": 3600, "38191": 5200, "38253": 4600, "38548": 3300, "73257": 7800, "73296": 8200}

    def __init__(self, seed=42, semaine=0):
        self.rng = random.Random(seed)
        self.t = 0
        self.med = {c: float(self.BASE.get(c, 3000)) for c in toutes_communes()}
        self.trend = {c: self.rng.gauss(0.0005, 0.001) for c in self.med}
        for _ in range(semaine):
            self.advance()

    def stats(self, insee):
        m = self.med[insee]
        return {"mediane_m2": round(m), "ventes_12m": 120, "evolution_1an": self.trend[insee] * 52,
                "par_type": {"appartement": {"mediane_m2": round(m), "ventes": 90},
                             "maison": {"mediane_m2": round(m * 1.1), "ventes": 30}},
                "derniere_vente": self.label()}

    def annonces_simulees(self, key):
        rng = random.Random(f"{key}-{self.t}")
        communes = list(config.AGENTS[key]["communes"])
        out = []
        for i in range(6):
            c = rng.choice(communes)
            t = rng.choice(TYPES)
            surface = round(rng.uniform(18, 110))
            # prix demandé / prix du marché : le plus souvent proche du marché, parfois une affaire, parfois un piège
            ratio = rng.uniform(0.3, 0.4) if rng.random() < 0.1 else rng.gauss(0.97, 0.12)
            renover = key == "renovation" or rng.random() < 0.25
            travaux = round(surface * rng.uniform(300, 1200), -2) if renover else 0
            if renover:
                ratio *= 0.8
            prix = round(surface * self.mediane_m2(c, t) * ratio, -3)
            lo, hi = config.AGENTS[zone_de(c)]["loyer_m2"]
            loyer = round(surface * rng.uniform(lo, hi * 1.3))
            out.append({"titre": f"{t.capitalize()} {surface} m² à {toutes_communes()[c]}", "url": f"https://exemple.fr/annonce/{key}-{self.t}-{i}",
                        "commune_insee": c, "type_bien": t, "surface_m2": surface, "prix": prix,
                        "travaux_estimes": travaux, "loyer_mensuel_estime": loyer, "dpe": rng.choice("CDEFG") if renover else rng.choice("BCDE")})
        return out

    def label(self):
        return f"semaine simulée {self.t}"

    def advance(self):
        for c in self.med:
            self.med[c] *= 1 + self.trend[c] + self.rng.gauss(0, 0.003)
        self.t += 1
        return True
