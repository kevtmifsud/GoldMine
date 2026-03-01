#!/usr/bin/env python3
"""Generate realistic portfolio trade data for Flagship and Long Only portfolios.

Uses real prices from stock_history.csv and stock universe from stocks.csv.
Simulates two portfolios from Jan 2022 to Feb 2026 with monthly rebalancing.

Flagship: $600M AUM, long/short market-neutral, sector-neutral
  - 50 longs ($300M) + 50 shorts ($300M), ~$6M per position
  - Monthly rebalancing with 1-3 name replacements per side

Long Only: $500M AUM, long only
  - ~80 positions with jittered weights, 15% max position, 50% max sector
  - Monthly rebalancing with 1-4 name replacements

Output: data/structured/portfolio_trades.csv
Columns: date,ticker,action,shares,price,portfolio,side
"""

import csv
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOCKS_CSV = ROOT / "data" / "structured" / "stocks.csv"
HISTORY_CSV = ROOT / "data" / "structured" / "stock_history.csv"
OUTPUT_CSV = ROOT / "data" / "structured" / "portfolio_trades.csv"
PORTFOLIOS_CSV = ROOT / "data" / "structured" / "portfolios.csv"
DATASETS_CSV = ROOT / "data" / "structured" / "datasets.csv"

SEED = 42


def load_stocks():
    """Return dict of ticker -> sector from stocks.csv."""
    stocks = {}
    with open(STOCKS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            stocks[row["ticker"]] = row["sector"]
    return stocks


def load_price_history():
    """Return nested dict prices[date][ticker] = close from stock_history.csv."""
    prices = defaultdict(dict)
    with open(HISTORY_CSV, newline="") as f:
        for row in csv.DictReader(f):
            prices[row["date"]][row["ticker"]] = float(row["close"])
    return dict(prices)


def get_rebalance_dates(prices):
    """Return first trading day of each month from Jan 2022 onward."""
    dates = sorted(d for d in prices if d >= "2022-01")
    result, seen = [], set()
    for d in dates:
        ym = d[:7]
        if ym not in seen:
            seen.add(ym)
            result.append(d)
    return result


def proportional_alloc(sector_sizes, total):
    """Allocate total slots across sectors proportionally, min 1 each."""
    grand = sum(sector_sizes.values())
    exact = {s: n / grand * total for s, n in sector_sizes.items()}
    result = {s: max(1, int(v)) for s, v in exact.items()}
    diff = sum(result.values()) - total
    if diff > 0:
        for s in sorted(result, key=lambda s: result[s], reverse=True):
            if diff == 0:
                break
            if result[s] > 1:
                result[s] -= 1
                diff -= 1
    elif diff < 0:
        remainders = {s: exact[s] - result[s] for s in exact}
        for s in sorted(remainders, key=lambda s: remainders[s], reverse=True):
            if diff == 0:
                break
            result[s] += 1
            diff += 1
    return result


def main():
    random.seed(SEED)
    print("Loading data...")
    stocks = load_stocks()
    prices = load_price_history()
    dates = get_rebalance_dates(prices)
    start = dates[0]
    print(f"Rebalance dates: {len(dates)} ({start} to {dates[-1]})")

    # Eligible tickers: have price on start date and appear in stocks.csv
    eligible = sorted(t for t in prices[start] if t in stocks)
    print(f"Eligible tickers: {len(eligible)}")

    # Group by sector, shuffle within each
    by_sector = defaultdict(list)
    for t in eligible:
        by_sector[stocks[t]].append(t)
    for v in by_sector.values():
        random.shuffle(v)
    sector_sizes = {s: len(ts) for s, ts in by_sector.items()}
    for s in sorted(sector_sizes):
        print(f"  {s}: {sector_sizes[s]}")

    # ── Flagship ticker selection (50 long + 50 short) ──
    f_alloc = proportional_alloc(sector_sizes, 50)
    f_longs, f_shorts = [], []
    for s in sorted(f_alloc):
        n = min(f_alloc[s], len(by_sector[s]) // 2)
        f_longs.extend(by_sector[s][:n])
        f_shorts.extend(by_sector[s][n : 2 * n])

    # ── Long Only ticker selection (~80) ──
    lo_alloc = proportional_alloc(sector_sizes, 80)
    lo_tickers = []
    for s in sorted(lo_alloc):
        n = min(lo_alloc[s], len(by_sector[s]))
        lo_tickers.extend(random.sample(by_sector[s], n))

    print(f"\nFlagship: {len(f_longs)} longs + {len(f_shorts)} shorts")
    print(f"Long Only: {len(lo_tickers)} positions")
    flagship_set = set(f_longs) | set(f_shorts)
    print(f"Overlap with Flagship: {len(set(lo_tickers) & flagship_set)}")

    trades = []
    sp = prices[start]

    # ═══════════ Flagship initialization ═══════════
    f_pos = {}  # ticker -> {sh, side, sec, tgt}
    tgt_l = 300_000_000 / max(len(f_longs), 1)
    tgt_s = 300_000_000 / max(len(f_shorts), 1)

    for t in f_longs:
        sh = max(1, round(tgt_l / sp[t]))
        f_pos[t] = {"sh": sh, "side": "long", "sec": stocks[t], "tgt": tgt_l}
        trades.append(dict(date=start, ticker=t, action="buy", shares=sh,
                           price=round(sp[t], 2), portfolio="Flagship", side="long"))

    for t in f_shorts:
        sh = max(1, round(tgt_s / sp[t]))
        f_pos[t] = {"sh": sh, "side": "short", "sec": stocks[t], "tgt": tgt_s}
        trades.append(dict(date=start, ticker=t, action="sell", shares=sh,
                           price=round(sp[t], 2), portfolio="Flagship", side="short"))

    # Available replacement pool for Flagship
    f_avail = defaultdict(list)
    for t in eligible:
        if t not in f_pos:
            f_avail[stocks[t]].append(t)
    for v in f_avail.values():
        random.shuffle(v)

    # ═══════════ Long Only initialization ═══════════
    lo_pos = {}
    base = 500_000_000 / max(len(lo_tickers), 1)
    lo_tgts = {}
    for t in lo_tickers:
        lo_tgts[t] = min(base * random.uniform(0.5, 2.5), 75_000_000)

    # Scale to $500M
    raw_sum = sum(lo_tgts.values())
    if raw_sum > 0:
        for t in lo_tgts:
            lo_tgts[t] = min(lo_tgts[t] * 500_000_000 / raw_sum, 75_000_000)

    # Sector cap: no sector > $250M
    sec_sums = defaultdict(float)
    for t, v in lo_tgts.items():
        sec_sums[stocks[t]] += v
    for sec, total in sec_sums.items():
        if total > 250_000_000:
            r = 250_000_000 / total
            for t in lo_tgts:
                if stocks[t] == sec:
                    lo_tgts[t] *= r

    for t in lo_tickers:
        sh = max(1, round(lo_tgts[t] / sp[t]))
        lo_pos[t] = {"sh": sh, "side": "long", "sec": stocks[t], "tgt": lo_tgts[t]}
        trades.append(dict(date=start, ticker=t, action="buy", shares=sh,
                           price=round(sp[t], 2), portfolio="Long Only", side="long"))

    lo_avail = defaultdict(list)
    for t in eligible:
        if t not in lo_pos:
            lo_avail[stocks[t]].append(t)
    for v in lo_avail.values():
        random.shuffle(v)

    # ═══════════ Monthly rebalancing ═══════════
    for date in dates[1:]:
        dp = prices.get(date, {})
        if not dp:
            continue

        # ── Flagship turnover ──
        for side, tgt in [("long", tgt_l), ("short", tgt_s)]:
            current = [t for t in f_pos if f_pos[t]["side"] == side and t in dp]
            if not current:
                continue
            n_replace = min(random.randint(1, 3), max(1, len(current) - 5))
            removed = random.sample(current, n_replace)
            removed_set = set(removed)
            sectors_needed = []

            for old in removed:
                pos = f_pos.pop(old)
                act = "sell" if side == "long" else "buy"
                trades.append(dict(date=date, ticker=old, action=act,
                                   shares=pos["sh"], price=round(dp[old], 2),
                                   portfolio="Flagship", side=side))
                f_avail[pos["sec"]].append(old)
                sectors_needed.append(pos["sec"])

            for sec in sectors_needed:
                cands = [t for t in f_avail.get(sec, [])
                         if t in dp and t not in f_pos and t not in removed_set]
                if cands:
                    new = cands[0]
                    f_avail[sec].remove(new)
                    sh = max(1, round(tgt / dp[new]))
                    f_pos[new] = {"sh": sh, "side": side, "sec": sec, "tgt": tgt}
                    act = "buy" if side == "long" else "sell"
                    trades.append(dict(date=date, ticker=new, action=act,
                                       shares=sh, price=round(dp[new], 2),
                                       portfolio="Flagship", side=side))

        # ── Flagship drift rebalance ──
        for t in list(f_pos):
            if t not in dp:
                continue
            pos = f_pos[t]
            val = pos["sh"] * dp[t]
            if abs(val - pos["tgt"]) / pos["tgt"] > 0.15:
                new_sh = max(1, round(pos["tgt"] / dp[t]))
                diff = new_sh - pos["sh"]
                if diff == 0:
                    continue
                if diff > 0:
                    act = "buy" if pos["side"] == "long" else "sell"
                else:
                    act = "sell" if pos["side"] == "long" else "buy"
                trades.append(dict(date=date, ticker=t, action=act,
                                   shares=abs(diff), price=round(dp[t], 2),
                                   portfolio="Flagship", side=pos["side"]))
                pos["sh"] = new_sh

        # ── Long Only turnover ──
        lo_current = [t for t in lo_pos if t in dp]
        if lo_current:
            n_replace = min(random.randint(1, 4), max(1, len(lo_current) - 5))
            lo_removed = random.sample(lo_current, n_replace)
            lo_removed_set = set(lo_removed)
            lo_sectors = []

            for old in lo_removed:
                pos = lo_pos.pop(old)
                trades.append(dict(date=date, ticker=old, action="sell",
                                   shares=pos["sh"], price=round(dp[old], 2),
                                   portfolio="Long Only", side="long"))
                lo_avail[pos["sec"]].append(old)
                lo_sectors.append((pos["sec"], pos["tgt"]))

            for sec, t_tgt in lo_sectors:
                cands = [t for t in lo_avail.get(sec, [])
                         if t in dp and t not in lo_pos and t not in lo_removed_set]
                if cands:
                    new = cands[0]
                    lo_avail[sec].remove(new)
                    sh = max(1, round(t_tgt / dp[new]))
                    lo_pos[new] = {"sh": sh, "side": "long", "sec": sec, "tgt": t_tgt}
                    trades.append(dict(date=date, ticker=new, action="buy",
                                       shares=sh, price=round(dp[new], 2),
                                       portfolio="Long Only", side="long"))

        # ── Long Only drift rebalance ──
        for t in list(lo_pos):
            if t not in dp:
                continue
            pos = lo_pos[t]
            val = pos["sh"] * dp[t]
            if abs(val - pos["tgt"]) / pos["tgt"] > 0.15:
                new_sh = max(1, round(pos["tgt"] / dp[t]))
                diff = new_sh - pos["sh"]
                if diff == 0:
                    continue
                act = "buy" if diff > 0 else "sell"
                trades.append(dict(date=date, ticker=t, action=act,
                                   shares=abs(diff), price=round(dp[t], 2),
                                   portfolio="Long Only", side="long"))
                pos["sh"] = new_sh

        # ── Long Only: position cap >15% ($75M) → trim to 12% ($60M) ──
        for t in list(lo_pos):
            if t not in dp:
                continue
            pos = lo_pos[t]
            val = pos["sh"] * dp[t]
            if val > 75_000_000:
                new_tgt = 60_000_000
                new_sh = max(1, round(new_tgt / dp[t]))
                diff = pos["sh"] - new_sh
                if diff > 0:
                    trades.append(dict(date=date, ticker=t, action="sell",
                                       shares=diff, price=round(dp[t], 2),
                                       portfolio="Long Only", side="long"))
                    pos["sh"] = new_sh
                    pos["tgt"] = new_tgt

        # ── Long Only: sector cap >50% ($250M) → trim to 45% ($225M) ──
        sec_vals = defaultdict(float)
        for t, pos in lo_pos.items():
            if t in dp:
                sec_vals[pos["sec"]] += pos["sh"] * dp[t]
        for sec, total in sec_vals.items():
            if total > 250_000_000:
                ratio = 225_000_000 / total
                for t in list(lo_pos):
                    pos = lo_pos[t]
                    if pos["sec"] == sec and t in dp:
                        new_sh = max(1, round(pos["sh"] * ratio))
                        diff = pos["sh"] - new_sh
                        if diff > 0:
                            trades.append(dict(date=date, ticker=t, action="sell",
                                               shares=diff, price=round(dp[t], 2),
                                               portfolio="Long Only", side="long"))
                            pos["sh"] = new_sh

    # ═══════════ Write output ═══════════
    trades.sort(key=lambda t: (t["date"], t["portfolio"], t["ticker"]))
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["date", "ticker", "action", "shares", "price", "portfolio", "side"]
    with open(OUTPUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(trades)

    # ═══════════ Derive portfolios.csv from trades ═══════════
    write_portfolios(trades)

    # ═══════════ Update datasets.csv record counts ═══════════
    update_datasets_csv(len(trades))

    # ═══════════ Summary ═══════════
    print(f"\nWrote {len(trades)} trades to {OUTPUT_CSV}")
    for pf in sorted({t["portfolio"] for t in trades}):
        pt = [t for t in trades if t["portfolio"] == pf]
        buys = sum(1 for t in pt if t["action"] == "buy")
        sells = sum(1 for t in pt if t["action"] == "sell")
        tickers = len({t["ticker"] for t in pt})
        print(f"  {pf}: {len(pt)} trades ({buys} buys, {sells} sells), {tickers} unique tickers")
    print(f"Date range: {trades[0]['date']} to {trades[-1]['date']}")


PORTFOLIO_META = {
    "Flagship": {
        "strategy": "Long/Short Market-Neutral",
        "aum": 600_000_000,
        "max_position_pct": 10,
    },
    "Long Only": {
        "strategy": "Long Only",
        "aum": 500_000_000,
        "max_position_pct": 15,
    },
}


def write_portfolios(trades):
    """Derive portfolios.csv from the generated trades."""
    portfolios = sorted({t["portfolio"] for t in trades})
    rows = []
    for i, name in enumerate(portfolios, 1):
        pt = [t for t in trades if t["portfolio"] == name]
        meta = PORTFOLIO_META.get(name, {})
        inception = min(t["date"] for t in pt)
        unique_tickers = {t["ticker"] for t in pt}
        long_tickers = {t["ticker"] for t in pt if t["side"] == "long"}
        short_tickers = {t["ticker"] for t in pt if t["side"] == "short"}
        # Compute initial exposure from inception-date trades
        init_trades = [t for t in pt if t["date"] == inception]
        long_exp = sum(int(t["shares"]) * float(t["price"])
                       for t in init_trades if t["side"] == "long")
        short_exp = sum(int(t["shares"]) * float(t["price"])
                        for t in init_trades if t["side"] == "short")
        rows.append({
            "portfolio_id": f"PF-{i:03d}",
            "name": name,
            "strategy": meta.get("strategy", ""),
            "aum": meta.get("aum", round(long_exp + short_exp)),
            "long_exposure": round(long_exp),
            "short_exposure": round(short_exp),
            "num_positions": len(init_trades),
            "max_position_pct": meta.get("max_position_pct", ""),
            "inception_date": inception,
            "rebalance_frequency": "Monthly",
            "total_trades": len(pt),
            "unique_tickers": len(unique_tickers),
            "status": "Active",
        })

    fields = list(rows[0].keys())
    with open(PORTFOLIOS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} portfolios to {PORTFOLIOS_CSV}")


def update_datasets_csv(trade_count):
    """Update record counts for portfolio_trades and portfolios in datasets.csv."""
    if not DATASETS_CSV.exists():
        return
    rows = []
    with open(DATASETS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["name"] == "portfolio_trades":
                row["record_count"] = str(trade_count)
                row["id_field"] = "ticker"
            elif row["name"] == "portfolios":
                # Count rows in the portfolios CSV we just wrote
                with open(PORTFOLIOS_CSV, newline="") as pf:
                    pf_count = sum(1 for _ in csv.DictReader(pf))
                row["record_count"] = str(pf_count)
            rows.append(row)
    with open(DATASETS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"Updated datasets.csv record counts")


if __name__ == "__main__":
    main()
