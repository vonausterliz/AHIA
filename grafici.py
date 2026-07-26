"""AHIA — grafici temporali degli analiti (Altair)."""

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

import altair as alt
import pandas as pd

COLORI = {"N": "#2e7d32", "H": "#c62828", "L": "#1565c0", "": "#616161"}
STATI = {"N": "nella norma", "H": "alto", "L": "basso", "": "senza riferimento"}
_SCALA = alt.Scale(domain=list(COLORI), range=list(COLORI.values()))


def serie_df(conn, analiti: list[str]) -> pd.DataFrame:
    """Serie storica in formato lungo per gli analiti richiesti."""
    if not analiti:
        return pd.DataFrame()
    righe = conn.execute(
        f"""SELECT id, analita, data_prelievo, valore, valore_testo, unita,
                   range_min, range_max, flag, laboratorio, origine_range
            FROM risultati
            WHERE analita IN ({','.join('?' * len(analiti))}) AND valore IS NOT NULL
            ORDER BY analita, data_prelievo, id""", analiti).fetchall()
    df = pd.DataFrame([dict(r) for r in righe])
    if df.empty:
        return df
    df["data"] = pd.to_datetime(df["data_prelievo"], errors="coerce")
    df = df.dropna(subset=["data"])
    # Due referti dello stesso giorno per lo stesso esame darebbero due punti
    # sulla stessa ascissa e un segmento verticale: si tiene l'ultimo caricato.
    df = df.drop_duplicates(subset=["analita", "data"], keep="last")
    df["flag"] = df["flag"].fillna("")
    df["stato"] = df["flag"].map(STATI)
    df["origine_range"] = df["origine_range"].fillna("")
    df["riferimento"] = df["origine_range"].map(
        {"referto": "dal referto", "catalogo": "dal catalogo (indicativo)"}
    ).fillna("assente")
    return df


def _indice(riga: pd.Series) -> float | None:
    """Posizione nel proprio intervallo, normalizzata: dentro 0-1 = nella norma.

    Permette di confrontare sullo stesso grafico analiti con unita' diverse.
    La convenzione e' sempre la stessa: fuori dalla fascia 0-1 = fuori range.
      - intervallo chiuso  -> (v - min) / (max - min)
      - solo massimo       -> v / max          (oltre 1 = troppo alto)
      - solo minimo        -> min / v          (oltre 1 = troppo basso)
    Nell'ultimo caso l'indice e' invertito rispetto al valore: scende quando
    l'esame migliora. E' il prezzo per mantenere una sola lettura della fascia.
    """
    v, lo, hi = riga["valore"], riga["range_min"], riga["range_max"]
    if pd.notna(lo) and pd.notna(hi) and hi != lo:
        return (v - lo) / (hi - lo)
    if pd.notna(hi) and hi:
        return v / hi
    if pd.notna(lo) and lo and v:
        return lo / v
    return None


def _range_testo(riga) -> str:
    lo, hi = riga["range_min"], riga["range_max"]
    if pd.isna(lo) and pd.isna(hi):
        return "-"
    if pd.isna(lo):
        return f"< {hi:g}"
    if pd.isna(hi):
        return f"> {lo:g}"
    return f"{lo:g} – {hi:g}"


def tabella_variazioni(df: pd.DataFrame) -> pd.DataFrame:
    """Ultimo valore, variazione sul precedente e sul primo disponibile."""
    def delta(ultimo, rif):
        if rif is None or not rif["valore"]:
            return None, None
        d = ultimo["valore"] - rif["valore"]
        return round(d, 3), round(d / rif["valore"] * 100, 1)

    voci = []
    for analita, g in df.groupby("analita"):
        g = g.sort_values("data")
        u = g.iloc[-1]
        d_prec, p_prec = delta(u, g.iloc[-2] if len(g) > 1 else None)
        _, p_primo = delta(u, g.iloc[0] if len(g) > 1 else None)
        voci.append({"Analita": analita, "Ultimo": u["valore_testo"],
                     "Unita'": u["unita"], "Data": u["data"].date().isoformat(),
                     "Stato": u["stato"], "Δ prec.": d_prec, "Δ% prec.": p_prec,
                     "Δ% dal primo": p_primo, "Misurazioni": len(g),
                     "Riferimento": _range_testo(u)
                     + (" *" if u["origine_range"] == "catalogo" else "")})
    return pd.DataFrame(voci)


def _asse_tempo(d: pd.DataFrame, titolo=None) -> alt.X:
    """Asse temporale onesto: nessun arrotondamento del dominio.

    Vega-Lite di default estende il dominio a un confine "tondo": con l'ultimo
    prelievo al 29 giugno compariva una tacca di luglio, che si legge come una
    misurazione inesistente. Con pochi punti si mette una tacca esattamente su
    ogni data reale.
    """
    date = sorted(d["data"].dt.strftime("%Y-%m-%dT00:00:00").unique())
    asse = alt.Axis(format="%d/%m/%y", labelAngle=-40)
    if len(date) <= 12:
        asse = alt.Axis(format="%d/%m/%y", labelAngle=-40, values=list(date))
    return alt.X("data:T", title=titolo,
                 scale=alt.Scale(nice=False, padding=18), axis=asse)


def _margine_asse(d: pd.DataFrame) -> tuple[float, float]:
    """Estremi verticali del grafico: minimo e massimo tra valori e intervalli,
    con un piccolo margine, così le fasce fuori norma arrivano fino ai bordi."""
    import pandas as _pd
    serie = _pd.concat([d["valore"], d["range_min"], d["range_max"]]).dropna()
    if serie.empty:
        return (0.0, 1.0)
    lo, hi = float(serie.min()), float(serie.max())
    if lo == hi:
        return (lo - 1, hi + 1)
    m = (hi - lo) * 0.08
    return (lo - m, hi + m)


def grafico_analita(df: pd.DataFrame, analita: str, altezza: int = 260):
    """Serie di un singolo analita: fasce fuori norma in rosso, banda normale.

    Le zone fuori dall'intervallo di riferimento sono colorate di rosso chiaro
    (sopra il massimo e sotto il minimo), così si vede a colpo d'occhio quando un
    punto cade fuori norma senza dover leggere i numeri. La banda normale resta
    tenue sullo sfondo.
    """
    d = df[df["analita"] == analita].sort_values("data")
    unita = d["unita"].iloc[-1] if not d.empty else ""
    titolo = f"{analita} ({unita})" if unita else analita
    # verde se l'intervallo lo dichiara il laboratorio, grigio-azzurro se viene
    # dal catalogo: la differenza deve saltare all'occhio senza leggere note
    da_catalogo = (d["origine_range"] == "catalogo").any()
    colore_banda = "#5c6bc0" if da_catalogo else "#2e7d32"
    dominio = _margine_asse(d)
    y = alt.Y("valore:Q", title=titolo,
              scale=alt.Scale(zero=False, domain=list(dominio)))

    strati = []
    banda = d.dropna(subset=["range_min", "range_max"])
    if not banda.empty:
        # fasce fuori norma in rosso chiaro: dal massimo verso l'alto e dal
        # minimo verso il basso, fino ai bordi del grafico.
        fuori = banda.assign(alto=dominio[1], basso=dominio[0])
        rosso = "#e53935"
        strati.append(alt.Chart(fuori).mark_area(opacity=0.12,
                                                 color=rosso).encode(
            x=_asse_tempo(d), y=alt.Y("range_max:Q", title=titolo),
            y2="alto:Q"))
        strati.append(alt.Chart(fuori).mark_area(opacity=0.12,
                                                 color=rosso).encode(
            x=_asse_tempo(d), y=alt.Y("range_min:Q", title=titolo),
            y2="basso:Q"))
        # banda normale, tenue, sopra le fasce rosse
        strati.append(alt.Chart(banda).mark_area(opacity=0.16,
                                                 color=colore_banda).encode(
            x=_asse_tempo(d), y=alt.Y("range_min:Q", title=titolo),
            y2="range_max:Q"))
    else:
        # intervallo aperto da un lato: una tratteggiata sull'estremo noto
        limiti = d.melt(id_vars="data", value_vars=["range_min", "range_max"],
                        value_name="limite").dropna(subset=["limite"])
        if not limiti.empty:
            strati.append(alt.Chart(limiti).mark_line(
                strokeDash=[5, 4], color="#9e9e9e", size=1).encode(
                x=_asse_tempo(d), y=alt.Y("limite:Q", title=titolo)))

    strati.append(alt.Chart(d).mark_line(color="#37474f", size=2).encode(
        x=_asse_tempo(d), y=y))
    strati.append(alt.Chart(d).mark_point(size=90, filled=True).encode(
        x=_asse_tempo(d), y=y,
        color=alt.Color("flag:N", scale=_SCALA, legend=None),
        tooltip=[alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
                 alt.Tooltip("valore_testo:N", title="Valore"),
                 alt.Tooltip("unita:N", title="Unita'"),
                 alt.Tooltip("stato:N", title="Stato"),
                 alt.Tooltip("riferimento:N", title="Intervallo"),
                 alt.Tooltip("laboratorio:N", title="Laboratorio")]))
    return alt.layer(*strati).properties(height=altezza).interactive(bind_y=False)


def grafico_comparativo(df: pd.DataFrame, altezza: int = 380):
    """Piu' analiti sullo stesso grafico, normalizzati sul proprio intervallo."""
    d = df.assign(indice=df.apply(_indice, axis=1)).dropna(subset=["indice"])
    fascia = alt.Chart(pd.DataFrame({"lo": [0], "hi": [1]})).mark_rect(
        opacity=0.12, color="#2e7d32").encode(y="lo:Q", y2="hi:Q")
    linee = alt.Chart(d).mark_line(size=2, point=True).encode(
        x=_asse_tempo(d),
        y=alt.Y("indice:Q", title="Indice normalizzato (fuori da 0-1 = fuori range)"),
        color=alt.Color("analita:N", title="Analita"),
        tooltip=[alt.Tooltip("analita:N", title="Analita"),
                 alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
                 alt.Tooltip("valore_testo:N", title="Valore"),
                 alt.Tooltip("unita:N", title="Unita'"),
                 alt.Tooltip("indice:Q", title="Indice", format=".2f"),
                 alt.Tooltip("stato:N", title="Stato")])
    return alt.layer(fascia, linee).properties(height=altezza).interactive(bind_y=False)


def heatmap_stati(df: pd.DataFrame, altezza: int = 300):
    """Griglia analita × prelievo con lo stato di ogni misurazione."""
    return alt.Chart(df).mark_rect(stroke="white", strokeWidth=1).encode(
        x=alt.X("yearmonthdate(data):O", title=None,
                axis=alt.Axis(format="%d/%m/%y", labelAngle=-45)),
        y=alt.Y("analita:N", title=None),
        color=alt.Color("flag:N", title="Stato", scale=_SCALA),
        tooltip=[alt.Tooltip("analita:N", title="Analita"),
                 alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
                 alt.Tooltip("valore_testo:N", title="Valore"),
                 alt.Tooltip("unita:N", title="Unita'"),
                 alt.Tooltip("stato:N", title="Stato")]).properties(height=altezza)
