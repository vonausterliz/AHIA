"""AHIA — autenticazione e gestione degli utenti.

Le password non vengono mai salvate: si conserva un hash scrypt con sale
casuale per utente. scrypt e' nella libreria standard ed e' memory-hard, quindi
regge molto meglio di SHA-256 a un attacco con hardware dedicato, nel caso in
cui il file del database finisse in mani altrui.

Questo modulo decide CHI entra. Non separa gli archivi: tutti gli utenti
abilitati vedono gli stessi referti.
"""

# AHIA — archivio e lettura dei referti medici, in locale.
# Copyright (C) 2026  vonausterliz
#
# Questo programma e' software libero: puoi ridistribuirlo e/o modificarlo
# secondo i termini della GNU Affero General Public License, versione 3, come
# pubblicata dalla Free Software Foundation.
#
# Distribuito nella speranza che sia utile, ma SENZA ALCUNA GARANZIA, neppure
# quella implicita di commerciabilita' o idoneita' a uno scopo particolare.
# Vedi la GNU Affero General Public License per i dettagli:
# https://www.gnu.org/licenses/agpl-3.0.html

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import pathlib
import re
import secrets
import sqlite3

# Parametri scrypt: ~64 MB di memoria per verifica, circa 0,1 s su hardware
# recente. Alzarli rende piu' costoso un attacco a forza bruta, e anche il login.
SCRYPT_N = 2 ** 16
SCRYPT_R = 8
SCRYPT_P = 1
LUNGHEZZA_HASH = 64

TENTATIVI_MAX = 5
BLOCCO_MINUTI = 15
LUNGHEZZA_MINIMA = 10

DDL = """
CREATE TABLE IF NOT EXISTS utenti (
    id INTEGER PRIMARY KEY,
    nome_utente TEXT NOT NULL UNIQUE COLLATE NOCASE,
    hash BLOB NOT NULL,
    sale BLOB NOT NULL,
    ruolo TEXT NOT NULL DEFAULT 'utente' CHECK (ruolo IN ('admin', 'utente')),
    attivo INTEGER NOT NULL DEFAULT 1,
    cambio_password INTEGER NOT NULL DEFAULT 0,
    creato_il TEXT NOT NULL DEFAULT (datetime('now')),
    ultimo_accesso TEXT,
    tentativi_falliti INTEGER NOT NULL DEFAULT 0,
    bloccato_fino TEXT
);
"""


def apri(percorso=None) -> sqlite3.Connection:
    """Connessione al database delle utenze, separato dagli archivi sanitari."""
    from config import AUTH_DB

    conn = sqlite3.connect(percorso or AUTH_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    conn.commit()
    return conn


def prepara(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


def elimina_archivio(utente_id: int) -> bool:
    """Cancella la cartella dati di un utente. Irreversibile."""
    import shutil

    from config import Archivio

    cartella = Archivio(utente_id).dir
    if cartella.exists():
        shutil.rmtree(cartella, ignore_errors=True)
        return True
    return False


def esporta_archivio(utente_id: int) -> bytes | None:
    """Impacchetta l'intero archivio di un utente in uno zip, in memoria.

    Contiene i file cosi' come stanno su disco — salute.db, i PDF, i JSON del
    dizionario e dei riferimenti — quindi lo zip e' gia' un formato
    reimportabile: nella nuova istanza si scompatta nella cartella dell'utente e
    l'app lo ritrova identico. None se l'archivio non esiste.
    """
    import io
    import zipfile

    from config import Archivio

    cartella = Archivio(utente_id).dir
    if not cartella.exists():
        return None
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for percorso in sorted(cartella.rglob("*")):
            if percorso.is_file():
                z.write(percorso, percorso.relative_to(cartella).as_posix())
    return buffer.getvalue()


def importa_archivio(utente_id: int, dati_zip: bytes,
                     sovrascrivi: bool = False) -> tuple[bool, str]:
    """Ripristina un archivio da uno zip prodotto da esporta_archivio.

    Rifiuta se l'utente ha gia' un archivio non vuoto, salvo sovrascrivi=True.
    Estrae solo i percorsi previsti, per non far uscire file dalla cartella.
    """
    import io
    import zipfile

    from config import Archivio

    archivio = Archivio(utente_id)
    if archivio.db.exists() and not sovrascrivi:
        return False, "L'utente ha gia' un archivio. Serve conferma per sostituirlo."

    consentiti = {"salute.db", "alias_analiti.json", "riferimenti_personali.json"}
    LIMITE_FILE = 200 * 1024 * 1024   # 200 MB per file: oltre e' quasi certo abuso
    LIMITE_TOTALE = 500 * 1024 * 1024
    try:
        with zipfile.ZipFile(io.BytesIO(dati_zip)) as z:
            info = z.infolist()
            nomi = [i.filename for i in info]
            if "salute.db" not in nomi:
                return False, "Lo zip non sembra un archivio AHIA: manca salute.db."
            totale = 0
            for i in info:
                nome = i.filename
                # backslash normalizzato: su alcuni sistemi separa i percorsi
                parti = pathlib.PurePosixPath(nome.replace("\\", "/")).parts
                if nome.startswith("/") or ".." in parti:
                    return False, f"Percorso non sicuro nello zip: {nome}"
                # symlink e altri tipi non regolari: rifiutati
                if (i.external_attr >> 16) & 0o170000 not in (0, 0o100000, 0o040000):
                    return False, f"Voce non consentita nello zip: {nome}"
                if i.file_size > LIMITE_FILE:
                    return False, f"File troppo grande nello zip: {nome}"
                totale += i.file_size
            if totale > LIMITE_TOTALE:
                return False, "Archivio troppo grande: possibile file corrotto."
            if sovrascrivi and archivio.dir.exists():
                import shutil
                shutil.rmtree(archivio.dir, ignore_errors=True)
            archivio.pdf.mkdir(parents=True, exist_ok=True)
            for nome in nomi:
                base = nome.split("/", 1)[0]
                if base in consentiti or nome.startswith("referti/"):
                    z.extract(nome, archivio.dir)
    except zipfile.BadZipFile:
        return False, "Il file non e' uno zip valido."
    return True, "Archivio importato."


def migra_archivio_singolo(utente_id: int) -> bool:
    """Sposta l'archivio della versione a utente singolo dentro quello indicato.

    Serve una volta sola, quando si aggiorna da una versione senza utenze: senza
    questo passaggio i referti gia' caricati resterebbero orfani.
    """
    import shutil

    from config import (Archivio, LEGACY_ALIAS, LEGACY_DB, LEGACY_PDF,
                        LEGACY_RIFERIMENTI)

    if not LEGACY_DB.exists():
        return False
    archivio = Archivio(utente_id)
    if archivio.db.exists():
        return False  # l'archivio dell'utente esiste gia': non si sovrascrive
    shutil.move(str(LEGACY_DB), str(archivio.db))
    for sorgente, destinazione in ((LEGACY_ALIAS, archivio.alias),
                                   (LEGACY_RIFERIMENTI, archivio.riferimenti)):
        if sorgente.exists():
            shutil.move(str(sorgente), str(destinazione))
    if LEGACY_PDF.exists():
        for pdf in LEGACY_PDF.glob("*.pdf"):
            shutil.move(str(pdf), str(archivio.pdf / pdf.name))
        shutil.rmtree(LEGACY_PDF, ignore_errors=True)
    return True


# --- Password --------------------------------------------------------------


def _impronta(password: str, sale: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=sale, n=SCRYPT_N,
                          r=SCRYPT_R, p=SCRYPT_P, dklen=LUNGHEZZA_HASH,
                          maxmem=SCRYPT_N * SCRYPT_R * 200)


def robustezza(password: str) -> str:
    """Motivo del rifiuto, o stringa vuota se la password va bene."""
    if len(password) < LUNGHEZZA_MINIMA:
        return f"Servono almeno {LUNGHEZZA_MINIMA} caratteri."
    categorie = sum(bool(re.search(schema, password))
                    for schema in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w\s]"))
    if categorie < 3:
        return ("Servono almeno tre tipi di carattere tra minuscole, maiuscole, "
                "cifre e simboli.")
    if password.lower() in {"password123", "amministratore", "1234567890",
                            "qwertyuiop", "ahiaahiaahia"}:
        return "Password troppo comune."
    return ""


def password_suggerita(parole: int = 4) -> str:
    """Password casuale leggibile, per la creazione di un nuovo utente."""
    alfabeto = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    gruppi = ["".join(secrets.choice(alfabeto) for _ in range(4))
              for _ in range(parole)]
    return "-".join(gruppi)


# --- Utenti ----------------------------------------------------------------


def esistono_utenti(conn) -> bool:
    return conn.execute("SELECT COUNT(*) FROM utenti").fetchone()[0] > 0


def elenco(conn) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT id, nome_utente, ruolo, attivo, creato_il, ultimo_accesso,
                  tentativi_falliti, bloccato_fino
           FROM utenti ORDER BY ruolo, nome_utente""").fetchall()


def crea(conn, nome_utente: str, password: str, ruolo: str = "utente",
         cambio_password: bool = True) -> str:
    """Crea un utente. Restituisce il messaggio d'errore, vuoto se riuscito."""
    nome_utente = (nome_utente or "").strip()
    if not re.fullmatch(r"[\w.@-]{3,32}", nome_utente):
        return ("Il nome utente deve avere da 3 a 32 caratteri, senza spazi "
                "(lettere, cifre, punto, trattino, chiocciola).")
    if problema := robustezza(password):
        return problema
    sale = secrets.token_bytes(16)
    try:
        conn.execute(
            "INSERT INTO utenti (nome_utente, hash, sale, ruolo, cambio_password) "
            "VALUES (?,?,?,?,?)",
            (nome_utente, _impronta(password, sale), sale, ruolo,
             1 if cambio_password else 0))
        conn.commit()
    except sqlite3.IntegrityError:
        return "Nome utente gia' esistente."
    return ""


def _quanti_admin_attivi(conn, escluso: int | None = None) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM utenti WHERE ruolo='admin' AND attivo=1 "
        "AND id IS NOT ?", (escluso,)).fetchone()[0]


def imposta_stato(conn, id_utente: int, attivo: bool) -> str:
    """Blocca o riabilita un utente."""
    u = conn.execute("SELECT ruolo FROM utenti WHERE id=?", (id_utente,)).fetchone()
    if not u:
        return "Utente inesistente."
    if not attivo and u["ruolo"] == "admin" and _quanti_admin_attivi(conn, id_utente) == 0:
        return "E' l'ultimo amministratore attivo: non puoi bloccarlo."
    conn.execute("UPDATE utenti SET attivo=?, tentativi_falliti=0, "
                 "bloccato_fino=NULL WHERE id=?", (1 if attivo else 0, id_utente))
    conn.commit()
    return ""


def elimina(conn, id_utente: int) -> str:
    u = conn.execute("SELECT ruolo FROM utenti WHERE id=?", (id_utente,)).fetchone()
    if not u:
        return "Utente inesistente."
    if u["ruolo"] == "admin" and _quanti_admin_attivi(conn, id_utente) == 0:
        return "E' l'ultimo amministratore: non puoi eliminarlo."
    conn.execute("DELETE FROM utenti WHERE id=?", (id_utente,))
    conn.commit()
    return ""


def cambia_ruolo(conn, id_utente: int, ruolo: str) -> str:
    if ruolo not in ("admin", "utente"):
        return "Ruolo non valido."
    u = conn.execute("SELECT ruolo FROM utenti WHERE id=?", (id_utente,)).fetchone()
    if not u:
        return "Utente inesistente."
    if (u["ruolo"] == "admin" and ruolo == "utente"
            and _quanti_admin_attivi(conn, id_utente) == 0):
        return "E' l'ultimo amministratore: deve restare tale."
    conn.execute("UPDATE utenti SET ruolo=? WHERE id=?", (ruolo, id_utente))
    conn.commit()
    return ""


def cambia_password(conn, id_utente: int, password: str,
                    forza_cambio: bool = False) -> str:
    if problema := robustezza(password):
        return problema
    sale = secrets.token_bytes(16)
    conn.execute("UPDATE utenti SET hash=?, sale=?, cambio_password=?, "
                 "tentativi_falliti=0, bloccato_fino=NULL WHERE id=?",
                 (_impronta(password, sale), sale, 1 if forza_cambio else 0,
                  id_utente))
    conn.commit()
    return ""


# --- Accesso ---------------------------------------------------------------


def verifica(conn, nome_utente: str, password: str) -> tuple[dict | None, str]:
    """(utente, errore). L'utente e' None se l'accesso e' negato."""
    riga = conn.execute(
        "SELECT * FROM utenti WHERE nome_utente = ?", ((nome_utente or "").strip(),)
    ).fetchone()

    # Confronto fittizio quando l'utente non esiste: senza, il tempo di risposta
    # rivelerebbe quali nomi utente sono validi.
    if not riga:
        _impronta(password, b"0" * 16)
        return None, "Credenziali non valide."

    if not riga["attivo"]:
        return None, "Utente bloccato. Rivolgiti all'amministratore."

    if riga["bloccato_fino"]:
        try:
            fino = dt.datetime.fromisoformat(riga["bloccato_fino"])
        except ValueError:
            fino = None
        if fino and fino > dt.datetime.now():
            restano = int((fino - dt.datetime.now()).total_seconds() // 60) + 1
            return None, f"Troppi tentativi falliti: riprova tra {restano} minuti."

    if hmac.compare_digest(_impronta(password, riga["sale"]), riga["hash"]):
        conn.execute("UPDATE utenti SET ultimo_accesso=datetime('now'), "
                     "tentativi_falliti=0, bloccato_fino=NULL WHERE id=?",
                     (riga["id"],))
        conn.commit()
        return ({"id": riga["id"], "nome_utente": riga["nome_utente"],
                 "ruolo": riga["ruolo"],
                 "cambio_password": bool(riga["cambio_password"])}, "")

    tentativi = riga["tentativi_falliti"] + 1
    if tentativi >= TENTATIVI_MAX:
        fino = (dt.datetime.now() + dt.timedelta(minutes=BLOCCO_MINUTI)).isoformat()
        conn.execute("UPDATE utenti SET tentativi_falliti=?, bloccato_fino=? "
                     "WHERE id=?", (tentativi, fino, riga["id"]))
        conn.commit()
        return None, (f"Troppi tentativi falliti: accesso sospeso per "
                      f"{BLOCCO_MINUTI} minuti.")
    conn.execute("UPDATE utenti SET tentativi_falliti=? WHERE id=?",
                 (tentativi, riga["id"]))
    conn.commit()
    return None, (f"Credenziali non valide. Tentativi rimasti: "
                  f"{TENTATIVI_MAX - tentativi}.")


def variabile_admin_iniziale() -> tuple[str, str]:
    """Credenziali del primo amministratore da variabili d'ambiente, se presenti.

    Utile per un'installazione automatizzata; altrimenti l'app le chiede al
    primo avvio.
    """
    return (os.environ.get("AHIA_ADMIN_USER", ""),
            os.environ.get("AHIA_ADMIN_PASSWORD", ""))
