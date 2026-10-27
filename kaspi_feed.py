#!/usr/bin/env python3
"""Shopify -> Kaspi XML fiyat/stok listesi.

Calistirma:  python kaspi_feed.py
Gerekli ortam degiskenleri (GitHub Secrets):
  SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET   (veya hazir token: SHOPIFY_ACCESS_TOKEN)
Cikti:  public/kaspi.xml  ve  public/audit.csv
"""
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape, quoteattr

API_VERSION = "2025-07"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "public")

QUERY = """
query($cursor: String) {
  productVariants(first: 40, after: $cursor) {
    nodes {
      sku price compareAtPrice
      product { title vendor status }
      inventoryItem {
        inventoryLevels(first: 20) {
          nodes { location { name } quantities(names: ["available"]) { quantity } }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def fail(msg):
    print("HATA: " + msg, file=sys.stderr)
    sys.exit(1)


def load_config():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    bad = [loc for loc, pp in cfg["locations"].items() if not pp or "?" in pp]
    if bad:
        fail("config.json icinde PP kodu girilmemis lokasyonlar var: " + ", ".join(bad))
    pps = list(cfg["locations"].values())
    if len(set(pps)) != len(pps):
        fail("config.json icinde ayni PP kodu birden fazla lokasyona verilmis.")
    if not cfg.get("merchant_id"):
        fail("config.json icinde merchant_id bos.")
    return cfg


def post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def get_token(shop):
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN")
    if token:
        return token
    cid = os.environ.get("SHOPIFY_CLIENT_ID")
    secret = os.environ.get("SHOPIFY_CLIENT_SECRET")
    if not cid or not secret:
        fail("SHOPIFY_CLIENT_ID ve SHOPIFY_CLIENT_SECRET tanimli degil (GitHub > Settings > Secrets).")
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": cid, "client_secret": secret,
    }).encode()
    res = post(f"https://{shop}/admin/oauth/access_token", body,
               {"Content-Type": "application/x-www-form-urlencoded"})
    if "access_token" not in res:
        fail("Shopify token alinamadi: " + json.dumps(res)[:300])
    return res["access_token"]


def fetch_variants(shop, token):
    url = f"https://{shop}/admin/api/{API_VERSION}/graphql.json"
    headers = {"Content-Type": "application/json", "X-Shopify-Access-Token": token}
    cursor, out = None, []
    while True:
        for attempt in range(6):
            res = post(url, json.dumps({"query": QUERY, "variables": {"cursor": cursor}}).encode(), headers)
            errs = res.get("errors")
            if errs and any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in errs):
                time.sleep(2 + attempt * 2)
                continue
            break
        if res.get("errors"):
            fail("Shopify sorgu hatasi: " + json.dumps(res["errors"])[:500])
        page = res["data"]["productVariants"]
        out.extend(page["nodes"])
        throttle = (res.get("extensions") or {}).get("cost", {}).get("throttleStatus", {})
        if throttle and throttle.get("currentlyAvailable", 1000) < 400:
            time.sleep(1.5)
        if not page["pageInfo"]["hasNextPage"]:
            return out
        cursor = page["pageInfo"]["endCursor"]


def fmt_price(v):
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:.2f}"


def build(cfg, variants, kaspi_skus):
    loc_to_pp = cfg["locations"]
    min_stock = int(cfg["min_stock"])
    audit = []

    by_sku = {}
    for v in variants:
        sku = (v.get("sku") or "").strip()
        if sku:
            by_sku.setdefault(sku, []).append(v)

    if cfg.get("only_listed_skus"):
        wanted = [s for s in kaspi_skus]
        for s in wanted:
            if s not in by_sku:
                audit.append((s, "Shopify'da yok", "XML'e eklenmedi"))
    else:
        wanted = sorted(by_sku)

    offers, seen_locs = [], set()
    for sku in wanted:
        vs = by_sku.get(sku)
        if not vs:
            continue
        active = [v for v in vs if v["product"]["status"] == "ACTIVE"]
        if len(vs) > 1:
            audit.append((sku, f"Shopify'da {len(vs)} varyantta ayni SKU", "aktif olanlardan her nokta icin en yuksek stok alindi"))
        use = active or vs
        main = use[0]

        price = main["price"]
        if cfg.get("price_source") == "compare_at" and main.get("compareAtPrice"):
            if float(main["compareAtPrice"]) > float(main["price"]):
                price = main["compareAtPrice"]
        if not price or float(price) <= 0:
            audit.append((sku, "fiyat yok veya 0", "XML'e eklenmedi"))
            continue

        stock = {pp: 0 for pp in loc_to_pp.values()}
        if active:
            for v in active:
                for lvl in v["inventoryItem"]["inventoryLevels"]["nodes"]:
                    name = lvl["location"]["name"]
                    seen_locs.add(name)
                    pp = loc_to_pp.get(name)
                    if pp:
                        q = lvl["quantities"][0]["quantity"] if lvl["quantities"] else 0
                        stock[pp] = max(stock[pp], q or 0)
        else:
            audit.append((sku, "Shopify'da urun aktif degil", "tum noktalarda kapali gonderildi"))

        offers.append({
            "sku": sku, "model": main["product"]["title"], "brand": main["product"]["vendor"] or "",
            "price": fmt_price(price), "stock": stock,
        })

    unknown = sorted(seen_locs - set(loc_to_pp))
    for name in unknown:
        audit.append(("-", f"Shopify lokasyonu config.json'da yok: {name}", "bu lokasyonun stogu sayilmadi"))

    now = datetime.now(timezone(timedelta(hours=5)))
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<kaspi_catalog date="{now.strftime("%Y-%m-%d %H:%M")}" xmlns="kaspiShopping" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="kaspiShopping http://kaspi.kz/kaspishopping.xsd">',
        f"  <company>{escape(cfg['company'])}</company>",
        f"  <merchantid>{escape(cfg['merchant_id'])}</merchantid>",
        "  <offers>",
    ]
    open_count = 0
    for o in offers:
        lines.append(f"    <offer sku={quoteattr(o['sku'])}>")
        lines.append(f"      <model>{escape(o['model'])}</model>")
        lines.append(f"      <brand>{escape(o['brand'])}</brand>")
        lines.append("      <availabilities>")
        any_open = False
        for pp in sorted(o["stock"]):
            q = o["stock"][pp]
            ok = q >= min_stock
            any_open |= ok
            lines.append(f'        <availability available="{"yes" if ok else "no"}" storeId="{pp}" stockCount="{q if ok else 0}"/>')
        open_count += any_open
        lines.append("      </availabilities>")
        lines.append(f"      <price>{o['price']}</price>")
        lines.append("    </offer>")
    lines += ["  </offers>", "</kaspi_catalog>", ""]

    return "\n".join(lines), audit, len(offers), open_count


def main():
    cfg = load_config()
    with open(os.path.join(HERE, "kaspi_skus.txt"), encoding="utf-8") as f:
        kaspi_skus = [l.strip() for l in f if l.strip()]
    if os.environ.get("KASPI_TEST_DATA"):
        with open(os.environ["KASPI_TEST_DATA"], encoding="utf-8") as f:
            variants = json.load(f)
    else:
        token = get_token(cfg["shop"])
        variants = fetch_variants(cfg["shop"], token)
    xml, audit, n, n_open = build(cfg, variants, kaspi_skus)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "kaspi.xml"), "w", encoding="utf-8") as f:
        f.write(xml)
    with open(os.path.join(OUT_DIR, "audit.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["SKU", "Sorun", "Ne yapildi"])
        w.writerows(audit)
    print(f"Shopify varyant: {len(variants)} | XML'deki urun: {n} | en az bir noktada acik: {n_open} | audit satiri: {len(audit)}")


if __name__ == "__main__":
    main()
