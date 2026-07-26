#!/usr/bin/env python3
"""Hook UserPromptSubmit: inietta una "scheda stato atleta" da data/kb.sqlite3.

Scopo (anti-allucinazione / anti-dimenticanza): mettere la VERITÀ DI RIFERIMENTO nel
contesto PRIMA che il modello risponda, così non si affida alla memoria sfocata
(fitness, wellness, volume reale, prossime gare, pianificato, date test).

Contratto: read-only, deterministico, e **non deve mai bloccare il prompt** — su
qualsiasi errore stampa una riga di fallback (o niente) ed esce 0.
"""
import json
import os
import sqlite3
import statistics
import sys

AID = "i215294"


def _r(x, nd=0):
    try:
        return round(float(x), nd) if nd else int(round(float(x)))
    except (TypeError, ValueError):
        return "?"


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(here, "..", "data", "kb.sqlite3")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    def q(sql, args=()):
        return conn.execute(sql, args).fetchall()

    # "oggi" = ultimo giorno con un dato MISURATO (hrv/rhr/sonno). NON usare MAX(date):
    # intervals.icu proietta CTL/ATL nel futuro sul pianificato → falserebbe lo stato.
    trow = q("SELECT MAX(date) d FROM athlete_timeseries WHERE athlete_id=? "
             "AND metric_type IN ('hrv','resting_hr','sleep')", (AID,))
    today = trow[0]["d"] if trow and trow[0]["d"] else None
    if not today:
        return

    def latest(metric):
        # ultimo valore NON oltre 'oggi' (esclude le proiezioni future di CTL/ATL/TSB)
        r = q("SELECT json_extract(data,'$.value') v FROM athlete_timeseries "
              "WHERE athlete_id=? AND metric_type=? AND date<=? ORDER BY date DESC LIMIT 1",
              (AID, metric, today))
        return r[0]["v"] if r else None

    ctl, atl, tsb = latest("ctl"), latest("atl"), latest("tsb")
    hrv, rhr = latest("hrv"), latest("resting_hr")
    sl = q("SELECT json_extract(data,'$.value')/3600.0 h FROM athlete_timeseries "
           "WHERE athlete_id=? AND metric_type='sleep' ORDER BY date DESC LIMIT 2", (AID,))
    sleep_now = sl[0]["h"] if sl else None
    sleep_prev = sl[1]["h"] if len(sl) > 1 else None

    def baseline(metric):
        vals = [r["v"] for r in q(
            "SELECT json_extract(data,'$.value') v FROM athlete_timeseries "
            "WHERE athlete_id=? AND metric_type=? AND date>=date(?, '-45 day')",
            (AID, metric, today)) if r["v"] is not None]
        if len(vals) >= 3:
            return statistics.mean(vals), statistics.pstdev(vals)
        return None, None

    hrv_m, hrv_sd = baseline("hrv")
    rhr_m, rhr_sd = baseline("resting_hr")

    p20_rec = p20_all = None
    pc = q("SELECT data FROM athlete_timeseries WHERE athlete_id=? AND metric_type='power_curve' "
           "ORDER BY date DESC LIMIT 1", (AID,))
    if pc:
        per = (json.loads(pc[0]["data"]).get("extra") or {}).get("periods", {})
        p20_rec = (per.get("42 days", {}).get("secs_watts", {}) or {}).get("1200")
        p20_all = (per.get("All time", {}).get("secs_watts", {}) or {}).get("1200")

    wk = q("SELECT strftime('%Y-W%W', date) w, "
           "ROUND(SUM(json_extract(data,'$.moving_time_s'))/3600.0,1) h, "
           "ROUND(SUM(COALESCE(json_extract(data,'$.load'),0))) tss "
           "FROM activities WHERE athlete_id=? AND json_extract(data,'$.type') IS NOT NULL "
           "AND date>=date(?, '-28 day') GROUP BY w ORDER BY w DESC LIMIT 4", (AID, today))
    races = q("SELECT json_extract(data,'$.date') d, json_extract(data,'$.name') n, "
              "json_extract(data,'$.priority') p FROM races WHERE athlete_id=? "
              "AND json_extract(data,'$.date')>=? ORDER BY d LIMIT 4", (AID, today))
    plan = q("SELECT date, json_extract(data,'$.name') n, json_extract(data,'$.load_target') l "
             "FROM planned_workouts WHERE athlete_id=? AND date>=? AND date<=date(?, '+8 day') "
             "ORDER BY date LIMIT 8", (AID, today, today))
    tests = q("SELECT json_extract(data,'$.planned_date') d FROM assessments WHERE athlete_id=? "
              "AND json_extract(data,'$.protocol')='ftp' AND json_extract(data,'$.planned_date')>=? "
              "ORDER BY d", (AID, today))

    out = []
    out.append("=== STATO ATLETA (auto da kb.sqlite3 — VERITÀ DI RIFERIMENTO, non citare a memoria) ===")
    out.append(f"Aggiornato al {today} (ultimo giorno sincronizzato).")
    out.append(f"FITNESS: CTL {_r(ctl)} · ATL {_r(atl)} · TSB {_r(tsb)}")
    hrv_b = f" (base {_r(hrv_m,1)}±{_r(hrv_sd,1)}, SWC≈{_r(hrv_m-0.5*hrv_sd,1)})" if hrv_m else ""
    rhr_b = f" (base {_r(rhr_m,1)}±{_r(rhr_sd,1)})" if rhr_m else ""
    slp = f" · sonno {_r(sleep_now,1)}h" + (f" (ieri {_r(sleep_prev,1)}h)" if sleep_prev else "") + " [target≥7.5]"
    out.append(f"WELLNESS: HRV {_r(hrv)}{hrv_b} · RHR {_r(rhr)}{rhr_b}{slp}")
    if wk:
        vol = " · ".join(f"{r['h']}h/{_r(r['tss'])}TSS" for r in reversed(wk))
        out.append(f"VOLUME sett (ultime 4): {vol}  [carico reale ~14-16h, NON lowballare]")
    if p20_rec or p20_all:
        ftp_r = _r(p20_rec * 0.95) if p20_rec else "?"
        ftp_a = _r(p20_all * 0.95) if p20_all else "?"
        out.append(f"POTENZA: 20min recente {_r(p20_rec)}W (FTP~{ftp_r}) · assoluto {_r(p20_all)}W (FTP~{ftp_a})")
    if races:
        out.append("PROSSIME GARE: " + " · ".join(
            f"{r['d']} {r['n']} [{r['p']}]" for r in races))
    else:
        out.append("PROSSIME GARE: nessuna nel DB — CHIEDI il calendario prima di pianificare.")
    if plan:
        out.append("PIANIFICATO (oggi→+8gg): " + " · ".join(
            f"{r['date'][5:]} {r['n']}" + (f"({_r(r['l'])})" if r['l'] else "") for r in plan))
    if tests:
        out.append("TEST FTP pianificati: " + " · ".join(t["d"] for t in tests))
    out.append("NB: il pianificato = calendario (planned_workouts+races), NON il piano interno. "
               "Leggi il calendario PRIMA di pianificare/pushare (pull, non push cieco).")
    out.append("=== fine scheda ===")
    print("\n".join(out))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # non bloccare MAI il prompt
        print(f"[athlete_state_card: scheda non disponibile ({type(e).__name__})]", file=sys.stdout)
        sys.exit(0)
