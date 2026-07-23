"""MetalsDesk market data layer, powered by OpenBB.

Pulls futures and equity prices via the OpenBB Platform (yfinance provider,
no API keys needed) and writes market.json for the static site to render.
Falls back to plain yfinance if OpenBB is unavailable.

Run: python fetch_market.py
"""

import datetime
import json
import sys

FUTURES = [
    ("HRC=F", "HRC (CME)"),
    ("HG=F", "Copper"),
    ("ALI=F", "Aluminum"),
]
EQUITIES = [
    ("NUE", "Nucor"),
    ("STLD", "Steel Dynamics"),
    ("CLF", "Cliffs"),
    ("X", "US Steel"),
    ("RS", "Reliance"),
]
HISTORY_DAYS = 130
CHART_POINTS = 90


def hist_openbb(symbol, days):
    from openbb import obb

    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    result = obb.equity.price.historical(
        symbol=symbol, start_date=start, provider="yfinance"
    )
    df = result.to_df()
    df.columns = [str(c).lower() for c in df.columns]
    return df


def hist_yf(symbol, days):
    import yfinance as yf

    df = yf.Ticker(symbol).history(period=f"{days}d")
    df.columns = [str(c).lower() for c in df.columns]
    return df


def get_history(symbol, days=HISTORY_DAYS):
    try:
        df = hist_openbb(symbol, days)
        source = "openbb"
    except Exception as exc:  # noqa: BLE001
        print(f"OpenBB failed for {symbol} ({exc}); falling back to yfinance")
        df = hist_yf(symbol, days)
        source = "yfinance"
    if df is None or df.empty or "close" not in df.columns:
        raise RuntimeError(f"no data for {symbol}")
    return df, source


def tape_entry(symbol, name):
    df, source = get_history(symbol)
    closes = df["close"].dropna()
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) > 1 else last
    chg = ((last - prev) / prev * 100) if prev else 0.0
    return {
        "sym": symbol,
        "name": name,
        "last": round(last, 2),
        "chg_pct": round(chg, 2),
        "source": source,
    }, df


def main():
    tape = []
    hrc_series = []
    errors = []

    for symbol, name in FUTURES + EQUITIES:
        try:
            entry, df = tape_entry(symbol, name)
            tape.append(entry)
            if symbol == "HRC=F":
                closes = df["close"].dropna().iloc[-CHART_POINTS:]
                hrc_series = [
                    {"d": str(idx)[:10], "c": round(float(val), 2)}
                    for idx, val in closes.items()
                ]
        except Exception as exc:  # noqa: BLE001
            print(f"skipped {symbol}: {exc}")
            errors.append(symbol)

    if not tape:
        print("No data fetched at all; leaving existing market.json untouched.")
        sys.exit(1)

    payload = {
        "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "engine": "OpenBB Platform (yfinance provider)",
        "tape": tape,
        "hrc_series": hrc_series,
        "skipped": errors,
    }
    with open("market.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    print(f"Wrote market.json: {len(tape)} instruments, "
          f"{len(hrc_series)} HRC points, skipped {errors or 'none'}")


if __name__ == "__main__":
    main()
