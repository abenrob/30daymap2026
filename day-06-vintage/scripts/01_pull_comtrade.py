"""Pull bilateral wine trade from UN Comtrade (annual, all reporters, all partners).

Wine of fresh grapes is SITC 1121 (Rev.1, Rev.2, Rev.3) and HS 2204. Each
classification only returns data that reporters originally submitted in it, so
we pull every classification for the years it covers and pick per reporter-year
later (02_build_flows.py).

The API key is read from the environment (COMTRADE_API_KEY) or a .env file
passed with --env; it is never written anywhere.
Usage: python 01_pull_comtrade.py RAWDIR [--env ../.env]
"""
import argparse
import json
import os
import time
import urllib.request

PLAN = {  # classification: (cmdCode, first year, last year)
    "S1": ("1121", 1962, 1999),
    "S2": ("1121", 1976, 2005),
    "S3": ("1121", 1988, 2005),
    "HS": ("2204", 1988, 2023),
}
URL = "https://comtradeapi.un.org/data/v1/get/C/A/{cl}?period={y}&cmdCode={cmd}&flowCode={fl}&maxRecords=100000"


def key(env):
    k = os.environ.get("COMTRADE_API_KEY")
    if not k and env and os.path.exists(env):
        for line in open(env):
            if line.startswith("COMTRADE_API_KEY="):
                k = line.split("=", 1)[1].strip()
    if not k:
        raise SystemExit("COMTRADE_API_KEY not set")
    return k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rawdir")
    ap.add_argument("--env")
    ap.add_argument("--only", help="comma list of classifications to pull, e.g. HS")
    a = ap.parse_args()
    k = key(a.env)
    os.makedirs(a.rawdir, exist_ok=True)
    calls = 0
    for cl, (cmd, y0, y1) in PLAN.items():
        if a.only and cl not in a.only.split(","):
            continue
        for y in range(y0, y1 + 1):
            for fl in ("M", "X"):
                out = os.path.join(a.rawdir, f"{cl}_{y}_{fl}.json")
                if os.path.exists(out):
                    continue
                req = urllib.request.Request(URL.format(cl=cl, y=y, cmd=cmd, fl=fl),
                                             headers={"Ocp-Apim-Subscription-Key": k})
                for attempt in range(5):
                    try:
                        with urllib.request.urlopen(req, timeout=180) as r:
                            d = json.load(r)
                        break
                    except Exception as e:
                        print("retry", cl, y, fl, e, flush=True)
                        time.sleep(10 * (attempt + 1))
                else:
                    continue
                calls += 1
                json.dump(d.get("data") or [], open(out, "w"))
                print(cl, y, fl, len(d.get("data") or []), d.get("error") or "", flush=True)
                time.sleep(1.2)
    print("calls", calls)


if __name__ == "__main__":
    main()
