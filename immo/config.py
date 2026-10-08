"""Configuration du système : zones, capital, règles d'investissement, modèle."""
import os

MODEL = os.environ.get("IMMO_MODEL", "claude-opus-5-5")
# Modèle local (Ollama) quand on lance avec --brain local
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
AGENT_EFFORT = os.environ.get("AGENT_EFFORT", "medium")
MANAGER_EFFORT = os.environ.get("MANAGER_EFFORT", "high")
# Les agents cherchent eux-mêmes des annonces en ligne (Claude uniquement)
WEB_SEARCH = os.environ.get("IMMO_WEB_SEARCH", "1") == "1"
MAX_RECHERCHES = 8            # recherches web max par agent et par tour

INITIAL_CAPITAL = 2_000_000.0  # enveloppe fictive totale, répartie à parts égales au départ
FRAIS_NOTAIRE = 0.08           # frais d'acquisition dans l'ancien
FRAIS_REVENTE = 0.05           # décote appliquée à la valorisation (frais d'agence à la revente)
CHARGES_LOCATIVES = 0.25       # part des loyers perdue en charges, taxe foncière, vacance, gestion
TRAVAUX_PAR_MOIS = 15_000.0    # rythme des travaux : pas de loyer tant qu'ils ne sont pas finis

# Règles appliquées par le code, quoi que décident les agents
MAX_ACHATS_PAR_TOUR = 1
MAX_PART_PAR_BIEN = 0.6        # un bien ne peut pas coûter plus de 60 % du compte de l'agent
MAX_OPPORTUNITES = 3           # opportunités présentées par agent et par tour
PRIX_SUSPECT = 0.4             # prix au m² < 40 % de la médiane du secteur : annonce rejetée (erreur, viager, arnaque)
RENDEMENT_BRUT_MAX = 0.15      # loyer annoncé plafonné à 15 % de rendement brut
MIN_AGENT_ALLOCATION = 0.10    # le manager doit laisser au moins 10 % à chaque agent
MAX_AGENT_ALLOCATION = 0.40    # et au plus 40 %
MANAGER_EVERY = int(os.environ.get("MANAGER_EVERY", 4))  # revue du manager tous les N tours (1 tour = 1 semaine)
SEMAINES_PAR_TOUR = 1

MANAGER = {
    "name": "Hélène",
    "role": "Directrice d'investissement",
    "emoji": "🧭",
    "persona": "Directrice d'investissement immobilier exigeante et juste. Elle récompense les dossiers "
               "solides et chiffrés, sanctionne les paris hasardeux et parle franchement à ses agents.",
}

HYERES = {"83069": "Hyères"}
GRENOBLE = {"38185": "Grenoble", "38421": "Saint-Martin-d'Hères", "38151": "Échirolles", "38229": "Meylan"}
STATIONS = {"38567": "Chamrousse", "38191": "Huez (Alpe d'Huez)", "38253": "Les Deux Alpes",
            "38548": "Villard-de-Lans", "73257": "Les Belleville (Val Thorens, Les Menuires)", "73296": "Tignes"}

AGENTS = {
    "hyeres": {
        "name": "Marius",
        "role": "Agent Hyères",
        "emoji": "☀️",
        "persona": "Varois pur jus, il connaît chaque quartier de Hyères, de Costebelle à la presqu'île de Giens. "
                   "Il arbitre entre location à l'année et saisonnière et se méfie des prix gonflés en bord de mer.",
        "zone": "Hyères-les-Palmiers (Var) : centre-ville, Costebelle, L'Ayguade, Le Port, Giens",
        "strategie": "appartements et maisons avec un bon rapport prix / emplacement, rentables en location "
                     "à l'année ou saisonnière",
        "communes": HYERES,
        "loyer_m2": (11.0, 24.0),   # fourchette plausible de loyer mensuel au m² (€)
    },
    "grenoble": {
        "name": "Chloé",
        "role": "Agente Grenoble",
        "emoji": "🏙️",
        "persona": "Ancienne gestionnaire locative, méthodique et rigoureuse. Elle vise le rendement : "
                   "étudiants, colocation, proximité tram et campus, et surveille de près le DPE.",
        "zone": "Grenoble et sa première couronne (Saint-Martin-d'Hères, Échirolles, Meylan)",
        "strategie": "rendement locatif : petites surfaces, colocation, biens proches des transports et du campus",
        "communes": GRENOBLE,
        "loyer_m2": (9.0, 19.0),
    },
    "station": {
        "name": "Bastien",
        "role": "Agent stations de ski",
        "emoji": "⛷️",
        "persona": "Moniteur de ski reconverti, il connaît la vie des stations été comme hiver. Il regarde "
                   "l'altitude, l'accès aux pistes, les charges de copropriété et la durée de la saison.",
        "zone": "stations des Alpes : Chamrousse, Alpe d'Huez, Les Deux Alpes, Villard-de-Lans, "
                "Les Belleville (Val Thorens, Les Menuires), Tignes",
        "strategie": "studios et appartements skis aux pieds pour la location saisonnière, stations "
                     "avec un enneigement fiable et une activité l'été",
        "communes": STATIONS,
        "loyer_m2": (10.0, 32.0),
    },
    "renovation": {
        "name": "Inès",
        "role": "Agente biens à rénover",
        "emoji": "🔨",
        "persona": "Marchande de biens dans l'âme, elle chiffre les travaux au mètre carré près. Elle chasse "
                   "les passoires thermiques (DPE F et G), les successions et les biens délaissés à forte décote.",
        "zone": "les trois territoires de l'équipe : Hyères, l'agglomération grenobloise et les stations",
        "strategie": "biens à rénover achetés nettement sous le prix du marché, dont la valeur après "
                     "travaux dépasse largement le coût total (prix + frais + travaux)",
        "communes": {**HYERES, **GRENOBLE, **STATIONS},
        "loyer_m2": (9.0, 30.0),
    },
}


def display(key):
    a = AGENTS[key]
    return f"{a['name']} ({a['role']})"
