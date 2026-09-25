"""Test script for MOEX ISS API."""

from datetime import date, timedelta

import httpx


def fetch_candles(secid: str, interval: int = 24, days: int = 30) -> list[dict]:
    """Fetch candles from MOEX ISS."""
    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{secid}/candles.json"

    till = date.today()
    since = till - timedelta(days=days)

    params = {
        "from": since.isoformat(),
        "till": till.isoformat(),
        "interval": interval,
        "iss.meta": "off",
    }

    response = httpx.get(url, params=params, timeout=30)
    response.raise_for_status()

    payload = response.json()
    columns = payload["candles"]["columns"]
    data = payload["candles"]["data"]

    return [dict(zip(columns, row)) for row in data]


def main() -> None:
    """Entry point: fetch and print first 5 candles."""
    secid = "SBER"
    candles = fetch_candles(secid, interval=24, days=30)

    print(f"Ticker: {secid}")
    print(f"Total candles: {len(candles)}")
    print("First 5 candles:")
    print("-" * 80)

    for candle in candles[:5]:
        print(
            f"{candle['begin']} → {candle['end']} | "
            f"O: {candle['open']:.2f} | "
            f"H: {candle['high']:.2f} | "
            f"L: {candle['low']:.2f} | "
            f"C: {candle['close']:.2f} | "
            f"V: {candle['volume']}"
        )


if __name__ == "__main__":
    main()
