# Agents immobiliers IA : 4 agents de recherche en compétition + 1 directrice d'investissement

Même principe que l'[Arène des traders](https://github.com/Lapome12/arene-des-traders), appliqué à l'immobilier.
Les agents **n'achètent rien** : chaque semaine, ils cherchent de vraies annonces en ligne et proposent les biens
les plus intéressants pour investir, avec un **budget maximum de 150 000 € par bien**. Hélène les vérifie et les note.

## L'équipe

| Agent | Rôle | Secteur |
|---|---|---|
| 🧭 **Hélène** | Directrice d'investissement (manager) | Vérifie et note chaque proposition à partir d'avis et de prix au m² trouvés en ligne |
| ☀️ **Marius** | Agent Hyères | Hyères hors presqu'île de Giens : centre, Costebelle, L'Ayguade, Le Port, Les Salins |
| 🏙️ **Chloé** | Agente Grenoble | Grenoble, Saint-Martin-d'Hères, Échirolles, Meylan |
| ⛷️ **Bastien** | Agent stations de ski | Chamrousse, Alpe d'Huez, Les Deux Alpes, Villard-de-Lans, Les Belleville, Tignes |
| 🔨 **Inès** | Agente presqu'île de Giens | L'Almanarre, La Capte, Le Pousset, Giens, La Madrague, La Tour Fondue (Hyères) et Carqueiranne, en priorité biens à rénover ou sous-évalués |

Noms, personnalités, communes et fourchettes de loyers se changent dans `immo/config.py`
(par exemple pour donner à Inès un autre territoire ou ajouter une station).

## Comment ça marche

- **Un tour par semaine.** Chaque agent reçoit les prix réels des ventes de son secteur (médiane au m² par
  commune et type de bien, évolution sur un an, ventes récentes, d'après [DVF](https://www.data.gouv.fr/fr/datasets/demandes-de-valeurs-foncieres-geolocalisees/)),
  le classement et le dernier message d'Hélène. Il cherche des annonces en ligne et présente **5 propositions** :
  1. **la plus chère** : le meilleur bien que le budget permet ;
  2. **la moins chère** : le ticket d'entrée le plus bas qui reste un placement sain ;
  3. **un bon plan** : la meilleure affaire du moment ;
  4. et 5. **deux au choix de l'agent**, selon sa stratégie.
- **Le code vérifie les chiffres** : prix au m² comparé aux ventes réelles du secteur, loyer plafonné à une
  fourchette réaliste par zone, et signalement des annonces sans lien, hors budget ou au prix suspect.
- **Hélène corrige chaque proposition** : elle cherche en ligne les avis sur le quartier ou la station et les prix
  au m² actuels (MeilleursAgents, SeLoger, notaires…), puis donne une note sur 10, un verdict (validée, à revoir,
  rejetée) et la correction à retenir. Elle choisit aussi son coup de cœur de la semaine.
- **Classement** : note moyenne donnée par Hélène, semaine après semaine.

Le budget, les catégories et la fréquence des revues se règlent dans `immo/config.py`.

Tu peux aussi **donner des annonces à étudier** : colle le texte d'une annonce et son lien dans un fichier
`.txt` du dossier `annonces/<agent>/` (`hyeres`, `grenoble`, `station`, `renovation`). L'agent l'étudie en
priorité au tour suivant.

## Installation

```bash
pip install -r requirements.txt
```

Deux façons de faire tourner les agents avec Claude (choix automatique), comme pour l'agent de trading :
- **Ton abonnement Claude, sans clé API** (recommandé) : installe Claude Code
  (`npm install -g @anthropic-ai/claude-code`) et connecte-toi avec `claude`.
  Pour GitHub, crée un jeton avec `claude setup-token`.
- **Une clé API** : `export ANTHROPIC_API_KEY=sk-ant-...` (facturée à l'usage).

## Utilisation

```bash
# 1. Tester gratuitement, sans clé ni Internet : marché et annonces simulés, stratégie simple
python main.py sim --rounds 16 --mock

# 2. En conditions réelles : un tour sur les vrais prix DVF et de vraies annonces, une fois par semaine
python main.py live
```

Chaque partie est sauvegardée dans `runs/<mode>/` :
- `rapport.html` : les 5 propositions de chaque agent (avec liens) et les corrections d'Hélène, sans JavaScript
- `journal.md` : toutes les analyses et décisions, semaine par semaine
- `state.json` : l'état complet (le mode `live` reprend là où il s'était arrêté)

Les prix DVF sont téléchargés depuis data.gouv.fr et gardés dans `cache/dvf/`.

## L'interface graphique

Comme pour l'Arène des traders, le dossier `site/` est un tableau de bord interactif : un tableau par agent
avec ses 5 propositions et les notes et corrections d'Hélène, son coup de cœur, les courbes des notes, ses bilans,
le journal, et une **discussion en direct avec chaque agent** (clique sur sa carte).

- Sur GitHub Pages : publié automatiquement après chaque tour (voir plus bas).
- En local : `python main.py export --out _site` puis `python -m http.server -d _site`, ou `lancer_local.bat`.
- Sur claude.ai, sans GitHub : `python main.py artifact` produit une page unique à publier comme Artifact ;
  la discussion passe alors par ton compte Claude, sans clé API.

## Automatique sur GitHub

Le workflow `.github/workflows/immobilier.yml` joue un tour **chaque lundi matin**, sauvegarde la partie
dans le dépôt et publie le rapport sur GitHub Pages.

1. Settings > Secrets and variables > Actions : ajoute le secret `CLAUDE_CODE_OAUTH_TOKEN`
   (le même jeton que pour l'agent de trading convient), ou `ANTHROPIC_API_KEY`.
2. Facultatif : Settings > Pages, source « GitHub Actions » (Pages sur un dépôt privé demande un compte payant ;
   sinon le rapport reste lisible dans `runs/live/rapport.html`).
3. Onglet Actions > Immobilier > Run workflow pour lancer le premier tour.

## Version 100 % locale (Ollama)

Double-clic sur `lancer_local.bat` (même installation que pour l'Arène des traders, voir son `GUIDE_LOCAL.md`).
Le tableau de bord s'ouvre sur http://localhost:8001 avec un bouton « Lancer un tour » et la discussion avec les agents, et un tour est joué chaque
lundi à 8h tant que la fenêtre reste ouverte (`--jour`, `--heure` pour changer). Un modèle local n'a pas accès
au web : les agents travaillent alors uniquement sur les annonces que tu déposes dans `annonces/`.
`--marche simule` permet de tester sans Internet.

## Coût indicatif

Un tour = 5 appels Claude avec recherche web (4 agents + Hélène). Avec l'abonnement,
ces appels comptent dans tes limites d'usage ; avec une clé API, ils sont facturés (recherche web comprise).
Pour réduire : `AGENT_EFFORT=low`, `IMMO_MODEL=claude-sonnet-5-5`, ou `IMMO_WEB_SEARCH=0`
(les agents ne travaillent alors que sur les annonces déposées).

## Structure

```
main.py               lancement (sim, live, report, export, artifact)
local.py              version locale : tour hebdomadaire + tableau de bord sur localhost (Ollama)
site/                 interface graphique (tableau de bord + discussion avec les agents)
lancer_local.bat      lanceur Windows de la version locale
annonces/             annonces à faire étudier, un dossier par agent
.github/workflows/    tour hebdomadaire automatique + publication GitHub Pages
immo/config.py        agents, communes, budget, catégories, garde-fous, modèle
immo/brains.py        prompts et appels Claude (+ Ollama, + mode --mock)
immo/engine.py        tours, vérification des chiffres, classement, corrections d'Hélène
immo/marche.py        prix réels DVF ou marché simulé
immo/report.py        rapport HTML
```

## Avant de passer à l'acte

Les agents peuvent se tromper avec assurance : une annonce peut être déjà vendue, mal décrite ou cacher
un problème (copropriété en difficulté, zone inondable, charges énormes en station). Sers-toi d'eux pour
**repérer et trier**, puis vérifie chaque dossier toi-même (visite, diagnostics, PV d'AG, avis d'un notaire ou
d'un artisan) avant toute offre.
