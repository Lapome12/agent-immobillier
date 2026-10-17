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
    "giens": {
        "name": "Lou",
        "role": "Agente presqu'île de Giens, Mont des Oiseaux et Carqueiranne",
        "emoji": "🏝️",
        "persona": "Née à La Capte, elle connaît chaque lieu-dit de la presqu'île, de L'Almanarre à La Tour Fondue, "
                   "en passant par le Mont des Oiseaux, jusqu'à Carqueiranne. Elle sait ce qui est inondable, ce qui se loue l'été et ce qui se loue toute l'année.",
        "zone": "la presqu'île de Giens à Hyères (Var) : L'Almanarre, Le Port, Les Pesquiers, La Capte, Le Pousset, "
                "Giens village, La Madrague, La Tour Fondue, le Mont des Oiseaux, ainsi que la commune voisine de Carqueiranne. "
                "À Hyères, uniquement ces secteurs (pas le centre-ville ni Costebelle)",
        "strategie": "les biens avec le meilleur potentiel d'investissement de la presqu'île, du Mont des Oiseaux et de Carqueiranne, "
                     "en location saisonnière ou à l'année ; indique toujours le lieu-dit précis dans le champ quartier",
        "communes": {**HYERES, "83034": "Carqueiranne"},
        "loyer_m2": (12.0, 28.0),
    },
    "sniper": {
        "name": "Gaspard",
        "role": "Sniper montagne à rénover",
        "emoji": "🎯",
        "persona": "Ancien charpentier savoyard devenu chasseur de biens, il ne tire qu'à coup sûr : une vieille grange, "
                   "un chalet d'alpage ou une maison de village à retaper, au pied d'une grande station d'altitude. "
                   "Il connaît les règles d'urbanisme de montagne (changement de destination, PLU, loi Montagne).",
        "zone": "la moyenne et haute montagne, dans ou à proximité immédiate des stations de ski réputées et "
                "situées en altitude (domaines au-dessus de 1 800 m environ) : Tarentaise, Haute-Maurienne, Oisans, "
                "Briançonnais, Queyras et vallée de Chamonix",
        "strategie": "uniquement des biens À RÉNOVER : vieilles granges, fermes, maisons de village, chalets ou "
                     "appartements anciens nécessitant de vrais travaux, achetés sous le prix du marché avec un fort "
                     "potentiel après rénovation (location saisonnière ou revente). Aucun bien en bon état. Chiffre les "
                     "travaux, précise l'altitude, la distance aux pistes, et vérifie qu'une grange est bien habitable "
                     "ou transformable (risque de changement de destination refusé)",
        "communes": {
            "73054": "Bourg-Saint-Maurice (Les Arcs)", "73285": "Séez", "73323": "Villaroger",
            "73232": "Sainte-Foy-Tarentaise", "73304": "Val-d'Isère", "73296": "Tignes",
            "73197": "Peisey-Nancroix", "73142": "Landry", "73150": "La Plagne Tarentaise",
            "73227": "Courchevel", "73015": "Les Allues (Méribel)", "73257": "Les Belleville (Val Thorens, Les Menuires)",
            "73290": "Val-Cenis", "73047": "Bonneval-sur-Arc", "73306": "Valloire",
            "38191": "Huez (Alpe d'Huez)", "38253": "Les Deux Alpes", "05063": "La Grave", "05181": "Villar-d'Arêne",
            "05023": "Briançon", "05133": "Saint-Chaffrey", "05161": "La Salle-les-Alpes",
            "05079": "Le Monêtier-les-Bains", "05085": "Montgenèvre", "05093": "Névache",
            "05177": "Vars", "05157": "Saint-Véran", "05077": "Molines-en-Queyras",
            "74056": "Chamonix-Mont-Blanc",
        },
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
