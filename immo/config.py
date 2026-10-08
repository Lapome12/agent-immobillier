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

BUDGET_MAX = 150_000.0         # prix maximum d'une proposition (frais d'agence inclus), pour chaque agent
FRAIS_NOTAIRE = 0.08           # frais d'acquisition dans l'ancien
FRAIS_REVENTE = 0.05           # décote appliquée à la valeur de marché (frais d'agence à la revente)
CHARGES_LOCATIVES = 0.25       # part des loyers perdue en charges, taxe foncière, vacance, gestion

# Les 5 propositions demandées à chaque agent, à chaque tour
CATEGORIES = {
    "chere": "La plus chère : le meilleur bien que le budget permet (emplacement, qualité)",
    "pas_chere": "La moins chère : le ticket d'entrée le plus bas qui reste un placement sain",
    "bon_plan": "Le bon plan : la meilleure affaire du moment (prix nettement sous le marché, potentiel)",
    "choix_agent": "Au choix de l'agent : ce qu'il juge le plus intéressant, selon sa stratégie",
}
ORDRE = ["chere", "pas_chere", "bon_plan", "choix_agent", "choix_agent"]

# Règles appliquées par le code, quoi que décident les agents
PRIX_SUSPECT = 0.4             # prix au m² < 40 % de la médiane du secteur : annonce signalée (erreur, viager, arnaque)
RENDEMENT_BRUT_MAX = 0.15      # loyer annoncé plafonné à 15 % de rendement brut
MANAGER_EVERY = int(os.environ.get("MANAGER_EVERY", 1))  # Hélène corrige les propositions tous les N tours (1 tour = 1 semaine)

MANAGER = {
    "name": "Hélène",
    "role": "Directrice d'investissement",
    "emoji": "🧭",
    "persona": "Directrice d'investissement immobilier exigeante et juste. Elle vérifie chaque proposition "
               "(avis sur le quartier, vrais prix au m², pièges) et corrige franchement ses agents.",
}

HYERES = {"83069": "Hyères"}
GRENOBLE = {"38185": "Grenoble", "38421": "Saint-Martin-d'Hères", "38151": "Échirolles", "38229": "Meylan"}
STATIONS = {"38567": "Chamrousse", "38191": "Huez (Alpe d'Huez)", "38253": "Les Deux Alpes",
            "38548": "Villard-de-Lans", "73257": "Les Belleville (Val Thorens, Les Menuires)", "73296": "Tignes"}

AGENTS = {
    "hyeres": {
        "name": "Marius",
        "role": "Agent presqu'île de Giens et Carqueiranne",
        "emoji": "☀️",
        "persona": "Varois pur jus, il connaît chaque lieu-dit de la presqu'île de Giens, de L'Almanarre à La Tour "
                   "Fondue, jusqu'à Carqueiranne. Il arbitre entre location à l'année et saisonnière et se méfie des "
                   "prix gonflés en bord de mer.",
        "zone": "la presqu'île de Giens à Hyères (Var) : L'Almanarre, Le Port, Les Pesquiers, La Capte, Le Pousset, "
                "Giens village, La Madrague, La Tour Fondue, ainsi que la commune voisine de Carqueiranne. À Hyères, "
                "uniquement ces secteurs (pas le centre-ville ni Costebelle)",
        "strategie": "appartements et maisons avec un bon rapport prix / emplacement, rentables en location "
                     "à l'année ou saisonnière ; indique toujours le lieu-dit précis dans le champ quartier",
        "communes": {**HYERES, "83034": "Carqueiranne"},
        "loyer_m2": (12.0, 28.0),   # fourchette plausible de loyer mensuel au m² (€)
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
