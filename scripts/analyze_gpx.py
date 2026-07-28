#!/usr/bin/env python3
"""Analisi di un percorso GPX: profilo, salite, e pacing su CP/W' dell'atleta.

Solo stdlib: nessuna dipendenza da gpxpy/numpy (non installate nel progetto).

Il gradiente da quota GPS è rumoroso: campioni a 1 s producono oscillazioni di
diversi punti percentuali su strada piatta. Per questo si ricampiona a passo fisso
e si smussa PRIMA di derivare — le pendenze riportate sono medie di settore.

    python scripts/analyze_gpx.py percorso.gpx --cp 273 --wprime 28300
"""

from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
from typing import List, Tuple

NS = {"g": "http://www.topografix.com/GPX/1/1"}

# --- Fisica: massa, resistenze, aria -----------------------------------------
M_RIDER = 75.5        # kg (icu_weight)
M_BIKE = 9.0          # kg (bici + borracce + kit)
G = 9.80665
CRR = 0.004           # pneumatici da strada su asfalto buono
CDA_CLIMB = 0.34      # m^2, posizione in salita sulle prese alte
RHO = 1.19            # kg/m^3, ~200-400 m di quota, estate
ETA = 0.975           # efficienza trasmissione

RESAMPLE_M = 25.0     # passo di ricampionamento
SMOOTH_M = 150.0      # finestra di smussamento della quota


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_points(path: str) -> List[Tuple[float, float, float]]:
    root = ET.parse(path).getroot()
    pts = root.findall(".//g:trkpt", NS) or root.findall(".//g:rtept", NS)
    out = []
    for p in pts:
        ele_el = p.find("g:ele", NS)
        if ele_el is None or ele_el.text is None:
            continue
        out.append((float(p.get("lat")), float(p.get("lon")), float(ele_el.text)))
    return out


def resample(pts, step=RESAMPLE_M):
    """Ricampiona a passo costante: rende il gradiente confrontabile fra settori."""
    dist = [0.0]
    for i in range(1, len(pts)):
        dist.append(dist[-1] + haversine(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]))
    total = dist[-1]
    xs, es = [], []
    j = 0
    x = 0.0
    while x <= total:
        while j < len(dist) - 2 and dist[j + 1] < x:
            j += 1
        d0, d1 = dist[j], dist[j + 1]
        f = 0.0 if d1 <= d0 else (x - d0) / (d1 - d0)
        xs.append(x)
        es.append(pts[j][2] + f * (pts[j + 1][2] - pts[j][2]))
        x += step
    return xs, es, total


def smooth(values, window_pts):
    """Media mobile centrata. Il rumore altimetrico va tolto prima di derivare."""
    n = len(values)
    half = max(1, window_pts // 2)
    out = []
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        out.append(sum(values[a:b]) / (b - a))
    return out


def power_for_speed(v: float, grade: float) -> float:
    """Watt necessari a velocità v (m/s) su pendenza `grade` (frazione)."""
    theta = math.atan(grade)
    m = M_RIDER + M_BIKE
    f_roll = CRR * m * G * math.cos(theta)
    f_grav = m * G * math.sin(theta)
    f_agst = 0.5 * RHO * CDA_CLIMB * v * v
    return (f_roll + f_grav + f_agst) * v / ETA


def speed_for_power(p: float, grade: float) -> float:
    """Inversione numerica: velocità sostenibile a potenza p su pendenza grade."""
    lo, hi = 0.05, 30.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if power_for_speed(mid, grade) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def find_climbs(xs, es, min_gain=25.0, min_grade=0.02, bridge_m=250.0):
    """Salite: tratti in ascesa sostenuta, unendo brevi respiri intermedi."""
    step = xs[1] - xs[0]
    grades = [0.0]
    for i in range(1, len(es)):
        grades.append((es[i] - es[i - 1]) / step)
    runs = []
    start = None
    gap = 0.0
    for i, gr in enumerate(grades):
        if gr >= min_grade:
            if start is None:
                start = i
            gap = 0.0
        elif start is not None:
            gap += step
            if gap > bridge_m:
                runs.append((start, i - int(gap / step)))
                start, gap = None, 0.0
    if start is not None:
        runs.append((start, len(grades) - 1))

    climbs = []
    for a, b in runs:
        if b <= a:
            continue
        gain = es[b] - es[a]
        length = xs[b] - xs[a]
        if gain < min_gain or length < 200:
            continue
        # pendenza massima sostenuta su 200 m e su 500 m
        def max_sustained(win_m):
            k = max(1, int(win_m / step))
            best = 0.0
            for i in range(a, max(a + 1, b - k + 1)):
                j = min(b, i + k)
                if xs[j] > xs[i]:
                    best = max(best, (es[j] - es[i]) / (xs[j] - xs[i]))
            return best
        climbs.append({
            "start_km": xs[a] / 1000, "end_km": xs[b] / 1000,
            "length_m": length, "gain_m": gain,
            "avg_grade": gain / length,
            "max200": max_sustained(200), "max500": max_sustained(500),
            "top_ele": es[b],
        })
    return climbs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("gpx")
    ap.add_argument("--cp", type=float, default=273.0)
    ap.add_argument("--wprime", type=float, default=28300.0)
    a = ap.parse_args()

    pts = load_points(a.gpx)
    xs, es, total = resample(pts)
    es_s = smooth(es, int(SMOOTH_M / RESAMPLE_M))

    gain = sum(max(0.0, es_s[i] - es_s[i - 1]) for i in range(1, len(es_s)))
    loss = sum(max(0.0, es_s[i - 1] - es_s[i]) for i in range(1, len(es_s)))

    print("=" * 74)
    print(f"PERCORSO: {a.gpx.split('/')[-1]}   ({len(pts)} punti GPS)")
    print("=" * 74)
    print(f"  Distanza          {total/1000:8.2f} km")
    print(f"  Dislivello +      {gain:8.0f} m      (D- {loss:.0f} m)")
    print(f"  Quota min/max     {min(es_s):8.0f} / {max(es_s):.0f} m")
    print(f"  Dislivello/km     {gain/(total/1000):8.1f} m/km")
    delta = es_s[-1] - es_s[0]
    print(f"  Circuito?         {'sì (arrivo ~partenza)' if abs(delta) < 30 else f'no, dislivello netto {delta:+.0f} m'}")

    climbs = find_climbs(xs, es_s)
    print(f"\n  Salite rilevate (>=25 m di dislivello): {len(climbs)}")
    print("\n" + "=" * 74)
    print("SALITE")
    print("=" * 74)
    print(f"{'#':>2} {'km':>7} {'lung.':>7} {'D+':>6} {'media':>7} {'max200':>7} {'max500':>7}")
    for i, c in enumerate(climbs, 1):
        print(f"{i:>2} {c['start_km']:>7.1f} {c['length_m']:>6.0f}m {c['gain_m']:>5.0f}m"
              f" {c['avg_grade']*100:>6.1f}% {c['max200']*100:>6.1f}% {c['max500']*100:>6.1f}%")

    CP, WP = a.cp, a.wprime
    print("\n" + "=" * 74)
    print(f"PACING su CP={CP:.0f}W  W'={WP/1000:.1f}kJ   (massa {M_RIDER+M_BIKE:.1f} kg)")
    print("=" * 74)
    print("Per ogni salita: tempo e W' speso a tre intensità.\n")
    print(f"{'#':>2} {'lung.':>7} {'med%':>6} | " + " | ".join(
        f"{lab:>18}" for lab in ("a CP (273W)", "CP+20W (293W)", "CP+40W (313W)")))
    print("-" * 74)
    for i, c in enumerate(climbs, 1):
        row = f"{i:>2} {c['length_m']:>6.0f}m {c['avg_grade']*100:>5.1f}% | "
        cells = []
        for extra in (0, 20, 40):
            p = CP + extra
            v = speed_for_power(p, c["avg_grade"])
            t = c["length_m"] / v
            spent = extra * t
            cells.append(f"{int(t)//60:>2}'{int(t)%60:02d}\" {spent/1000:>5.1f}kJ")
        print(row + " | ".join(f"{c:>18}" for c in cells))

    print(f"\n  W' totale disponibile: {WP/1000:.1f} kJ")

    # --- La salita decisiva: il tetto imposto da W' -----------------------------
    final = max(climbs, key=lambda c: c["gain_m"])
    print("\n" + "=" * 74)
    print(f"SALITA DECISIVA — km {final['start_km']:.1f}, {final['length_m']/1000:.1f} km "
          f"al {final['avg_grade']*100:.1f}%, +{final['gain_m']:.0f} m")
    print("=" * 74)
    print(f"{'watt':>6} {'su CP':>7} {'tempo':>8} {'km/h':>6} {'W speso':>9}  esito")
    print("-" * 74)
    for p in (240, 250, 260, 270, 273, 281, 290, 300):
        v = speed_for_power(p, final["avg_grade"])
        t = final["length_m"] / v
        spent = max(0.0, (p - CP) * t)
        if spent <= 0:
            verdict = "sotto CP: sostenibile (se la durabilità tiene)"
        elif spent <= WP:
            verdict = f"OK — {100*spent/WP:.0f}% del W'"
        else:
            verdict = f"IMPOSSIBILE: serve {spent/1000:.0f} kJ, ne hai {WP/1000:.1f}"
        print(f"{p:>6} {p-CP:>+7.0f} {int(t)//60:>5}'{int(t)%60:02d}\" {v*3.6:>6.1f}"
              f" {spent/1000:>7.1f}kJ  {verdict}")

    # Tetto teorico: P = CP + W'/t, risolto iterativamente (t dipende da P)
    p = CP
    for _ in range(60):
        t = final["length_m"] / speed_for_power(p, final["avg_grade"])
        p = CP + WP / t
    print(f"\n  Tetto teorico con W' PIENO ai piedi: {p:.0f}W ({p-CP:+.0f} su CP) "
          f"in {int(t)//60}'{int(t)%60:02d}\"")
    print(f"  Cioè: su uno sforzo di ~{int(t)//60} minuti il W' vale solo "
          f"{WP/t:.0f}W di supplemento. La salita è un test di CP, non di W'.")

    # --- Profilo km per km della salita decisiva -------------------------------
    print(f"\n  Profilo km per km (pendenza media di ogni km):")
    a_i = min(range(len(xs)), key=lambda i: abs(xs[i] - final["start_km"] * 1000))
    b_i = min(range(len(xs)), key=lambda i: abs(xs[i] - final["end_km"] * 1000))
    step = xs[1] - xs[0]
    per_km = int(1000 / step)
    k = 0
    for i in range(a_i, b_i, per_km):
        j = min(b_i, i + per_km)
        if xs[j] <= xs[i]:
            continue
        gr = (es_s[j] - es_s[i]) / (xs[j] - xs[i])
        k += 1
        bar = "█" * max(1, int(gr * 100 * 2.5))
        print(f"    km {k:>2}  {gr*100:>5.1f}%  (quota {es_s[j]:>4.0f} m)  {bar}")

    # --- Salite brevi: dove W' conta davvero -----------------------------------
    shorts = [c for c in climbs if c is not final]
    print("\n" + "=" * 74)
    print("SALITE BREVI (il circuito) — qui W' è la valuta")
    print("=" * 74)
    if shorts:
        tot20 = sum(20 * (c["length_m"] / speed_for_power(CP + 20, c["avg_grade"])) for c in shorts)
        tot50 = sum(50 * (c["length_m"] / speed_for_power(CP + 50, c["avg_grade"])) for c in shorts)
        print(f"  {len(shorts)} salite, da {min(c['length_m'] for c in shorts):.0f} m "
              f"a {max(c['length_m'] for c in shorts):.0f} m")
        print(f"  Tutte a CP+20W → {tot20/1000:>5.1f} kJ ({100*tot20/WP:>3.0f}% del W', "
              "senza contare il recupero fra una e l'altra)")
        print(f"  Tutte a CP+50W → {tot50/1000:>5.1f} kJ ({100*tot50/WP:>3.0f}% del W')")
        print("  NB: fra le salite si recupera W' (tau ~8 min sotto CP), quindi il costo")
        print("      reale è inferiore — ma il margine non è infinito.")

    # --- Tempo e rifornimento --------------------------------------------------
    print("\n" + "=" * 74)
    print("DURATA E RIFORNIMENTO")
    print("=" * 74)
    flat_km = total / 1000 - sum(c["length_m"] for c in climbs) / 1000
    for label, vflat, pclimb in (("gruppo tranquillo", 34, 250), ("ritmo gara", 38, 265)):
        t_flat = flat_km / vflat * 3600
        t_climb = sum(c["length_m"] / speed_for_power(pclimb, c["avg_grade"]) for c in climbs)
        tot_s = t_flat + t_climb
        print(f"  {label:<20} ~{int(tot_s)//3600}h{(int(tot_s)%3600)//60:02d}"
              f"   (pianura {vflat} km/h, salite {pclimb}W)")
        print(f"    CHO a 80-90 g/h → {80*tot_s/3600:.0f}-{90*tot_s/3600:.0f} g totali")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
