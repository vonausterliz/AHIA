"""Catalogo normalizzato dei modelli disponibili presso i provider supportati."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any
from urllib import error, request


class ErroreCatalogo(RuntimeError):
    """Errore leggibile senza includere corpi di risposta o segreti."""


@dataclass(frozen=True)
class ModelloCatalogo:
    id: str
    nome: str
    provider: str
    input: tuple[str, ...] = ("testo",)
    capacita: tuple[str, ...] = ()
    contesto: int | None = None
    output_massimo: int | None = None
    costo_input_milione: float | None = None
    costo_output_milione: float | None = None
    creato: str | None = None
    scadenza: str | None = None
    descrizione: str = ""
    installato: bool = True
    alias_variabile: bool = False
    canonical_slug: str | None = None

    def serializza(self) -> dict[str, Any]:
        dato = asdict(self)
        dato["input"] = list(self.input)
        dato["capacita"] = list(self.capacita)
        return dato

    @classmethod
    def deserializza(cls, dato: dict[str, Any]) -> "ModelloCatalogo":
        pulito = dict(dato)
        pulito["input"] = tuple(pulito.get("input", ("testo",)))
        pulito["capacita"] = tuple(pulito.get("capacita", ()))
        return cls(**pulito)


def _json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    metodo: str = "GET",
    corpo: dict[str, Any] | None = None,
    timeout: float = 12,
) -> dict[str, Any]:
    dati = None if corpo is None else json.dumps(corpo).encode("utf-8")
    intestazioni = {"Accept": "application/json", **(headers or {})}
    if dati is not None:
        intestazioni["Content-Type"] = "application/json"
    richiesta = request.Request(url, data=dati, headers=intestazioni, method=metodo)
    try:
        with request.urlopen(richiesta, timeout=timeout) as risposta:
            return json.loads(risposta.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise ErroreCatalogo(f"Il provider ha risposto con HTTP {exc.code}.") from exc
    except (error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise ErroreCatalogo("Il catalogo del provider non è raggiungibile.") from exc


def _prezzo_milione(valore: Any) -> float | None:
    try:
        return float(valore) * 1_000_000
    except (TypeError, ValueError):
        return None


def _capacita_da_id(identificativo: str) -> tuple[str, ...]:
    nome = identificativo.lower()
    capacita = ["chat"]
    if any(x in nome for x in ("vision", "vl", "gpt-4o", "gpt-5", "claude")):
        capacita.append("visione")
    if any(x in nome for x in ("embed", "bge", "nomic")):
        capacita = ["embedding"]
    return tuple(capacita)


def normalizza_openai(dati: dict[str, Any]) -> list[ModelloCatalogo]:
    modelli = []
    esclusi = ("audio", "image", "tts", "transcribe", "whisper", "moderation", "realtime")
    for voce in dati.get("data", []):
        ident = str(voce.get("id", "")).strip()
        if not ident or any(x in ident.lower() for x in esclusi):
            continue
        capacita = _capacita_da_id(ident)
        if "chat" not in capacita and "embedding" not in capacita:
            continue
        creato = voce.get("created")
        if isinstance(creato, (int, float)):
            creato = datetime.fromtimestamp(creato, timezone.utc).isoformat()
        modelli.append(
            ModelloCatalogo(
                id=ident,
                nome=ident,
                provider="openai",
                input=("testo", "immagine") if "visione" in capacita else ("testo",),
                capacita=capacita,
                creato=creato,
                alias_variabile=not any(c.isdigit() for c in ident[-10:]),
            )
        )
    return sorted(modelli, key=lambda x: x.id)


def normalizza_anthropic(dati: dict[str, Any]) -> list[ModelloCatalogo]:
    modelli = []
    for voce in dati.get("data", []):
        ident = str(voce.get("id", "")).strip()
        if not ident:
            continue
        capacita = voce.get("capabilities") or {}
        strumenti = ["chat", "visione"]
        if capacita.get("thinking") or capacita.get("extended_thinking"):
            strumenti.append("ragionamento")
        modelli.append(
            ModelloCatalogo(
                id=ident,
                nome=str(voce.get("display_name") or ident),
                provider="anthropic",
                input=("testo", "immagine"),
                capacita=tuple(strumenti),
                creato=voce.get("created_at"),
                alias_variabile=ident.endswith(("-latest", "-current")),
            )
        )
    return sorted(modelli, key=lambda x: x.id)


def normalizza_openrouter(dati: dict[str, Any]) -> list[ModelloCatalogo]:
    modelli = []
    for voce in dati.get("data", []):
        ident = str(voce.get("id", "")).strip()
        if not ident:
            continue
        architettura = voce.get("architecture") or {}
        modalita = tuple(str(x).lower() for x in architettura.get("input_modalities", ["text"]))
        input_ = tuple("immagine" if x == "image" else "testo" if x == "text" else x for x in modalita)
        parametri = set(voce.get("supported_parameters") or [])
        capacita = ["chat"]
        if "image" in modalita:
            capacita.append("visione")
        if "tools" in parametri or "tool_choice" in parametri:
            capacita.append("strumenti")
        if "reasoning" in parametri or "include_reasoning" in parametri:
            capacita.append("ragionamento")
        prezzi = voce.get("pricing") or {}
        modelli.append(
            ModelloCatalogo(
                id=ident,
                nome=str(voce.get("name") or ident),
                provider="openrouter",
                input=input_ or ("testo",),
                capacita=tuple(capacita),
                contesto=voce.get("context_length"),
                output_massimo=(voce.get("top_provider") or {}).get("max_completion_tokens"),
                costo_input_milione=_prezzo_milione(prezzi.get("prompt")),
                costo_output_milione=_prezzo_milione(prezzi.get("completion")),
                creato=str(voce.get("created")) if voce.get("created") else None,
                scadenza=voce.get("expiration_date"),
                descrizione=str(voce.get("description") or ""),
                canonical_slug=voce.get("canonical_slug"),
            )
        )
    return sorted(modelli, key=lambda x: x.id)


def normalizza_ollama(
    dati: dict[str, Any], dettagli: dict[str, dict[str, Any]] | None = None
) -> list[ModelloCatalogo]:
    modelli = []
    dettagli = dettagli or {}
    for voce in dati.get("models", []):
        ident = str(voce.get("name") or voce.get("model") or "").strip()
        if not ident:
            continue
        dettaglio = dettagli.get(ident, {})
        capabilities = tuple(dettaglio.get("capabilities") or _capacita_da_id(ident))
        input_ = ("testo", "immagine") if "vision" in capabilities or "visione" in capabilities else ("testo",)
        capacita = tuple("visione" if x == "vision" else "embedding" if x == "embedding" else x for x in capabilities)
        info = dettaglio.get("model_info") or {}
        contesto = next((v for k, v in info.items() if k.endswith(".context_length") and isinstance(v, int)), None)
        modelli.append(
            ModelloCatalogo(
                id=ident,
                nome=ident,
                provider="ollama",
                input=input_,
                capacita=capacita,
                contesto=contesto,
                creato=voce.get("modified_at"),
                installato=True,
            )
        )
    return sorted(modelli, key=lambda x: x.id)


def carica(
    provider: str,
    *,
    chiave: str = "",
    ollama_host: str = "http://localhost:11434",
    openrouter_eu: bool = True,
) -> list[ModelloCatalogo]:
    """Carica il catalogo. Le chiamate esterne avvengono solo su richiesta esplicita."""

    provider = provider.lower()
    if provider == "ollama":
        base = ollama_host.rstrip("/")
        elenco = _json(f"{base}/api/tags")
        dettagli: dict[str, dict[str, Any]] = {}
        for voce in elenco.get("models", []):
            nome = voce.get("name") or voce.get("model")
            if nome:
                try:
                    dettagli[str(nome)] = _json(
                        f"{base}/api/show", metodo="POST", corpo={"model": nome}
                    )
                except ErroreCatalogo:
                    pass
        return normalizza_ollama(elenco, dettagli)

    if not chiave:
        raise ErroreCatalogo("Configura prima la chiave API del provider.")
    if provider == "openai":
        dati = _json("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {chiave}"})
        return normalizza_openai(dati)
    if provider == "anthropic":
        dati = _json(
            "https://api.anthropic.com/v1/models?limit=1000",
            headers={"x-api-key": chiave, "anthropic-version": "2023-06-01"},
        )
        return normalizza_anthropic(dati)
    if provider == "openrouter":
        host = "https://openrouter.ai" if not openrouter_eu else "https://eu.openrouter.ai"
        dati = _json(f"{host}/api/v1/models/user", headers={"Authorization": f"Bearer {chiave}"})
        return normalizza_openrouter(dati)
    raise ErroreCatalogo(f"Provider non supportato: {provider}.")


def salva_cache(conn, provider: str, modelli: list[ModelloCatalogo]) -> None:
    payload = {
        "aggiornato_il": datetime.now(timezone.utc).isoformat(),
        "modelli": [m.serializza() for m in modelli],
    }
    conn.execute(
        "INSERT OR REPLACE INTO impostazioni (chiave, valore) VALUES (?, ?)",
        (f"catalogo_modelli.{provider}", json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def leggi_cache(conn, provider: str) -> tuple[list[ModelloCatalogo], str | None]:
    riga = conn.execute(
        "SELECT valore FROM impostazioni WHERE chiave = ?", (f"catalogo_modelli.{provider}",)
    ).fetchone()
    if not riga:
        return [], None
    try:
        payload = json.loads(riga[0])
        modelli = [ModelloCatalogo.deserializza(x) for x in payload.get("modelli", [])]
        return modelli, payload.get("aggiornato_il")
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return [], None
