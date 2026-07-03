import os
import json
import urllib.request

def uw_option_contract_id(ticker, expiry_yyyymmdd, right, strike):
    yy = expiry_yyyymmdd[2:4]
    mm = expiry_yyyymmdd[4:6]
    dd = expiry_yyyymmdd[6:8]

    strike_int = int(round(float(strike) * 1000))

    return (
        f"{ticker.upper()}"
        f"{yy}{mm}{dd}"
        f"{right.upper()}"
        f"{strike_int:08d}"
    )

def fetch_contract(contract_id):
    key = os.getenv("UNUSUAL_WHALES_API_KEY", "").strip()

    if not key:
        return None

    url = (
        f"https://api.unusualwhales.com/api/"
        f"option-contract/{contract_id}/flow"
    )

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "SchwarzCapitalBot/2.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())

        rows = data.get("data") or []

        if not rows:
            return None

        return rows[0]

    except Exception as e:
        print('UW_ERROR:', repr(e), flush=True)
        return None
