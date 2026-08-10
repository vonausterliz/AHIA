"""AHIA — livello dati (SQLite), costruzione del contesto e client Ollama."""

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
import re
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

from config import (DB_PATH, FUNZIONI, LOG_OLLAMA, OLLAMA_CHAT_URL,
                    etichetta as etichetta_tipo,
                    OLLAMA_PULL_URL, OLLAMA_TAGS_URL, TIMEOUT_LLM,
                    TIMEOUT_PULL)

DDL = """
CREATE TABLE IF NOT EXISTS profilo (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    nome TEXT, anno_nascita INTEGER, sesso TEXT,
    altezza_cm REAL, peso_kg REAL, terapie TEXT, note TEXT,
    aggiornato_il TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS impostazioni (
    chiave TEXT PRIMARY KEY,
    valore TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS file_processati (
    sha256 TEXT PRIMARY KEY,
    nome_file TEXT NOT NULL,
    origine TEXT NOT NULL,
    ingerito_il TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS documenti (
    sha256 TEXT PRIMARY KEY REFERENCES file_processati(sha256) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    data_documento TEXT,
    titolo TEXT,
    struttura TEXT,
    sintesi TEXT,
    conclusioni TEXT,
    reperti TEXT
);
CREATE INDEX IF NOT EXISTS idx_documenti_tipo ON documenti (tipo, data_documento);
CREATE TABLE IF NOT EXISTS testi (
    sha256 TEXT PRIMARY KEY REFERENCES file_processati(sha256) ON DELETE CASCADE,
    testo TEXT NOT NULL,
    caratteri INTEGER NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS testi_fts USING fts5(
    sha256 UNINDEXED, testo,
    tokenize = "unicode61 remove_diacritics 2"
);
CREATE TABLE IF NOT EXISTS frammenti (
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL REFERENCES file_processati(sha256) ON DELETE CASCADE,
    ordine INTEGER NOT NULL,
    testo TEXT NOT NULL,
    modello TEXT NOT NULL,
    vettore BLOB NOT NULL,
    UNIQUE (sha256, ordine)
);
CREATE TABLE IF NOT EXISTS risultati (
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL REFERENCES file_processati(sha256) ON DELETE CASCADE,
    data_prelievo TEXT NOT NULL, laboratorio TEXT,
    analita TEXT NOT NULL, nome_referto TEXT NOT NULL,
    valore REAL, operatore TEXT, valore_testo TEXT, unita TEXT,
    range_min REAL, range_max REAL, flag TEXT, origine_range TEXT,
    UNIQUE (data_prelievo, laboratorio, analita, nome_referto)
);
CREATE INDEX IF NOT EXISTS idx_analita_data ON risultati (analita, data_prelievo);
CREATE INDEX IF NOT EXISTS idx_risultati_sha ON risultati (sha256);
CREATE TABLE IF NOT EXISTS istruzioni_layout (
    id INTEGER PRIMARY KEY,
    laboratorio TEXT NOT NULL,
    problema TEXT,
    istruzione TEXT NOT NULL,
    creata_il TEXT NOT NULL DEFAULT (datetime('now')),
    usata INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_layout_lab ON istruzioni_layout (laboratorio);
CREATE TABLE IF NOT EXISTS conversazioni (
    id INTEGER PRIMARY KEY,
    titolo TEXT NOT NULL, modello TEXT,
    creata_il TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS messaggi (
    id INTEGER PRIMARY KEY,
    conversazione_id INTEGER NOT NULL REFERENCES conversazioni(id) ON DELETE CASCADE,
    ruolo TEXT NOT NULL, contenuto TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eventi (
    id INTEGER PRIMARY KEY,
    quando TEXT NOT NULL DEFAULT (datetime('now')),
    tipo TEXT NOT NULL,          -- 'modello', 'operazione', 'errore'
    categoria TEXT,              -- fase/funzione: estrazione, analisi, login…
    esito TEXT,                  -- 'ok' | 'errore'
    modello TEXT,
    durata_s REAL,
    token_in INTEGER,
    token_out INTEGER,
    dettaglio TEXT               -- messaggio d'errore o nota, mai dati sanitari
);
"""


_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FORMATI = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%m-%y",
            "%d/%m/%y", "%Y%m%d", "%d %B %Y", "%d %b %Y")


def normalizza_data(grezza: str | None) -> str:
    """Qualunque formato plausibile -> YYYY-MM-DD. Stringa vuota se irriconoscibile.

    Il modello restituisce a volte il formato italiano: archiviarlo cosi' com'e'
    romperebbe l'ordinamento, che sulle date e' un confronto tra stringhe.
    """
    testo = (grezza or "").strip()
    if not testo:
        return ""
    if _ISO.match(testo):
        try:
            dt.date.fromisoformat(testo)
            return testo
        except ValueError:
            return ""
    for formato in _FORMATI:
        try:
            return dt.datetime.strptime(testo, formato).date().isoformat()
        except ValueError:
            continue
    return ""


def _aggiungi_colonna(conn, tabella: str, colonna: str, tipo: str) -> None:
    """CREATE TABLE IF NOT EXISTS non aggiunge colonne a una tabella esistente."""
    presenti = {r[1] for r in conn.execute(f"PRAGMA table_info({tabella})")}
    if colonna not in presenti:
        conn.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {tipo}")
        conn.commit()


def applica_catalogo(conn, sesso: str = "", percorso_riferimenti=None) -> int:
    """Completa gli intervalli mancanti con quelli del catalogo.

    Tocca solo le righe in cui il laboratorio non ha indicato alcun riferimento,
    e solo quando l'unita' di misura coincide. Le righe cosi' completate restano
    marcate con origine_range='catalogo'.
    """
    import riferimenti

    aggiornate = 0
    for r in conn.execute(
        """SELECT id, analita, unita, valore FROM risultati
           WHERE valore IS NOT NULL
             AND ((range_min IS NULL AND range_max IS NULL
                   AND origine_range IS NULL)
                  OR origine_range = 'catalogo')""").fetchall():
        trovato = riferimenti.intervallo(r["analita"], r["unita"], sesso,
                                         percorso_riferimenti)
        if not trovato:
            continue
        lo, hi, _ = trovato
        flag = ("L" if lo is not None and r["valore"] < lo
                else "H" if hi is not None and r["valore"] > hi else "N")
        conn.execute(
            "UPDATE risultati SET range_min=?, range_max=?, flag=?, "
            "origine_range='catalogo' WHERE id=?", (lo, hi, flag, r["id"]))
        aggiornate += 1
    if aggiornate:
        conn.commit()
    return aggiornate


def svuota_catalogo(conn) -> int:
    """Rimuove gli intervalli presi dal catalogo, lasciando quelli dei referti."""
    cur = conn.execute(
        "UPDATE risultati SET range_min=NULL, range_max=NULL, flag='', "
        "origine_range=NULL WHERE origine_range = 'catalogo'")
    conn.commit()
    return cur.rowcount


def _ricalcola_flag(conn) -> int:
    """Riallinea i flag archiviati al calcolo sui limiti.

    Le versioni precedenti si fidavano del flag dichiarato dal modello, che su
    esami come l'HDL (dove alto e' desiderabile) sbagliava sistematicamente.
    """
    corretti = 0
    for r in conn.execute(
        """SELECT id, valore, range_min, range_max, flag FROM risultati
           WHERE valore IS NOT NULL
             AND (range_min IS NOT NULL OR range_max IS NOT NULL)
             AND (origine_range IS NULL OR origine_range <> 'catalogo')""").fetchall():
        atteso = ("L" if r["range_min"] is not None and r["valore"] < r["range_min"]
                  else "H" if r["range_max"] is not None and r["valore"] > r["range_max"]
                  else "N")
        if (r["flag"] or "") != atteso:
            conn.execute("UPDATE risultati SET flag = ? WHERE id = ?",
                         (atteso, r["id"]))
            corretti += 1
    if corretti:
        conn.commit()
    return corretti


def _migra_date(conn) -> int:
    """Riscrive in ISO le date archiviate in altri formati."""
    corrette = 0
    for tabella, campo in (("risultati", "data_prelievo"),
                           ("documenti", "data_documento")):
        righe = conn.execute(
            f"SELECT rowid AS rid, {campo} AS valore FROM {tabella} "
            f"WHERE {campo} IS NOT NULL AND {campo} <> '' "
            f"AND {campo} NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
        ).fetchall()
        for r in righe:
            iso = normalizza_data(r["valore"])
            conn.execute(f"UPDATE {tabella} SET {campo} = ? WHERE rowid = ?",
                         (iso or None, r["rid"]))
            corrette += 1
    if corrette:
        conn.commit()
    return corrette


def apri_db(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    # altezza inserita in metri invece che in centimetri: correzione una tantum
    conn.execute("UPDATE profilo SET altezza_cm = altezza_cm * 100 "
                 "WHERE altezza_cm > 0 AND altezza_cm < 3")
    conn.commit()
    _aggiungi_colonna(conn, "risultati", "origine_range", "TEXT")
    _migra_date(conn)
    _ricalcola_flag(conn)
    return conn


# --- Profilo e impostazioni ------------------------------------------------


def leggi_profilo(conn) -> dict:
    row = conn.execute("SELECT * FROM profilo WHERE id = 1").fetchone()
    return dict(row) if row else {}


def normalizza_altezza(altezza) -> float | None:
    """Accetta sia centimetri sia metri: sotto 3 e' certamente in metri."""
    if not altezza:
        return None
    altezza = float(altezza)
    return altezza * 100 if altezza < 3 else altezza


def calcola_bmi(altezza_cm, peso_kg) -> float | None:
    """BMI, oppure None se i dati non danno un risultato plausibile."""
    if not altezza_cm or not peso_kg:
        return None
    h = float(altezza_cm) / 100
    if h <= 0:
        return None
    bmi = float(peso_kg) / (h * h)
    return round(bmi, 1) if 8 <= bmi <= 90 else None


def salva_profilo(conn, dati: dict) -> None:
    dati = {**dati, "altezza_cm": normalizza_altezza(dati.get("altezza_cm"))}
    conn.execute(
        """INSERT INTO profilo (id, nome, anno_nascita, sesso, altezza_cm, peso_kg,
                                terapie, note, aggiornato_il)
           VALUES (1, :nome, :anno_nascita, :sesso, :altezza_cm, :peso_kg,
                   :terapie, :note, datetime('now'))
           ON CONFLICT(id) DO UPDATE SET
             nome=excluded.nome, anno_nascita=excluded.anno_nascita,
             sesso=excluded.sesso, altezza_cm=excluded.altezza_cm,
             peso_kg=excluded.peso_kg, terapie=excluded.terapie,
             note=excluded.note, aggiornato_il=datetime('now')""", dati)
    conn.commit()


def leggi_impostazioni(conn) -> dict[str, str]:
    return {r["chiave"]: r["valore"] for r in conn.execute("SELECT * FROM impostazioni")}


def salva_impostazione(conn, chiave: str, valore: str) -> None:
    conn.execute("""INSERT INTO impostazioni (chiave, valore) VALUES (?, ?)
                    ON CONFLICT(chiave) DO UPDATE SET valore = excluded.valore""",
                 (chiave, valore))
    conn.commit()


def elimina_impostazione(conn, chiave: str) -> None:
    conn.execute("DELETE FROM impostazioni WHERE chiave = ?", (chiave,))
    conn.commit()


def modello_per(conn, funzione: str) -> str:
    return leggi_impostazioni(conn).get(f"modello.{funzione}",
                                        FUNZIONI[funzione]["default"])


# --- Referti ---------------------------------------------------------------


def nome_file_sicuro(nome: str) -> str:
    """Nome utilizzabile su tutti i filesystem, Windows compreso."""
    pulito = re.sub(r'[\\/:*?"<>|]', "_", nome).strip(". ")
    return (pulito or "documento.pdf")[:120]


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def file_gia_presente(conn, sha: str) -> bool:
    return conn.execute("SELECT 1 FROM file_processati WHERE sha256 = ?",
                        (sha,)).fetchone() is not None


def salva_referto(conn, sha: str, nome_file: str, origine: str,
                  dati: dict, righe: list[dict]) -> int:
    conn.execute("INSERT OR REPLACE INTO file_processati "
                 "(sha256, nome_file, origine) VALUES (?,?,?)",
                 (sha, nome_file, origine))
    data = normalizza_data(dati.get("data_prelievo"))
    lab = dati.get("laboratorio") or ""
    nuove = 0
    for r in righe:
        cur = conn.execute(
            """INSERT OR IGNORE INTO risultati
               (sha256, data_prelievo, laboratorio, analita, nome_referto, valore,
                operatore, valore_testo, unita, range_min, range_max, flag,
                origine_range)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sha, data, lab, r["analita"], r["nome_referto"], r["valore"],
             r["operatore"], r["valore_testo"], r["unita"],
             r["range_min"], r["range_max"], r["flag"],
             "referto" if (r["range_min"] is not None
                           or r["range_max"] is not None) else None))
        nuove += cur.rowcount
    conn.commit()
    return nuove


def sostituisci_valori(conn, sha: str, righe: list[dict]) -> int:
    """Rimpiazza i valori di un referto con una nuova estrazione.

    Usato dal recupero dell'estrazione: cancella i valori attuali del documento
    e inserisce quelli nuovi, conservando data e laboratorio gia' noti.
    """
    testa = conn.execute(
        "SELECT data_prelievo, laboratorio FROM risultati WHERE sha256=? LIMIT 1",
        (sha,)).fetchone()
    data = testa["data_prelievo"] if testa else ""
    lab = testa["laboratorio"] if testa else ""
    conn.execute("DELETE FROM risultati WHERE sha256 = ?", (sha,))
    inserite = 0
    for r in righe:
        conn.execute(
            """INSERT INTO risultati
               (sha256, data_prelievo, laboratorio, analita, nome_referto, valore,
                operatore, valore_testo, unita, range_min, range_max, flag,
                origine_range)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sha, data, lab, r["analita"], r["nome_referto"], r["valore"],
             r["operatore"], r["valore_testo"], r["unita"],
             r["range_min"], r["range_max"], r["flag"],
             "referto" if (r["range_min"] is not None
                           or r["range_max"] is not None) else None))
        inserite += 1
    conn.commit()
    return inserite


def salva_documento(conn, sha: str, dati: dict) -> None:
    """Anagrafica del documento: tipologia, data, titolo e, se narrativo, sintesi."""
    n = dati.get("narrativa") or {}
    conn.execute(
        """INSERT INTO documenti (sha256, tipo, data_documento, titolo, struttura,
                                  sintesi, conclusioni, reperti)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(sha256) DO UPDATE SET
             tipo=excluded.tipo, data_documento=excluded.data_documento,
             titolo=excluded.titolo, struttura=excluded.struttura,
             sintesi=excluded.sintesi, conclusioni=excluded.conclusioni,
             reperti=excluded.reperti""",
        (sha, dati.get("tipo", "altro"),
         normalizza_data(dati.get("data_documento")) or None,
         dati.get("titolo") or None, dati.get("struttura") or None,
         n.get("sintesi") or None, n.get("conclusioni") or None,
         json.dumps(n.get("reperti_rilevanti") or [], ensure_ascii=False)))
    conn.commit()


def cambia_tipo(conn, sha: str, tipo: str) -> None:
    conn.execute("UPDATE documenti SET tipo = ? WHERE sha256 = ?", (tipo, sha))
    conn.commit()


def documenti_per_tipo(conn) -> dict[str, list[sqlite3.Row]]:
    """Documenti raggruppati per tipologia, piu' recenti prima."""
    # Il conteggio dei valori come sottoquery veniva eseguito una volta per
    # documento: con centinaia di referti diventava la parte piu' lenta della
    # scheda. Un solo raggruppamento fa lo stesso lavoro in un passaggio.
    righe = conn.execute(
        """SELECT d.*, f.nome_file, f.origine, f.ingerito_il,
                  COALESCE(c.n, 0) AS n_esami
           FROM documenti d
           JOIN file_processati f ON f.sha256 = d.sha256
           LEFT JOIN (SELECT sha256, COUNT(*) AS n FROM risultati
                      GROUP BY sha256) c ON c.sha256 = d.sha256
           ORDER BY d.data_documento DESC, f.ingerito_il DESC""").fetchall()
    gruppi: dict[str, list] = {}
    for r in righe:
        gruppi.setdefault(r["tipo"], []).append(r)
    return gruppi


def documenti_narrativi(conn, quanti: int = 6) -> list[sqlite3.Row]:
    """Referti non tabellari piu' recenti, con la loro sintesi."""
    return conn.execute(
        """SELECT tipo, data_documento, titolo, sintesi, conclusioni
           FROM documenti WHERE sintesi IS NOT NULL AND sintesi <> ''
           ORDER BY data_documento DESC LIMIT ?""", (quanti,)).fetchall()


def documenti_di_tipo(conn, tipo: str) -> list[sqlite3.Row]:
    """Tutti i documenti di un tipo, cronologici, con sintesi e testo completo.

    Serve alla scheda dei referti descrittivi: raccoglie per una categoria
    (oculistica, ecografia…) tutto ciò che serve a mostrarli e a farci ragionare
    il modello, in un'unica query.
    """
    return conn.execute(
        """SELECT d.sha256, d.tipo, d.data_documento, d.titolo, d.struttura,
                  d.sintesi, d.conclusioni, f.nome_file, f.origine,
                  t.testo
           FROM documenti d
           JOIN file_processati f ON f.sha256 = d.sha256
           LEFT JOIN testi t ON t.sha256 = d.sha256
           WHERE d.tipo = ?
           ORDER BY d.data_documento DESC, f.ingerito_il DESC""",
        (tipo,)).fetchall()


def documenti_di_tipo_qualunque(conn) -> list[sqlite3.Row]:
    """Tutti i documenti dell'archivio, con sintesi e testo, più recenti prima."""
    return conn.execute(
        """SELECT d.sha256, d.tipo, d.data_documento, d.titolo, d.struttura,
                  d.sintesi, d.conclusioni, f.nome_file, f.origine,
                  t.testo
           FROM documenti d
           JOIN file_processati f ON f.sha256 = d.sha256
           LEFT JOIN testi t ON t.sha256 = d.sha256
           ORDER BY d.data_documento DESC, f.ingerito_il DESC""").fetchall()


def contesto_referto(conn, sha: str, max_caratteri: int = 12000) -> str:
    """Testo di un singolo referto, pronto per il modello."""
    r = conn.execute(
        """SELECT d.tipo, d.data_documento, d.struttura, d.sintesi, d.conclusioni,
                  t.testo
           FROM documenti d LEFT JOIN testi t ON t.sha256 = d.sha256
           WHERE d.sha256 = ?""", (sha,)).fetchone()
    if not r:
        return ""
    from config import TIPI
    data = normalizza_data(r["data_documento"]) or "data ignota"
    etichetta_t = TIPI.get(r["tipo"], {}).get("label", "Referto")
    testa = f"— {etichetta_t} del {data}"
    if r["struttura"]:
        testa += f" · {r['struttura']}"
    corpo = (r["testo"] or r["sintesi"] or "").strip()
    if len(corpo) > max_caratteri:
        corpo = corpo[:max_caratteri] + " […]"
    return f"{testa}\n{corpo}"


def contesto_categoria(conn, tipo: str, max_caratteri: int = 12000) -> str:
    """Testo dei referti di una categoria, pronto per il modello.

    Mette in fila i referti in ordine cronologico con data, struttura e
    contenuto, così il modello può ragionare sull'evoluzione di quella sola
    categoria senza mescolarla con gli esami del sangue o con altre visite. Il
    testo di ogni referto è troncato se molto lungo, per non sforare il contesto.
    """
    righe = documenti_di_tipo(conn, tipo)
    if not righe:
        return ""
    per_referto = max(1500, max_caratteri // max(1, len(righe)))
    blocchi = []
    for r in righe:
        data = normalizza_data(r["data_documento"]) or "data ignota"
        intest = f"— Referto del {data}"
        if r["struttura"]:
            intest += f" · {r['struttura']}"
        corpo = (r["testo"] or "").strip()
        if not corpo:
            corpo = (r["sintesi"] or "").strip()
        if len(corpo) > per_referto:
            corpo = corpo[:per_referto] + " […]"
        blocchi.append(f"{intest}\n{corpo}")
    return "\n\n".join(blocchi)


def salva_testo(conn, sha: str, testo: str) -> None:
    """Conserva il testo estratto: e' la base di ricerca e indicizzazione.

    Senza questo, l'unica traccia di un referto narrativo sarebbe la sintesi
    prodotta dal modello, che e' per definizione parziale.
    """
    testo = (testo or "").strip()
    if not testo:
        return
    conn.execute("INSERT INTO testi (sha256, testo, caratteri) VALUES (?,?,?) "
                 "ON CONFLICT(sha256) DO UPDATE SET testo=excluded.testo, "
                 "caratteri=excluded.caratteri", (sha, testo, len(testo)))
    conn.execute("DELETE FROM testi_fts WHERE sha256 = ?", (sha,))
    conn.execute("INSERT INTO testi_fts (sha256, testo) VALUES (?,?)", (sha, testo))
    conn.commit()


def leggi_testo(conn, sha: str) -> str:
    r = conn.execute("SELECT testo FROM testi WHERE sha256 = ?", (sha,)).fetchone()
    return r["testo"] if r else ""


def registra_evento(conn, tipo: str, *, categoria: str = "", esito: str = "ok",
                    modello: str = "", durata_s: float | None = None,
                    token_in: int | None = None, token_out: int | None = None,
                    dettaglio: str = "", dettaglio_sicuro: bool = False) -> None:
    """Scrive una riga nel registro eventi (osservabilità).

    Per impostazione predefinita ``dettaglio`` non viene conservato: gli errori
    di modelli e provider possono incorporare parti dell'input. Soltanto una
    stringa costruita dal programma e dichiarata esplicitamente sicura può
    entrare nel registro. Best-effort: un errore di scrittura non influenza
    l'operazione principale.
    """
    try:
        conn.execute(
            """INSERT INTO eventi
               (tipo, categoria, esito, modello, durata_s, token_in, token_out,
                dettaglio)
               VALUES (?,?,?,?,?,?,?,?)""",
            (tipo, categoria, esito, modello, durata_s, token_in, token_out,
             (dettaglio or "")[:500] if dettaglio_sicuro else ""))
        conn.commit()
    except sqlite3.Error:
        pass


def leggi_eventi(conn, limite: int = 500, tipo: str | None = None) -> list:
    """Eventi recenti, più nuovi prima, opzionalmente filtrati per tipo."""
    if tipo:
        return conn.execute(
            "SELECT * FROM eventi WHERE tipo = ? ORDER BY id DESC LIMIT ?",
            (tipo, limite)).fetchall()
    return conn.execute(
        "SELECT * FROM eventi ORDER BY id DESC LIMIT ?", (limite,)).fetchall()


def statistiche_eventi(conn) -> dict:
    """Riepilogo per il cruscotto: conteggi, durate, token, velocità."""
    r = conn.execute(
        """SELECT
             COUNT(*) FILTER (WHERE tipo='modello') AS chiamate,
             COUNT(*) FILTER (WHERE tipo='operazione') AS operazioni,
             COUNT(*) FILTER (WHERE esito='errore') AS errori,
             ROUND(AVG(durata_s) FILTER (WHERE tipo='modello'), 1) AS durata_media,
             ROUND(MAX(durata_s) FILTER (WHERE tipo='modello'), 1) AS durata_max,
             COALESCE(SUM(token_in), 0) AS tok_in,
             COALESCE(SUM(token_out), 0) AS tok_out,
             ROUND(AVG(token_out) FILTER (WHERE tipo='modello'), 0) AS tok_out_medio
           FROM eventi""").fetchone()
    stat = dict(r) if r else {}
    # velocità di generazione media (token/s), quando abbiamo i dati
    vel = conn.execute(
        """SELECT ROUND(SUM(token_out) * 1.0 / NULLIF(SUM(durata_s), 0), 1)
           FROM eventi WHERE tipo='modello' AND token_out > 0 AND durata_s > 0"""
    ).fetchone()
    stat["token_s"] = vel[0] if vel else None
    return stat


def eventi_per_categoria(conn) -> list:
    """Conteggio e durata media per categoria: dove va il tempo."""
    return conn.execute(
        """SELECT categoria,
                  COUNT(*) AS n,
                  ROUND(AVG(durata_s), 1) AS durata_media,
                  COALESCE(SUM(token_out), 0) AS tok_out,
                  COUNT(*) FILTER (WHERE esito='errore') AS errori
           FROM eventi
           WHERE categoria != ''
           GROUP BY categoria
           ORDER BY n DESC""").fetchall()


def azzera_eventi(conn) -> None:
    """Svuota il registro eventi."""
    conn.execute("DELETE FROM eventi")
    conn.commit()


def cerca_testo(conn, query: str, limite: int = 20) -> list[sqlite3.Row]:
    """Ricerca full-text sui documenti, con l'estratto attorno alle occorrenze."""
    if not query.strip():
        return []
    # sintassi FTS5: ogni parola come prefisso, cosi' "colest" trova "colesterolo"
    espressione = " ".join(f'"{p}"*' for p in re.findall(r"\w+", query))
    if not espressione:
        return []
    try:
        return conn.execute(
            """SELECT f.sha256, d.tipo, d.data_documento, d.titolo, fp.nome_file,
                      snippet(testi_fts, 1, '**', '**', ' … ', 24) AS estratto,
                      bm25(testi_fts) AS punteggio
               FROM testi_fts f
               JOIN file_processati fp ON fp.sha256 = f.sha256
               LEFT JOIN documenti d ON d.sha256 = f.sha256
               WHERE testi_fts MATCH ?
               ORDER BY punteggio LIMIT ?""", (espressione, limite)).fetchall()
    except sqlite3.OperationalError:
        return []


def documenti_indicizzati(conn) -> tuple[int, int]:
    """(documenti con testo, documenti totali)."""
    con_testo = conn.execute("SELECT COUNT(*) FROM testi").fetchone()[0]
    totali = conn.execute("SELECT COUNT(*) FROM file_processati").fetchone()[0]
    return con_testo, totali


def estrazione_sospetta(conn, sha: str) -> list[str]:
    """Indizi che un referto potrebbe essere stato estratto male. Lista vuota
    se nulla insospettisce. Sono indizi, non certezze: guidano l'occhio."""
    righe = conn.execute(
        "SELECT analita, valore, valore_testo, unita, range_min, range_max "
        "FROM risultati WHERE sha256 = ?", (sha,)).fetchall()
    if not righe:
        return ["Nessun valore estratto da questo referto."]
    indizi = []
    senza_unita = sum(1 for r in righe if not (r["unita"] or "").strip())
    if senza_unita > len(righe) / 2:
        indizi.append(f"{senza_unita} valori su {len(righe)} sono senza unita' "
                      "di misura.")
    assurdi = [r["analita"] for r in righe
               if r["valore"] is not None and abs(r["valore"]) >= 1e5]
    if assurdi:
        indizi.append(f"Valori numerici molto grandi, forse mal letti: "
                      f"{', '.join(assurdi[:4])}.")
    senza_rif = sum(1 for r in righe
                    if r["range_min"] is None and r["range_max"] is None)
    if senza_rif == len(righe) and len(righe) > 3:
        indizi.append("Nessun valore ha un intervallo di riferimento: potrebbero "
                      "essere stati persi in lettura.")
    # confronto con la media dei referti dello stesso laboratorio
    lab = conn.execute("SELECT laboratorio FROM risultati WHERE sha256=? LIMIT 1",
                       (sha,)).fetchone()
    if lab and lab["laboratorio"]:
        media = conn.execute(
            """SELECT AVG(n) FROM (SELECT COUNT(*) AS n FROM risultati
               WHERE laboratorio = ? GROUP BY sha256)""",
            (lab["laboratorio"],)).fetchone()[0]
        if media and len(righe) < media * 0.5 and media - len(righe) > 3:
            indizi.append(f"Solo {len(righe)} valori, contro una media di "
                          f"{media:.0f} per questo laboratorio: forse ne mancano.")
    return indizi


def salva_istruzione_layout(conn, laboratorio: str, problema: str,
                            istruzione: str) -> None:
    """Registra un'istruzione scoperta diagnosticando un'estrazione fallita.

    Un laboratorio impagina di solito allo stesso modo: l'istruzione trovata su
    un suo referto vale probabilmente per i prossimi. Vengono conservate anche
    per costruire, col tempo, il materiale con cui migliorare i prompt di base.
    """
    if not (laboratorio or "").strip() or not istruzione.strip():
        return
    conn.execute(
        "INSERT INTO istruzioni_layout (laboratorio, problema, istruzione) "
        "VALUES (?,?,?)", (laboratorio.strip(), problema, istruzione.strip()))
    conn.commit()


def istruzione_layout_per(conn, laboratorio: str) -> str:
    """L'istruzione piu' recente nota per un laboratorio, se esiste."""
    if not (laboratorio or "").strip():
        return ""
    riga = conn.execute(
        "SELECT id, istruzione FROM istruzioni_layout WHERE laboratorio = ? "
        "ORDER BY creata_il DESC LIMIT 1", (laboratorio.strip(),)).fetchone()
    if riga:
        conn.execute("UPDATE istruzioni_layout SET usata = usata + 1 WHERE id = ?",
                     (riga["id"],))
        conn.commit()
        return riga["istruzione"]
    return ""


def elenco_istruzioni_layout(conn) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM istruzioni_layout ORDER BY laboratorio, creata_il DESC"
    ).fetchall()


def elimina_istruzione_layout(conn, id_istruzione: int) -> None:
    conn.execute("DELETE FROM istruzioni_layout WHERE id = ?", (id_istruzione,))
    conn.commit()


def elimina_referto(conn, sha: str) -> None:
    conn.execute("DELETE FROM testi_fts WHERE sha256 = ?", (sha,))
    conn.execute("DELETE FROM file_processati WHERE sha256 = ?", (sha,))
    conn.commit()


def elenco_file(conn) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT f.sha256, f.nome_file, f.origine, f.ingerito_il,
                  COUNT(r.id) AS n_esami, MIN(r.data_prelievo) AS data_prelievo
           FROM file_processati f LEFT JOIN risultati r ON r.sha256 = f.sha256
           GROUP BY f.sha256 ORDER BY data_prelievo DESC""").fetchall()


def elenco_analiti(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT analita FROM risultati "
        "WHERE valore IS NOT NULL ORDER BY analita")]


def analiti_fuori_range(conn) -> list[str]:
    """Analiti alterati nell'ultimo referto in cui compaiono."""
    return [r[0] for r in conn.execute(
        """SELECT r.analita FROM risultati r
           JOIN (SELECT analita, MAX(data_prelievo) AS ultima
                 FROM risultati GROUP BY analita) u
             ON u.analita = r.analita AND u.ultima = r.data_prelievo
           WHERE r.flag IN ('H','L') ORDER BY r.analita""")]


def misure_duplicate(conn) -> list[sqlite3.Row]:
    """Esami presenti piu' volte nella stessa data: referti sovrapposti."""
    return conn.execute(
        """SELECT analita, data_prelievo, COUNT(*) AS n,
                  GROUP_CONCAT(DISTINCT laboratorio) AS laboratori
           FROM risultati WHERE valore IS NOT NULL
           GROUP BY analita, data_prelievo HAVING n > 1
           ORDER BY data_prelievo DESC, analita""").fetchall()


def numero_prelievi(conn) -> int:
    """Date di prelievo distinte presenti in archivio."""
    return conn.execute(
        "SELECT COUNT(DISTINCT data_prelievo) FROM risultati").fetchone()[0] or 0


def stima_token(testo: str) -> int:
    """Stima grossolana: in italiano circa 3,5 caratteri per token."""
    return int(len(testo) / 3.5)


def ultimo_referto(conn) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT * FROM risultati
           WHERE data_prelievo = (SELECT MAX(data_prelievo) FROM risultati)
           ORDER BY analita""").fetchall()


# --- Contesto per l'LLM ----------------------------------------------------

SYSTEM = """Sei un assistente che aiuta una persona a leggere i propri esami di
laboratorio. Lavori in locale, sui dati che seguono.

Come rispondi:
- Riporti i valori esattamente come sono nei dati, senza inventarne o stimarne.
- Distingui i valori fuori range da quelli ai margini del range.
- Dai priorita' all'andamento nel tempo rispetto al singolo valore isolato.
- Spieghi cosa misura un esame e cosa puo' far variare quel valore.
- Se un dato manca o e' ambiguo, lo dici invece di colmarlo.

Limiti che rispetti sempre:
- Non formuli diagnosi e non proponi o modifichi terapie.
- Non hai la storia clinica completa, il motivo della prescrizione ne' l'esame
  obiettivo: molte variazioni hanno spiegazioni banali che non puoi vedere.
- Il tuo scopo e' rendere leggibile l'andamento e aiutare a formulare domande
  sensate al medico, non sostituirlo.
- Se emergono valori marcatamente alterati lo dici con chiarezza e senza
  allarmismi, indicando che vanno portati all'attenzione del medico."""

PROMPT_ANALISI = """Analizza i dati qui sopra e produci:

1. **Quadro d'insieme** — due o tre righe, mettendo in cima cio' che merita
   piu' attenzione.
2. **Fuori range** — valori alterati, ordinati per rilevanza clinica (prima i
   piu' marcati). Per ciascuno: entita' dello scostamento e cosa misura
   quell'esame. Se un valore e' di poco fuori norma e coerente col resto,
   dillo: spesso e' una variazione banale, non un problema.
3. **Pattern e andamenti** — non limitarti a commentare i valori uno per uno:
   collega quelli che raccontano una storia comune (piu' marcatori dello stesso
   organo che si muovono insieme, o una carenza che spiega piu' valori). Includi
   qui anche gli analiti che si muovono in modo consistente nel tempo tra un
   referto e l'altro, anche restando nella norma.
4. **Da chiedere al medico** — domande concrete da portare alla visita."""

# Sezione aggiuntiva, agganciata solo se l'utente attiva il controllo delle
# incoerenze: allunga l'analisi e va spiegata bene, quindi non e' sempre attiva.
PROMPT_INCOERENZE = """

5. **Possibili errori di lettura** — questa e' una sezione speciale. I dati che
   vedi provengono da un'estrazione automatica di PDF e possono contenere errori
   di trascrizione. Segnala QUI, e solo qui, i valori che sospetti mal estratti
   PIU' che clinicamente reali. Basati su INCOERENZE, non sul semplice essere
   fuori range:
   - valori fisiologicamente impossibili (es. potassiemia di 45 mmol/L);
   - relazioni interne che non tornano (colesterolo totale molto diverso dalla
     somma di HDL, LDL e un quinto dei trigliceridi; ematocrito che non e' circa
     tre volte l'emoglobina; frazioni dell'elettroforesi che non sommano a 100);
   - un singolo valore che stona con tutto il resto del quadro (un esame epatico
     isolato altissimo con tutti gli altri marcatori di fegato normali).
   Un valore semplicemente fuori norma ma coerente col resto NON va qui: quello
   e' un dato clinico, non un errore. Se non trovi incoerenze di questo tipo,
   scrivi esattamente "Nessuna incoerenza sospetta.".
   Per ogni sospetto usa questo formato su una riga:
   `- [ANALITA] valore attuale — perche' e' incoerente`."""


def referto_con_analita(conn, analita: str):
    """Il referto piu' recente che contiene un dato analita.

    Serve a collegare un sospetto emerso in analisi al documento da riverificare.
    Il nome puo' arrivare come dicitura o come nome canonico: si prova entrambi.
    """
    nome = (analita or "").strip().upper()
    return conn.execute(
        """SELECT sha256, data_prelievo FROM risultati
           WHERE UPPER(analita) = ? OR UPPER(nome_referto) = ?
           ORDER BY data_prelievo DESC LIMIT 1""", (nome, nome)).fetchone()


def sospetti_da_analisi(testo: str) -> list[dict]:
    """Estrae dall'analisi le righe della sezione «Possibili errori di lettura».

    Il modello le formatta come `- [ANALITA] valore — motivo`. Qui le si
    riconosce per trasformarle in verifiche puntuali sul testo grezzo.
    """
    import re as _re

    if not testo:
        return []
    # isola la sezione fino all'intestazione successiva o alla fine
    m = _re.search(r"(?:Possibili errori di lettura|possibili errori)"
                   r"[^\n]*\n(.*?)(?:\n#{1,6}\s|\n\*\*\d|\Z)",
                   testo, _re.S | _re.I)
    if not m or "nessuna incoerenza" in m.group(1).lower():
        return []
    sospetti = []
    for riga in m.group(1).splitlines():
        riga = riga.strip()
        if not riga.startswith(("-", "*")):
            continue
        # con l'analita tra parentesi quadre, oppure senza
        v = (_re.match(r"[-*]\s*\[([^\]]+)\]\s*.+?\s*[—–-]\s*(.+)", riga)
             or _re.match(r"[-*]\s*([^—–]+?)\s*[—–]\s*(.+)", riga))
        if v:
            sospetti.append({"analita": v.group(1).strip(),
                             "motivo": v.group(2).strip()})
    return sospetti


def statistiche_analiti(conn) -> dict[str, dict]:
    """Statistiche calcolate su TUTTO l'archivio, una voce per analita.

    Sono i numeri che altrimenti il modello proverebbe a calcolare da solo:
    differenze, percentuali, conteggi. Qui sono esatti per costruzione.
    """
    righe = conn.execute(
        """SELECT analita, data_prelievo, valore, unita, flag FROM risultati
           WHERE valore IS NOT NULL ORDER BY analita, data_prelievo""").fetchall()
    per_analita: dict[str, list] = {}
    for r in righe:
        per_analita.setdefault(r["analita"], []).append(r)

    esiti = {}
    for analita, misure in per_analita.items():
        valori = [m["valore"] for m in misure]
        ultimo, primo = misure[-1], misure[0]
        prec = misure[-2] if len(misure) > 1 else None

        def variazione(riferimento, ultimo=ultimo):
            if not riferimento or not riferimento["valore"]:
                return None, None
            d = ultimo["valore"] - riferimento["valore"]
            return round(d, 3), round(d / riferimento["valore"] * 100, 1)

        d_prec, pc_prec = variazione(prec)
        _, pc_primo = variazione(primo if len(misure) > 1 else None)
        esiti[analita] = {
            "unita": ultimo["unita"], "n": len(misure),
            "ultimo": ultimo["valore"], "data_ultimo": ultimo["data_prelievo"],
            "primo": primo["valore"], "data_primo": primo["data_prelievo"],
            "delta_prec": d_prec, "perc_prec": pc_prec, "perc_primo": pc_primo,
            "minimo": min(valori), "massimo": max(valori),
            "fuori_range": sum(1 for m in misure if m["flag"] in ("H", "L")),
        }
    return esiti


def _tabella_statistiche(stat: dict[str, dict]) -> str:
    righe = ["## Numeri gia' calcolati (su tutto l'archivio, non ricalcolarli)",
             "",
             "| Analita | Ultimo | Δ prec. | Δ% prec. | Δ% dal primo | Min | Max | "
             "Misure | Volte fuori range |",
             "|---|---|---|---|---|---|---|---|---|"]
    for analita, d in sorted(stat.items()):
        def n(x, suffisso=""):
            return "-" if x is None else f"{x:g}{suffisso}"
        righe.append(
            f"| {analita} | {n(d['ultimo'])} {d['unita']} | {n(d['delta_prec'])} | "
            f"{n(d['perc_prec'], '%')} | {n(d['perc_primo'], '%')} | "
            f"{n(d['minimo'])} | {n(d['massimo'])} | {d['n']} | {d['fuori_range']} |")
    return "\n".join(righe)


def elenco_documenti(conn) -> list[sqlite3.Row]:
    """Documenti selezionabili come ambito di analisi, piu' recenti prima."""
    return conn.execute(
        """SELECT d.sha256, d.tipo, d.data_documento, d.titolo, d.struttura,
                  f.nome_file, COALESCE(c.n, 0) AS n_esami
           FROM documenti d
           JOIN file_processati f ON f.sha256 = d.sha256
           LEFT JOIN (SELECT sha256, COUNT(*) AS n FROM risultati
                      GROUP BY sha256) c ON c.sha256 = d.sha256
           ORDER BY d.data_documento DESC, f.ingerito_il DESC""").fetchall()


def _testo_documento(conn, sha: str) -> str:
    """Contenuto narrativo di un documento: testo integrale o, in mancanza, sintesi."""
    d = conn.execute(
        """SELECT d.tipo, d.data_documento, d.titolo, d.sintesi, d.conclusioni,
                  t.testo FROM documenti d LEFT JOIN testi t ON t.sha256 = d.sha256
           WHERE d.sha256 = ?""", (sha,)).fetchone()
    if not d:
        return ""
    corpo = (d["testo"] or "").strip()
    if not corpo:
        corpo = "\n".join(filter(None, [d["sintesi"], d["conclusioni"]]))
    if not corpo:
        return ""
    testa = etichetta_tipo(d["tipo"])
    if d["data_documento"]:
        testa += f" — {d['data_documento']}"
    return (f"## Referto in esame\n\n**{testa}**"
            + (f" · _{d['titolo']}_" if d["titolo"] else "") + f"\n\n{corpo}")


def _testi_per_tipo(conn, tipo: str | None, quanti: int) -> str:
    """Contenuto dei referti narrativi di una tipologia."""
    if not tipo:
        return ""
    righe = conn.execute(
        """SELECT d.sha256 FROM documenti d WHERE d.tipo = ?
           ORDER BY d.data_documento DESC LIMIT ?""", (tipo, quanti)).fetchall()
    blocchi = [_testo_documento(conn, r["sha256"]) for r in righe]
    blocchi = [b.replace("## Referto in esame\n\n", "") for b in blocchi if b]
    if not blocchi:
        return ""
    return (f"## Referti in esame — {etichetta_tipo(tipo)} "
            f"({len(blocchi)})\n\n" + "\n\n---\n\n".join(blocchi))


def costruisci_contesto(conn, n_referti: int = 4, brani: str = "",
                        statistiche: bool = True, sha: str | None = None,
                        tipo: str | None = None) -> str:
    """Riepilogo compatto in Markdown: profilo + ultimi referti con storico.

    Se `brani` e' valorizzato (passaggi recuperati per similarita'), sostituisce
    le sintesi dei referti narrativi: sono piu' pertinenti e piu' fedeli, perche'
    sono il testo originale invece di un riassunto.
    """
    parti = []
    p = leggi_profilo(conn)
    if p:
        valore_bmi = calcola_bmi(p.get("altezza_cm"), p.get("peso_kg"))
        bmi = f", BMI {valore_bmi}" if valore_bmi else ""
        eta = (f"{dt.date.today().year - int(p['anno_nascita'])} anni"
               if p.get("anno_nascita") else "non indicata")
        parti.append(
            f"## Profilo\n- Eta': {eta}\n- Sesso: {p.get('sesso') or 'non indicato'}\n"
            f"- Altezza/peso: {p.get('altezza_cm') or '?'} cm / "
            f"{p.get('peso_kg') or '?'} kg{bmi}\n"
            f"- Terapie in corso: {p.get('terapie') or 'nessuna indicata'}\n"
            f"- Note: {p.get('note') or '-'}")

    if sha:
        date = [r[0] for r in conn.execute(
            "SELECT DISTINCT data_prelievo FROM risultati WHERE sha256 = ?", (sha,))]
    elif tipo:
        date = [r[0] for r in conn.execute(
            """SELECT DISTINCT r.data_prelievo FROM risultati r
               JOIN documenti d ON d.sha256 = r.sha256
               WHERE d.tipo = ? ORDER BY r.data_prelievo DESC LIMIT ?""",
            (tipo, n_referti))]
    else:
        date = [r[0] for r in conn.execute(
            "SELECT DISTINCT data_prelievo FROM risultati "
            "ORDER BY data_prelievo DESC LIMIT ?", (n_referti,))]

    if not date:
        # ambito senza valori di laboratorio: puo' essere un referto narrativo
        narrativo = _testo_documento(conn, sha) if sha else _testi_per_tipo(conn, tipo,
                                                                           n_referti)
        if narrativo:
            return "\n\n".join(parti + [narrativo])
        return "\n\n".join(parti + ["## Esami\nNessun dato per l'ambito scelto."])

    # il filtro sulle date non basta: due referti di tipo diverso possono
    # condividere la stessa data, e le urine finirebbero tra le analisi del sangue
    filtro, parametri = "", list(date)
    if sha:
        filtro = " AND sha256 = ?"
        parametri.append(sha)
    elif tipo:
        filtro = (" AND sha256 IN (SELECT sha256 FROM documenti WHERE tipo = ?)")
        parametri.append(tipo)
    storico: dict[str, list] = {}
    for r in conn.execute(
        f"""SELECT data_prelievo, analita, valore_testo, unita, range_min,
                   range_max, flag, origine_range FROM risultati
            WHERE data_prelievo IN ({','.join('?' * len(date))}){filtro}
            ORDER BY analita, data_prelievo""", parametri):
        storico.setdefault(r["analita"], []).append(r)

    da_catalogo = False
    righe = [f"## Esami (ultimi {len(date)} referti: "
             f"{', '.join(sorted(date, reverse=True))})", "",
             "| Analita | Ultimo | Unita' | Riferimento | Stato | Precedenti |",
             "|---|---|---|---|---|---|"]
    for analita, valori in sorted(storico.items()):
        u = valori[-1]
        prec = " → ".join(f"{v['valore_testo']} ({v['data_prelievo']})"
                          for v in valori[:-1]) or "-"
        rif = "-"
        if u["range_min"] is not None or u["range_max"] is not None:
            rif = f"{u['range_min'] if u['range_min'] is not None else ''}–" \
                  f"{u['range_max'] if u['range_max'] is not None else ''}"
        stato = {"L": "BASSO", "H": "ALTO", "N": "nella norma"}.get(u["flag"] or "", "?")
        if u["origine_range"] == "catalogo":
            rif += " *"
            da_catalogo = True
        righe.append(f"| {analita} | {u['valore_testo']} | {u['unita']} | "
                     f"{rif} | {stato} | {prec} |")
    if da_catalogo:
        righe.append("\n\\* intervallo non presente sul referto, preso da un "
                     "catalogo generale di valori adulti: indicativo, puo' non "
                     "corrispondere al metodo del laboratorio.")
    parti.append("\n".join(righe))

    if statistiche:
        stat = statistiche_analiti(conn)
        if sha:  # solo gli analiti presenti nel referto in esame
            stat = {k: v for k, v in stat.items() if k in storico}
        if stat:
            parti.append(_tabella_statistiche(stat))

    if sha:
        testo_doc = _testo_documento(conn, sha)
        if testo_doc:
            parti.append(testo_doc)
        return "\n\n".join(parti)

    if tipo:  # ambito ristretto a una tipologia: niente referti di altro tipo
        return "\n\n".join(parti)

    if brani:
        parti.append(brani)
        return "\n\n".join(parti)

    narrativi = documenti_narrativi(conn)
    if narrativi:
        blocco = ["## Altri referti (ecografie, visite, imaging)"]
        for d in narrativi:
            testa = f"**{etichetta_tipo(d['tipo'])}"
            testa += f" — {d['data_documento']}**" if d["data_documento"] else "**"
            blocco.append(f"\n{testa}"
                          + (f"\n_{d['titolo']}_" if d["titolo"] else "")
                          + (f"\n{d['sintesi']}" if d["sintesi"] else "")
                          + (f"\nConclusioni: {d['conclusioni']}"
                             if d["conclusioni"] else ""))
        parti.append("\n".join(blocco))
    return "\n\n".join(parti)


# --- Ollama ----------------------------------------------------------------


class ErroreOllama(RuntimeError):
    """Errore di Ollama con il messaggio del server, non solo il codice HTTP."""


def post_ollama(payload: dict, url: str = OLLAMA_CHAT_URL,
                timeout: int = TIMEOUT_LLM):
    """POST verso Ollama. Traduce gli errori HTTP nel messaggio vero del server."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            dettaglio = json.loads(e.read()).get("error", "")
        except Exception:
            dettaglio = ""
        if "think" in dettaglio.lower() and "think" in payload:
            # il modello non supporta il ragionamento esplicito: riprova senza
            return post_ollama({k: v for k, v in payload.items() if k != "think"},
                               url, timeout)
        if e.code == 404:
            raise ErroreOllama(
                f"{dettaglio or 'risorsa non trovata'} — "
                f"scaricalo con: ollama pull {payload.get('model', '?')}") from None
        raise ErroreOllama(dettaglio or f"HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise ErroreOllama(f"Ollama non raggiungibile ({e.reason})") from None


def modelli_disponibili() -> list[str]:
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=5) as resp:
            return sorted(m["name"] for m in json.loads(resp.read())["models"])
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return []


def con_battito(azione, progress=None, ogni: int = 20, etichetta: str = ""):
    """Esegue azione() battendo un segnale nel progress ogni `ogni` secondi.

    Serve a mostrare che il processo e' vivo durante le chiamate lunghe al
    modello: senza, un'attesa di due minuti sembra un blocco. Il battito gira
    in un thread separato e si ferma appena l'azione finisce.
    """
    import threading
    import time

    if progress is None:
        return azione()

    stop = threading.Event()
    inizio = time.perf_counter()

    def batte():
        while not stop.wait(ogni):
            trascorsi = int(time.perf_counter() - inizio)
            progress(f"…ancora in corso{' — ' + etichetta if etichetta else ''} "
                     f"({trascorsi}s)")

    t = threading.Thread(target=batte, daemon=True)
    t.start()
    try:
        return azione()
    finally:
        stop.set()


def modelli_mancanti(scelti: dict) -> list[str]:
    """Modelli richiesti dalle funzioni ma non installati in Ollama.

    Il confronto ignora il tag :latest implicito, cosi' "qwen3:14b" combacia
    anche se Ollama lo elenca come "qwen3:14b". Lista vuota se Ollama non
    risponde: in quel caso l'errore emergera' alla chiamata, ma non blocchiamo
    a torto.
    """
    installati = modelli_disponibili()
    if not installati:
        return []
    def norm(m):
        return m if ":" in m else m + ":latest"
    presenti = {norm(m) for m in installati}
    richiesti = {norm(m) for m in scelti.values() if m}
    return sorted(m for m in richiesti if m not in presenti)


def log_server(righe: int = 60) -> tuple[str, str]:
    """(percorso, ultime righe) del log del server Ollama, se accessibile."""
    for percorso in LOG_OLLAMA:
        if percorso.exists():
            try:
                coda = percorso.read_text(encoding="utf-8",
                                          errors="replace").splitlines()[-righe:]
                return str(percorso), "\n".join(coda)
            except OSError as e:
                return str(percorso), f"non leggibile: {e}"
    suggerimento = {
        "linux": "journalctl -u ollama -n 60 -f",
        "win32": 'Get-Content "$env:LOCALAPPDATA\\Ollama\\server.log" -Tail 60 -Wait',
        "darwin": "tail -f ~/.ollama/logs/server.log",
    }.get(sys.platform, "consulta la documentazione di Ollama")
    return "", f"Nessun file di log trovato. Per seguirlo dal terminale: {suggerimento}"


def scarica_modello(nome: str) -> Iterator[dict]:
    """Esegue 'ollama pull' via API, restituendo gli stati di avanzamento."""
    with post_ollama({"model": nome, "stream": True},
                     OLLAMA_PULL_URL, TIMEOUT_PULL) as resp:
        for riga in resp:
            if not riga.strip():
                continue
            try:
                stato = json.loads(riga)
            except json.JSONDecodeError:
                continue
            if errore := stato.get("error"):
                raise ErroreOllama(errore)
            yield stato


def chat_con_strumenti(model: str, messaggi: list[dict], funzione: str,
                       definizioni: list[dict], esegui, avviso=None,
                       max_giri: int = 3) -> tuple[str, list[dict]]:
    """Ciclo di tool calling: il modello chiede, noi eseguiamo, lui risponde.

    Non e' in streaming: con i tool la risposta finale arriva comunque solo dopo
    l'ultimo giro, e la logica a piu' passaggi resta molto piu' leggibile.
    Restituisce (testo_finale, tracce_delle_chiamate).
    """
    cfg = FUNZIONI[funzione]
    conversazione = list(messaggi)
    tracce: list[dict] = []

    for giro in range(max_giri):
        payload = {"model": model, "messages": conversazione, "stream": False,
                   "think": cfg["think"], "tools": definizioni,
                   "options": {"temperature": cfg["temperature"],
                               "num_ctx": cfg["num_ctx"]}}
        with post_ollama(payload) as resp:
            messaggio = json.loads(resp.read().decode())["message"]

        chiamate = messaggio.get("tool_calls") or []
        if not chiamate:
            return messaggio.get("content", ""), tracce

        conversazione.append({"role": "assistant",
                              "content": messaggio.get("content", ""),
                              "tool_calls": chiamate})
        for chiamata in chiamate:
            f = chiamata.get("function", {})
            nome, argomenti = f.get("name", ""), f.get("arguments", {})
            if avviso:
                avviso(f"{nome}({', '.join(f'{k}={v}' for k, v in (argomenti or {}).items())})")
            risultato = esegui(nome, argomenti)
            tracce.append({"giro": giro + 1, "strumento": nome,
                           "argomenti": argomenti, "risultato": risultato})
            conversazione.append({"role": "tool", "tool_name": nome,
                                  "content": risultato})

    # esauriti i giri: si chiede la risposta senza piu' strumenti
    payload = {"model": model, "messages": conversazione, "stream": False,
               "think": cfg["think"],
               "options": {"temperature": cfg["temperature"],
                           "num_ctx": cfg["num_ctx"]}}
    with post_ollama(payload) as resp:
        return json.loads(resp.read().decode())["message"].get("content", ""), tracce


def chat_stream(model: str, messaggi: list[dict],
                funzione: str) -> Iterator[tuple[str, str]]:
    """Coppie (tipo, pezzo) con tipo in {"pensiero", "testo"}.

    I modelli con ragionamento esplicito (qwen3, deepseek-r1) emettono prima il
    campo `thinking` e solo dopo `content`: distinguerli evita di lasciare
    l'interfaccia vuota per tutta la fase di ragionamento.
    """
    cfg = FUNZIONI[funzione]
    payload = {"model": model, "messages": messaggi, "stream": True,
               "think": cfg["think"],
               "options": {"temperature": cfg["temperature"], "num_ctx": cfg["num_ctx"]}}
    with post_ollama(payload) as resp:
        for riga in resp:
            if not riga.strip():
                continue
            try:
                blocco = json.loads(riga)
            except json.JSONDecodeError:
                continue
            messaggio = blocco.get("message", {})
            if pensiero := messaggio.get("thinking"):
                yield "pensiero", pensiero
            if pezzo := messaggio.get("content"):
                yield "testo", pezzo
            if blocco.get("done"):
                # ultimo blocco: Ollama include i contatori della chiamata
                metriche = {
                    "token_in": blocco.get("prompt_eval_count") or 0,
                    "token_out": blocco.get("eval_count") or 0,
                    "durata_s": round((blocco.get("total_duration") or 0) / 1e9, 1),
                }
                yield "metriche", json.dumps(metriche)
                break


# --- Conversazioni ---------------------------------------------------------


def crea_conversazione(conn, titolo: str, modello: str) -> int:
    cur = conn.execute("INSERT INTO conversazioni (titolo, modello) VALUES (?,?)",
                       (titolo, modello))
    conn.commit()
    return int(cur.lastrowid)


def elenco_conversazioni(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM conversazioni ORDER BY id DESC").fetchall()


def aggiungi_messaggio(conn, conv_id: int, ruolo: str, contenuto: str) -> None:
    conn.execute("INSERT INTO messaggi (conversazione_id, ruolo, contenuto) "
                 "VALUES (?,?,?)", (conv_id, ruolo, contenuto))
    conn.commit()


def leggi_messaggi(conn, conv_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT ruolo, contenuto FROM messaggi "
                        "WHERE conversazione_id = ? ORDER BY id", (conv_id,)).fetchall()


def elimina_conversazione(conn, conv_id: int) -> None:
    conn.execute("DELETE FROM conversazioni WHERE id = ?", (conv_id,))
    conn.commit()
