# Agents immobiliers IA : 4 agents en compétition + 1 directrice d'investissement

Même principe que l'[Arène des traders](https://github.com/Lapome12/arene-des-traders), appliqué à l'immobilier.
Tout est **fictif** : les agents cherchent de vraies annonces et les comparent aux vrais prix de vente,
mais les achats et les loyers sont simulés. Aucune offre n'est envoyée à personne.

## L'équipe

| Agent | Rôle | Secteur |
|---|---|---|
| 🧭 **Hélène** | Directrice d'investissement (manager) | Répartit l'enveloppe entre les 4 agents, sanctionne les achats surpayés |
| ☀️ **Marius** | Agent Hyères | Hyères : centre, Costebelle, L'Ayguade, Le Port, Giens |
| 🏙️ **Chloé** | Agente Grenoble | Grenoble, Saint-Martin-d'Hères, Échirolles, Meylan |
| ⛷️ **Bastien** | Agent stations de ski | Chamrousse, Alpe d'Huez, Les Deux Alpes, Villard-de-Lans, Les Belleville, Tignes |
| 🔨 **Inès** | Agente biens à rénover | Biens à forte décote (DPE F/G, travaux) sur les trois territoires |

Noms, personnalités, communes et fourchettes de loyers se changent dans `immo/config.py`
(par exemple pour donner à Inès un autre territoire ou ajouter une station).

## Comment ça marche

- **Un tour par semaine.** Chaque agent reçoit les prix réels de son secteur (médiane au m² par
  commune et type de bien, évolution sur un an, ventes récentes, d'après [DVF](https://www.data.gouv.fr/fr/datasets/demandes-de-valeurs-foncieres-geolocalisees/)),
  son portefeuille, le classement et le dernier message d'Hélène. Il **cherche lui-même des annonces en
  ligne** (recherche web de Claude), présente ses 3 meilleures opportunités avec leur lien, et peut en
  acheter une (fictivement) ou attendre.
- **Le code vérifie les chiffres**, quoi que dise l'agent : prix au m² comparé à la médiane DVF du secteur,
  loyer plafonné à une fourchette réaliste par zone (et à 15 % de rendement brut), annonce sans lien ou à
  moins de 40 % du prix du marché rejetée, 60 % max du compte dans un seul bien, un achat max par tour.
- **Score d'une opportunité** = marge (valeur au prix médian du secteur moins 5 % de frais de revente,
  rapportée au coût total prix + 8 % de notaire + travaux) et rendement locatif net (loyer × 12 × 75 % / coût total).
- **Performance d'un agent** = plus-values latentes de ses biens + loyers nets encaissés (pas de loyer pendant
  les travaux). Les biens sont revalorisés à chaque mise à jour des prix DVF.
- **Hélène fait une revue toutes les 4 semaines** : elle regarde performances, achats et opportunités, puis
  décide quelle part de l'enveloppe confier à chacun (entre 10 % et 40 %) et choisit son coup de cœur.
  Les biens ne se revendent pas : seule la trésorerie passe d'un agent à l'autre.

Enveloppe de départ : 2 000 000 € fictifs, 500 000 € par agent. Tout se règle dans `immo/config.py`.

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

# 2. Marché simulé avec les vrais agents Claude
python main.py sim --rounds 8

# 3. En conditions réelles : un tour sur les vrais prix DVF et de vraies annonces, une fois par semaine
python main.py live
```

Chaque partie est sauvegardée dans `runs/<mode>/` :
- `rapport.html` : meilleures opportunités (avec liens), classement, courbes, portefeuilles, décisions d'Hélène
- `journal.md` : toutes les analyses et décisions, semaine par semaine
- `state.json` : l'état complet (le mode `live` reprend là où il s'était arrêté)

Les prix DVF sont téléchargés depuis data.gouv.fr et gardés dans `cache/dvf/`.

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
Le rapport s'ouvre sur http://localhost:8001 avec un bouton « Lancer un tour », et un tour est joué chaque
lundi à 8h tant que la fenêtre reste ouverte (`--jour`, `--heure` pour changer). Un modèle local n'a pas accès
au web : les agents travaillent alors uniquement sur les annonces que tu déposes dans `annonces/`.
`--marche simule` permet de tester sans Internet.

## Coût indicatif

Un tour = 4 appels Claude avec recherche web (+1 pour Hélène toutes les 4 semaines). Avec l'abonnement,
ces appels comptent dans tes limites d'usage ; avec une clé API, ils sont facturés (recherche web comprise).
Pour réduire : `AGENT_EFFORT=low`, `IMMO_MODEL=claude-sonnet-5-5`, ou `IMMO_WEB_SEARCH=0`
(les agents ne travaillent alors que sur les annonces déposées).

## Structure

```
main.py               lancement (sim, live, report, export)
local.py              version locale : tour hebdomadaire + rapport sur localhost (Ollama)
lancer_local.bat      lanceur Windows de la version locale
annonces/             annonces à faire étudier, un dossier par agent
.github/workflows/    tour hebdomadaire automatique + publication GitHub Pages
immo/config.py        agents, communes, enveloppe, garde-fous, modèle
immo/brains.py        prompts et appels Claude (+ Ollama, + mode --mock)
immo/engine.py        tours, vérification des chiffres, achats, classement, revues d'Hélène
immo/marche.py        prix réels DVF ou marché simulé
immo/report.py        rapport HTML
```

## Avant de passer à l'acte

Les agents peuvent se tromper avec assurance : une annonce peut être déjà vendue, mal décrite ou cacher
un problème (copropriété en difficulté, zone inondable, charges énormes en station). La médiane DVF d'une
commune ne dit rien de l'état d'un bien précis. Sers-toi des agents pour **repérer et trier**, puis vérifie
chaque dossier toi-même (visite, diagnostics, PV d'AG, avis d'un notaire ou d'un artisan) avant toute offre.
