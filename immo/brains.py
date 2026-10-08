"""Les « cerveaux » des agents : Claude (API ou abonnement via Claude Code), un modèle local
(Ollama), ou une stratégie simple hors ligne (mode --mock) pour tester sans clé ni coût."""
import json
import math
from typing import List

from pydantic import BaseModel, Field

from . import config


# ---------- Formats de réponse imposés aux agents ----------

class Opportunite(BaseModel):
    titre: str = Field(description="Ex. : « T2 45 m² rénové, quartier Europole »")
    url: str = Field(description="Lien de l'annonce (obligatoire, sinon l'opportunité ne compte pas)")
    commune_insee: str = Field(description="Code INSEE de la commune, parmi ceux de ta zone")
    type_bien: str = Field(description="« appartement » ou « maison »")
    surface_m2: float
    prix: float = Field(description="Prix demandé en euros, frais d'agence inclus")
    travaux_estimes: float = Field(description="Budget travaux estimé en euros (0 si aucun)")
    loyer_mensuel_estime: float = Field(description="Loyer mensuel hors charges réaliste après travaux, en euros")
    dpe: str = Field(description="Classe DPE (A à G) ou « inconnu »")
    points_forts: str
    risques: str


class AgentDecision(BaseModel):
    analyse_marche: str = Field(description="Lecture du marché de ta zone en 2 à 4 phrases")
    opportunites: List[Opportunite] = Field(description="Tes 3 meilleures opportunités du moment, au plus")
    achat: int = Field(description="Numéro (0, 1 ou 2) de l'opportunité que tu achètes ce tour-ci, ou -1 pour ne rien acheter")
    justification_achat: str
    note_pour_plus_tard: str = Field(description="Ce que tu veux te rappeler au prochain tour")


class AgentBudget(BaseModel):
    agent: str
    weight: float = Field(description="Part de l'enveloppe totale confiée à cet agent, entre 0.10 et 0.40")
    feedback: str = Field(description="Message court à l'agent")


class ManagerDecision(BaseModel):
    commentary: str = Field(description="Bilan de la période et justification des choix")
    coup_de_coeur: str = Field(description="La meilleure opportunité vue sur la période, et pourquoi")
    budgets: List[AgentBudget]


# ---------- Cerveau Claude ----------

AGENT_SYSTEM = """Tu es {name}, un agent d'investissement immobilier IA spécialisé sur {zone}.
Ta personnalité : {persona}
Ta stratégie : {strategie}.
Tu gères une enveloppe fictive (tout est simulé, aucun achat réel) et tu es en compétition avec
3 autres agents IA spécialisés sur d'autres secteurs. Une directrice d'investissement IA réalloue
régulièrement l'enveloppe vers ceux qui trouvent les meilleures affaires : un mauvais achat te coûtera ton budget.

À chaque tour (une semaine), tu reçois les prix de vente réels de ta zone (DVF), ton portefeuille et le classement.
Tu présentes au plus 3 opportunités concrètes et actuelles, chacune avec le lien de l'annonce.
{source}
Communes autorisées (code INSEE : nom) : {communes}.
Tu peux en acheter une seule par tour, ou aucune : attendre une meilleure affaire est un choix valable.
Le code vérifie tes chiffres : il compare le prix au m² à la médiane DVF du secteur, plafonne les loyers
irréalistes et rejette les annonces sans lien ou au prix suspect. Le coût total d'un achat = prix + 8 % de frais
de notaire + travaux. La valeur retenue ensuite = surface × prix médian du secteur, moins 5 % de frais de revente.
Sois honnête sur les risques (copropriété, charges, DPE, inondation, saisonnalité)."""

SOURCE_WEB = ("Cherche des annonces en ligne actuellement en vente (leboncoin, seloger, bienici, pap, "
              "logic-immo, sites d'agences, ventes aux enchères notariales…) et vérifie chaque lien. "
              "N'invente jamais une annonce : si tu ne trouves rien de bon, présente moins d'opportunités.")
SOURCE_FOURNIE = ("Tu travailles uniquement à partir des annonces fournies dans le message. "
                  "N'invente jamais une annonce : sans annonce fournie, ne présente aucune opportunité.")

MANAGER_SYSTEM = """Tu es {name}, directrice d'investissement d'une équipe de 4 agents immobiliers IA en compétition,
chacun sur un secteur : {team}. Tout est fictif.
Ta personnalité : {persona}
Ton objectif est de maximiser la création de valeur de l'enveloppe entière (plus-values latentes + loyers nets), sans prendre de risques inconsidérés.
À chaque revue, tu reçois le classement, les achats et les opportunités repérées, puis tu décides quelle part de
l'enveloppe confier à chaque agent (entre 0.10 et 0.40 chacun, somme = 1). Récompense les dossiers solides et
réguliers, pas un coup de chance ; pénalise les achats surpayés ou mal documentés. Donne à chaque agent un retour court et utile."""


def agent_system(key, web):
    a = config.AGENTS[key]
    communes = ", ".join(f"{c} : {n}" for c, n in a["communes"].items())
    return AGENT_SYSTEM.format(name=a["name"], zone=a["zone"], persona=a["persona"], strategie=a["strategie"],
                               communes=communes, source=SOURCE_WEB if web else SOURCE_FOURNIE)


def manager_system():
    team = ", ".join(f"{a['name']} ({a['role']}, identifiant {k})" for k, a in config.AGENTS.items())
    return MANAGER_SYSTEM.format(name=config.MANAGER["name"], persona=config.MANAGER["persona"], team=team)


class ClaudeBrain:
    web = config.WEB_SEARCH

    def __init__(self):
        import anthropic

        self.client = anthropic.Anthropic()

    def _ask(self, system, prompt, schema, effort, web=False):
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": config.MAX_RECHERCHES}] if web else []
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
        return self._ask(manager_system(), prompt, ManagerDecision, config.MANAGER_EFFORT)


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
    """Fait tourner Hélène et les 4 agents avec un modèle installé localement via Ollama.
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
    """Stratégie déterministe simple : garde les annonces simulées les moins chères par rapport
    au marché et achète la meilleure si la décote dépasse un seuil propre à chaque agent."""

    web = False
    SEUIL = {"hyeres": 0.10, "grenoble": 0.05, "station": 0.15, "renovation": 0.20}

    def agent(self, key, prompt):
        data = json.loads(prompt.split("DONNÉES_JSON:", 1)[1])
        meds = {c: s["mediane_m2"] for c, s in data["marche"].items()}
        cands = []
        for a in data.get("annonces_simulees", []):
            cout = a["prix"] * (1 + config.FRAIS_NOTAIRE) + a["travaux_estimes"]
            decote = 1 - cout / (a["surface_m2"] * meds[a["commune_insee"]])
            cands.append((decote, a))
        cands.sort(key=lambda x: x[0], reverse=True)
        top = [c for c in cands if c[0] > -0.1][:config.MAX_OPPORTUNITES]
        opps = [Opportunite(**a, points_forts=f"décote estimée {d:+.0%}", risques="mode test") for d, a in top]
        achat = 0 if top and top[0][0] > self.SEUIL[key] and top[0][0] < 0.55 else -1
        return AgentDecision(analyse_marche="Sélection par décote (mode test).", opportunites=opps, achat=achat,
                             justification_achat="meilleure décote" if achat == 0 else "rien d'assez décoté",
                             note_pour_plus_tard="")

    def manager(self, prompt, context):
        scores = {k: v["rendement_periode"] for k, v in context.items()}
        exp = {k: math.exp(20 * s) for k, s in scores.items()}
        tot = sum(exp.values())
        return ManagerDecision(
            commentary="Allocation proportionnelle à la performance récente (mode test).",
            coup_de_coeur="(mode test)",
            budgets=[AgentBudget(agent=k, weight=exp[k] / tot, feedback="Continue.") for k in context],
        )
