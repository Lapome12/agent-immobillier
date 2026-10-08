"""Les « cerveaux » des agents : Claude (API ou abonnement via Claude Code), un modèle local
(Ollama), ou une stratégie simple hors ligne (mode --mock) pour tester sans clé ni coût."""
import json
from typing import List

from pydantic import BaseModel, Field

from . import config


# ---------- Formats de réponse imposés aux agents ----------

class Proposition(BaseModel):
    categorie: str = Field(description="« chere », « pas_chere », « bon_plan » ou « choix_agent »")
    titre: str = Field(description="Ex. : « T2 45 m² rénové, quartier Europole »")
    url: str = Field(description="Lien de l'annonce (obligatoire)")
    commune_insee: str = Field(description="Code INSEE de la commune, parmi ceux de ta zone")
    quartier: str = Field(description="Quartier ou secteur précis (rue, lieu-dit, front de neige…)")
    type_bien: str = Field(description="« appartement » ou « maison »")
    surface_m2: float
    prix: float = Field(description="Prix demandé en euros, frais d'agence inclus")
    travaux_estimes: float = Field(description="Budget travaux estimé en euros (0 si aucun)")
    loyer_mensuel_estime: float = Field(description="Loyer mensuel hors charges réaliste (après travaux), en euros")
    dpe: str = Field(description="Classe DPE (A à G) ou « inconnu »")
    pourquoi: str = Field(description="Pourquoi ce bien dans cette catégorie, en 1 ou 2 phrases")
    risques: str


class AgentDecision(BaseModel):
    analyse_marche: str = Field(description="Lecture du marché de ta zone en 2 à 4 phrases")
    propositions: List[Proposition] = Field(description="Exactement 5 propositions : chere, pas_chere, bon_plan, choix_agent, choix_agent")
    note_pour_plus_tard: str = Field(description="Ce que tu veux te rappeler au prochain tour")


class Correction(BaseModel):
    agent: str = Field(description="Identifiant de l'agent")
    numero: int = Field(description="Numéro de la proposition (0 à 4)")
    note: float = Field(description="Note de 0 à 10")
    verdict: str = Field(description="« validée », « à revoir » ou « rejetée »")
    prix_m2_constate: float = Field(description="Prix au m² réel du quartier selon tes sources (0 si inconnu)")
    source_prix: str = Field(description="D'où vient ce prix au m² (site, date)")
    avis_quartier: str = Field(description="Ce que disent les avis en ligne sur le quartier ou la station (1 à 2 phrases)")
    correction: str = Field(description="Ce que l'agent a mal évalué et ce qu'il faut retenir (1 à 2 phrases)")


class AgentFeedback(BaseModel):
    agent: str
    feedback: str = Field(description="Message court et utile à l'agent pour le prochain tour")


class ManagerDecision(BaseModel):
    commentary: str = Field(description="Bilan de la semaine en 3 à 5 phrases")
    coup_de_coeur: str = Field(description="La meilleure proposition de la semaine, et pourquoi")
    corrections: List[Correction] = Field(description="Une correction par proposition, pour toutes les propositions reçues")
    feedbacks: List[AgentFeedback]


# ---------- Cerveau Claude ----------

AGENT_SYSTEM = """Tu es {name}, un agent de recherche immobilière IA spécialisé sur {zone}.
Ta personnalité : {persona}
Ta stratégie : {strategie}.
Tu ne fais aucun achat : ton travail est de repérer les meilleurs biens en vente aujourd'hui, dans un but
d'investissement, pour Eliott. Ton budget maximum est de {budget} € par bien (prix frais d'agence inclus).
Tu es en compétition avec les autres agents IA de l'équipe sur d'autres secteurs. Hélène, la directrice d'investissement,
vérifie et note chacune de tes propositions (avis sur le quartier, vrais prix au m²) : des propositions solides et
honnêtes te font monter au classement.

À chaque tour (une semaine), tu reçois les prix de vente réels de ta zone (DVF) et le classement.
Tu présentes exactement 5 propositions, dans cet ordre :
1. chere : {chere}
2. pas_chere : {pas_chere}
3. bon_plan : {bon_plan}
4. et 5. choix_agent : {choix_agent}
{source}
Communes autorisées (code INSEE : nom) : {communes}.
Le code vérifie tes chiffres : il compare le prix au m² à la médiane DVF du secteur, plafonne les loyers irréalistes
et signale les annonces sans lien, hors budget ou au prix suspect.
Sois honnête sur les risques (copropriété, charges, DPE, inondation, saisonnalité)."""

SOURCE_WEB = ("Cherche des annonces en ligne actuellement en vente (leboncoin, seloger, bienici, pap, "
              "logic-immo, sites d'agences, ventes aux enchères notariales…) et vérifie chaque lien. "
              "N'invente jamais une annonce : si tu ne trouves pas 5 biens corrects, présente-en moins.")
SOURCE_FOURNIE = ("Tu travailles uniquement à partir des annonces fournies dans le message. "
                  "N'invente jamais une annonce : sans annonce fournie, ne présente aucune proposition.")

MANAGER_SYSTEM = """Tu es {name}, directrice d'investissement d'une équipe de 5 agents de recherche immobilière IA
en compétition, chacun sur un secteur : {team}. Ils ne font aucun achat : ils proposent chacun 5 biens en vente
(budget max {budget} € par bien) dans un but d'investissement pour Eliott.
Ta personnalité : {persona}
À chaque tour, tu reçois toutes les propositions avec les prix réels des ventes (DVF) calculés par le code.
{source}
Pour chaque proposition, donne une note sur 10, un verdict (validée, à revoir, rejetée), le prix au m² réel du
quartier selon tes sources, ce que disent les avis sur le quartier ou la station, et la correction à apporter
(lieu mal choisi ou hors de la zone de l'agent, prix au m² surestimé, loyer irréaliste, risque oublié…). Sois exigeante mais juste : récompense
les dossiers solides et honnêtes, pénalise les propositions surpayées, mal situées ou mal documentées.
Termine par un bilan, ton coup de cœur et un retour court à chaque agent."""

MANAGER_WEB = ("Vérifie avec des recherches en ligne : avis d'habitants sur les quartiers et les stations (sites d'avis "
               "de quartiers, forums, presse locale), prix au m² actuels par quartier (MeilleursAgents, SeLoger, "
               "Efficity, notaires), et si une annonce semble déjà vendue ou douteuse. Cite tes sources.")
MANAGER_SANS_WEB = "Tu n'as pas accès au web : appuie-toi sur les prix DVF fournis et sur tes connaissances."


def agent_system(key, web):
    a = config.AGENTS[key]
    communes = ", ".join(f"{c} : {n}" for c, n in a["communes"].items())
    budget = f"{config.BUDGET_MAX:,.0f}".replace(",", " ")
    return AGENT_SYSTEM.format(name=a["name"], zone=a["zone"], persona=a["persona"], strategie=a["strategie"],
                               communes=communes, source=SOURCE_WEB if web else SOURCE_FOURNIE, budget=budget,
                               **config.CATEGORIES)


def manager_system(web):
    team = "; ".join(f"{a['name']} ({a['role']}, identifiant {k}, zone : {a['zone']})" for k, a in config.AGENTS.items())
    budget = f"{config.BUDGET_MAX:,.0f}".replace(",", " ")
    return MANAGER_SYSTEM.format(name=config.MANAGER["name"], persona=config.MANAGER["persona"], team=team,
                                 budget=budget, source=MANAGER_WEB if web else MANAGER_SANS_WEB)


class ClaudeBrain:
    web = config.WEB_SEARCH

    def __init__(self):
        import anthropic

        self.client = anthropic.Anthropic()

    def _ask(self, system, prompt, schema, effort, web=False):
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": config.MAX_RECHERCHES * 2}] if web else []
        messages = [{"role": "user", "content": prompt}]
        for _ in range(5):  # une longue recherche web peut demander de relancer la réponse (pause_turn)
            response = self.client.beta.messages.parse(
                model=config.MODEL,
                max_tokens=32000,
                system=system,
                messages=messages,
                tools=tools,
                output_format=schema,
                output_config={"effort": effort},
                # Si la requête est refusée par un filtre de sécurité, l'API bascule
                # automatiquement sur un autre modèle au lieu d'échouer.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            if response.stop_reason != "pause_turn":
                break
            messages = [messages[0], {"role": "assistant", "content": response.content}]
        if response.stop_reason == "refusal":
            raise RuntimeError("Le modèle a refusé de répondre")
        if response.parsed_output is not None:
            return response.parsed_output
        texts = [b.text for b in response.content if b.type == "text"]
        try:  # avec la recherche web, le JSON est dans le dernier bloc de texte
            return schema.model_validate_json(texts[-1])
        except (IndexError, ValueError):
            raise RuntimeError(f"Réponse illisible (stop_reason={response.stop_reason})")

    def agent(self, key, prompt):
        return self._ask(agent_system(key, self.web), prompt, AgentDecision, config.AGENT_EFFORT, web=self.web)

    def manager(self, prompt, context):
        return self._ask(manager_system(self.web), prompt, ManagerDecision, config.MANAGER_EFFORT, web=self.web)


# ---------- Cerveau Claude Code (abonnement Claude, sans clé API) ----------

class ClaudeCodeBrain(ClaudeBrain):
    """Passe par la ligne de commande Claude Code (`claude -p`), authentifiée avec
    l'abonnement Claude (jeton CLAUDE_CODE_OAUTH_TOKEN créé par `claude setup-token`)."""

    def __init__(self):
        import shutil

        self.cli = shutil.which("claude")
        if not self.cli:
            raise RuntimeError("Claude Code introuvable : npm install -g @anthropic-ai/claude-code")

    def _ask(self, system, prompt, schema, effort, web=False):
        import os
        import subprocess

        tools = "WebSearch,WebFetch" if web else ""
        cmd = [self.cli, "-p", "--output-format", "json", "--tools", tools, "--no-session-persistence",
               "--system-prompt", system, "--json-schema", json.dumps(schema.model_json_schema()),
               "--model", config.MODEL, "--effort", effort]
        if web:
            cmd += ["--allowedTools", tools]
        env = dict(os.environ)
        if env.get("CLAUDE_CODE_OAUTH_TOKEN"):  # un copier-coller ajoute souvent espaces ou retours à la ligne
            env["CLAUDE_CODE_OAUTH_TOKEN"] = "".join(env["CLAUDE_CODE_OAUTH_TOKEN"].split())
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=1200, env=env)
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Claude Code a échoué : {(proc.stderr or proc.stdout)[-300:]}")
        if out.get("is_error") or out.get("structured_output") is None:
            raise RuntimeError(f"Claude Code a échoué : {str(out.get('result'))[:300]}")
        return schema.model_validate(out["structured_output"])


# ---------- Cerveau local (Ollama, 100 % sur ton ordinateur) ----------

class OllamaBrain(ClaudeBrain):
    """Fait tourner Hélène et les 5 agents avec un modèle installé localement via Ollama.
    Pas de recherche web : les agents travaillent sur les annonces déposées dans annonces/."""

    web = False

    def __init__(self, model=None, url=None):
        self.model = model or config.OLLAMA_MODEL
        self.url = (url or config.OLLAMA_URL).rstrip("/")

    def _post(self, path, payload, timeout=900):
        import urllib.request

        req = urllib.request.Request(self.url + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except OSError as e:
            raise RuntimeError(f"Ollama injoignable sur {self.url} ({e}). Lance l'application Ollama.") from e

    def installed_models(self):
        import urllib.request

        with urllib.request.urlopen(self.url + "/api/tags", timeout=5) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]

    def chat(self, system, messages, schema=None):
        payload = {"model": self.model, "stream": False, "think": False,
                   "messages": [{"role": "system", "content": system}] + messages,
                   "options": {"temperature": 0.4, "num_ctx": 16384}}
        if schema is not None:
            payload["format"] = schema.model_json_schema()  # Ollama contraint la réponse à ce schéma
        out = self._post("/api/chat", payload)
        if "error" in out:
            raise RuntimeError(f"Ollama : {out['error']}")
        return out["message"]["content"]

    def _ask(self, system, prompt, schema, effort, web=False):
        from pydantic import ValidationError

        system += "\nRéponds uniquement avec un objet JSON conforme au schéma demandé, en français."
        last = None
        for _ in range(2):  # les petits modèles se trompent parfois : on retente une fois
            text = self.chat(system, [{"role": "user", "content": prompt}], schema)
            try:
                return schema.model_validate_json(text)
            except ValidationError as e:
                last = e
        raise RuntimeError(f"Réponse du modèle local illisible : {str(last)[:200]}")


def make_brain(kind="auto"):
    """auto : clé API si ANTHROPIC_API_KEY existe, sinon abonnement via Claude Code."""
    import os

    if kind == "mock":
        return MockBrain()
    if kind == "local":
        return OllamaBrain()
    if kind == "api" or (kind == "auto" and os.environ.get("ANTHROPIC_API_KEY")):
        return ClaudeBrain()
    return ClaudeCodeBrain()


# ---------- Cerveau hors ligne (tests) ----------

class MockBrain:
    """Stratégie déterministe simple sur les annonces simulées : la plus chère et la moins chère
    du budget, la plus décotée en bon plan, puis les deux meilleurs rendements. Hélène note
    selon l'écart au marché."""

    web = False

    def agent(self, key, prompt):
        data = json.loads(prompt.split("DONNÉES_JSON:", 1)[1])
        meds = {c: s["mediane_m2"] for c, s in data["marche"].items()}
        ann = [a for a in data.get("annonces_simulees", []) if a["prix"] <= config.BUDGET_MAX]
        if not ann:
            return AgentDecision(analyse_marche="Rien dans le budget cette semaine (mode test).", propositions=[], note_pour_plus_tard="")
        decote = lambda a: 1 - a["prix"] / (a["surface_m2"] * meds[a["commune_insee"]])
        rdt = lambda a: a["loyer_mensuel_estime"] * 12 / (a["prix"] + a["travaux_estimes"])
        choix = [("chere", max(ann, key=lambda a: a["prix"])), ("pas_chere", min(ann, key=lambda a: a["prix"])),
                 ("bon_plan", max(ann, key=decote))]
        reste = sorted((a for a in ann if all(a is not c for _, c in choix)), key=rdt, reverse=True)
        choix += [("choix_agent", a) for a in reste[:2]]
        props = [Proposition(categorie=cat, quartier="centre", pourquoi=f"décote {decote(a):+.0%}, rendement brut {rdt(a):.1%}",
                             risques="mode test", **a) for cat, a in choix]
        return AgentDecision(analyse_marche="Sélection automatique (mode test).", propositions=props, note_pour_plus_tard="")

    def manager(self, prompt, context):
        data = json.loads(prompt.split("DONNÉES_JSON:", 1)[1])
        corr = []
        for k, props in data["propositions"].items():
            for i, p in enumerate(props):
                ecart = p.get("ecart_marche") or 0
                note = max(0.0, min(10.0, round(6 - ecart * 10, 1))) if p["valide"] else 1.0
                corr.append(Correction(agent=k, numero=i, note=note,
                                       verdict="validée" if note >= 6 else "à revoir" if note >= 3 else "rejetée",
                                       prix_m2_constate=p.get("mediane_m2") or 0, source_prix="DVF (mode test)",
                                       avis_quartier="(mode test)", correction="(mode test)"))
        return ManagerDecision(commentary="Notes calculées sur l'écart au marché (mode test).", coup_de_coeur="(mode test)",
                               corrections=corr, feedbacks=[AgentFeedback(agent=k, feedback="Continue.") for k in data["propositions"]])
