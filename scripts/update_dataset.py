"""
Automated Google Maps Cafe Dataset Updater via Apify REST API.
Designed for GitHub Actions cron automation within Apify's $5/month free tier.

Strict Quality Guards:
1. Uses explicit English city + province + country search strings so Google Maps locks to the city boundary.
2. Uses Apify 'categoryFilterList' to restrict crawling exclusively to coffee shops, cafes, and roasteries.
3. Validates every downloaded item against strict cafe category & blacklist rules (rejecting furniture stores,
   brownies/cake shops, minimarkets, warungs, etc.) before merging into apify_dataset.csv.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "apify_dataset.csv")

# Curated rotation of major cafe hubs across Indonesia: (Search Query, Expected City/Province Keywords)
INDONESIA_CITY_TARGETS: List[Tuple[str, List[str]]] = [
    # Jabodetabek
    ("Coffee shop in South Jakarta, DKI Jakarta, Indonesia", ["jakarta selatan", "south jakarta"]),
    ("Coffee shop in Central Jakarta, DKI Jakarta, Indonesia", ["jakarta pusat", "central jakarta"]),
    ("Coffee shop in West Jakarta, DKI Jakarta, Indonesia", ["jakarta barat", "west jakarta"]),
    ("Coffee shop in East Jakarta, DKI Jakarta, Indonesia", ["jakarta timur", "east jakarta"]),
    ("Coffee shop in North Jakarta, DKI Jakarta, Indonesia", ["jakarta utara", "north jakarta", "jkt utara"]),
    ("Coffee shop in South Tangerang, Banten, Indonesia", ["tangerang selatan", "south tangerang"]),
    ("Coffee shop in Tangerang City, Banten, Indonesia", ["kota tangerang", "tangerang"]),
    ("Coffee shop in Bogor City, West Java, Indonesia", ["kota bogor", "bogor"]),
    ("Coffee shop in Depok City, West Java, Indonesia", ["kota depok", "depok"]),
    ("Coffee shop in Bekasi City, West Java, Indonesia", ["kota bekasi", "kota bks", "bekasi"]),
    # Jawa Barat
    ("Coffee shop in Bandung City, West Java, Indonesia", ["kota bandung", "bandung"]),
    ("Coffee shop in Cirebon City, West Java, Indonesia", ["kota cirebon", "cirebon"]),
    # Jawa Tengah & DIY
    ("Coffee shop in Yogyakarta City, Special Region of Yogyakarta, Indonesia", ["yogyakarta", "sleman", "bantul"]),
    ("Coffee shop in Semarang City, Central Java, Indonesia", ["kota semarang", "semarang"]),
    ("Coffee shop in Surakarta Solo, Central Java, Indonesia", ["surakarta", "solo"]),
    # Jawa Timur
    ("Coffee shop in Surabaya City, East Java, Indonesia", ["kota surabaya", "surabaya"]),
    ("Coffee shop in Malang City, East Java, Indonesia", ["kota malang", "malang"]),
    # Bali & Nusa Tenggara
    ("Coffee shop in Denpasar, Bali, Indonesia", ["denpasar", "bali"]),
    ("Coffee shop in Badung Canggu Seminyak, Bali, Indonesia", ["badung", "kuta", "bali"]),
    ("Coffee shop in Ubud Gianyar, Bali, Indonesia", ["gianyar", "ubud", "bali"]),
    ("Coffee shop in Mataram Lombok, West Nusa Tenggara, Indonesia", ["mataram", "lombok"]),
    # Sumatera
    ("Coffee shop in Medan City, North Sumatra, Indonesia", ["kota medan", "medan"]),
    ("Coffee shop in Palembang City, South Sumatra, Indonesia", ["kota palembang", "palembang"]),
    ("Coffee shop in Pekanbaru City, Riau, Indonesia", ["kota pekanbaru", "pekanbaru"]),
    ("Coffee shop in Padang City, West Sumatra, Indonesia", ["kota padang", "padang"]),
    ("Coffee shop in Bandar Lampung, Lampung, Indonesia", ["bandar lampung", "lampung"]),
    ("Coffee shop in Batam City, Riau Islands, Indonesia", ["kota batam", "batam"]),
    # Kalimantan
    ("Coffee shop in Balikpapan City, East Kalimantan, Indonesia", ["kota balikpapan", "balikpapan"]),
    ("Coffee shop in Samarinda City, East Kalimantan, Indonesia", ["kota samarinda", "samarinda"]),
    ("Coffee shop in Pontianak City, West Kalimantan, Indonesia", ["kota pontianak", "pontianak"]),
    ("Coffee shop in Banjarmasin City, South Kalimantan, Indonesia", ["kota banjarmasin", "banjarmasin"]),
    # Sulawesi & Indonesia Timur
    ("Coffee shop in Makassar City, South Sulawesi, Indonesia", ["kota makassar", "makassar"]),
    ("Coffee shop in Manado City, North Sulawesi, Indonesia", ["kota manado", "manado"]),
    ("Coffee shop in Ambon City, Maluku, Indonesia", ["kota ambon", "ambon"]),
    ("Coffee shop in Jayapura City, Papua, Indonesia", ["kota jayapura", "jayapura"]),
]

VALID_CAFE_CATS = {
    "kedai kopi",
    "coffee shop",
    "kafe",
    "cafe",
    "coffee roastery",
    "coffee roasters",
    "coffee store",
    "espresso bar",
    "kafe seni",
    "art cafe",
    "coworking space",
    "tea house",
    "kedai teh",
    "coffee stand",
}

BLACKLIST_KEYWORDS = [
    "brownies",
    "furniture",
    "mebel",
    "perlengkapan rumah",
    "azko",
    "ace hardware",
    "informa",
    "minimarket",
    "indomaret",
    "alfamart",
    "alfamidi",
    "k3mart",
    "super indo",
    "supermarket",
    "hipermarket",
    "toserba",
    "swalayan",
    "grocery",
    "convenience store",
    "barber",
    "salon",
    "clothing",
    "toko helm",
    "motorsport",
    "shopping mall",
    "pusat bisnis",
    "grosir",
    "distributor",
    "collectibles",
    "record store",
    "niceso",
    "toko buku",
    "gramedia",
    "toko kue",
    "toko cokelat",
    "dapur cokelat",
    "jofie",
    "pukis",
    "martabak",
    "ayam penyet",
    "nasi goreng",
    "restoran mie",
    "mie pangsit",
    "bakmi",
    "soto mie",
    "bakso",
    "seblak",
    "ketoprak",
    "siomay",
    "restoran padang",
    "ampera",
    "restoran china",
    "restoran seafood",
    "restoran jawa",
    "restoran betawi",
    "kedai sarapan",
    "kedai bakpao",
    "durian kupas",
    "restoran ramen",
    "pujasera",
    "food court",
    "toko makanan sehat",
    "organic store",
]

CAFE_TITLE_HINTS = [
    "coffee",
    "kopi",
    "cafe",
    "café",
    "kafe",
    "roast",
    "espresso",
    "brew",
    "latte",
    "matcha",
]


def is_valid_cafe_row(row: pd.Series, query_map: Dict[str, List[str]]) -> bool:
    """Strictly verify that a scraped place is a real cafe/coffee shop and sits in the expected city."""
    title = str(row.get("title", "")).strip().lower()
    cat = str(row.get("categoryName", row.get("categories/0", ""))).strip().lower()
    all_cats = " ".join(str(row.get(f"categories/{i}", "")).lower() for i in range(5))

    for bw in BLACKLIST_KEYWORDS:
        if bw in title or bw in cat:
            return False

    is_cat_ok = (cat in VALID_CAFE_CATS) or any(h in title for h in CAFE_TITLE_HINTS) or any(vc in all_cats for vc in VALID_CAFE_CATS)
    if not is_cat_ok:
        return False

    ss = str(row.get("searchString", "")).strip()
    if ss in query_map:
        city_col = str(row.get("city", "")).lower()
        state_col = str(row.get("state", "")).lower()
        city_state = f"{city_col} {state_col}"
        expected_tokens = query_map[ss]
        if not any(tok in city_state for tok in expected_tokens):
            return False

    return True


def pick_next_queries(existing_df: pd.DataFrame, batch_size: int = 4) -> Tuple[List[str], Dict[str, List[str]]]:
    """Pick the next batch of Indonesian city queries that have the least coverage in the dataset."""
    query_map = {q: tokens for q, tokens in INDONESIA_CITY_TARGETS}

    custom_query = os.environ.get("TARGET_QUERY", "").strip()
    if custom_query:
        qs = [q.strip() for q in custom_query.split(";") if q.strip()]
        return qs, query_map

    city_col_series = existing_df.get("city", pd.Series([], dtype=str)).dropna().astype(str).str.lower()

    scored = []
    for idx, (q, tokens) in enumerate(INDONESIA_CITY_TARGETS):
        count = 0
        if len(city_col_series) > 0:
            count = int(city_col_series.apply(lambda c: any(t in c for t in tokens)).sum())
        scored.append((count, idx, q))

    scored.sort(key=lambda item: (item[0], item[1]))
    chosen = [item[2] for item in scored[:batch_size]]
    return chosen, query_map


def run_apify_scraper(token: str, queries: List[str], max_per_query: int = 50) -> pd.DataFrame:
    """Trigger Apify compass/crawler-google-places with strict cafe category filter."""
    actor_id = "compass~crawler-google-places"
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={urllib.parse.quote(token)}"

    payload = {
        "searchStringsArray": queries,
        "maxCrawledPlacesPerSearch": max_per_query,
        "language": "id",
        "countryCode": "id",
        "categoryFilterList": ["coffee shop", "cafe"],
        "includeWebResults": False,
        "scrapeDirectories": False,
        "maxImages": 0,
        "maxReviews": 0,
    }

    req = urllib.request.Request(
        run_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(f"[Apify] Memulai scraping untuk query: {queries} (maks {max_per_query} kafe/query)...")
    with urllib.request.urlopen(req, timeout=60) as resp:
        run_info = json.loads(resp.read().decode("utf-8"))["data"]

    run_id = run_info["id"]
    dataset_id = run_info["defaultDatasetId"]
    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={urllib.parse.quote(token)}"

    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(15)
        with urllib.request.urlopen(status_url, timeout=30) as s_resp:
            status_data = json.loads(s_resp.read().decode("utf-8"))["data"]
        status = status_data.get("status")
        print(f"[Apify] Status run {run_id}: {status}")
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify run berakhir dengan status: {status}")
    else:
        raise TimeoutError("Apify run melebihi batas waktu tunggu 15 menit.")

    csv_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?format=csv&clean=true&token={urllib.parse.quote(token)}"
    print(f"[Apify] Mengunduh hasil dataset {dataset_id}...")
    new_df = pd.read_csv(csv_url, low_memory=False)
    return new_df


def merge_datasets(existing_df: pd.DataFrame, new_df: pd.DataFrame, query_map: Dict[str, List[str]]) -> pd.DataFrame:
    """Filter out non-cafe noise and stray locations, then merge and deduplicate."""
    if new_df is None or new_df.empty:
        print("[Merge] Dataset baru kosong. Mempertahankan dataset lama.")
        return existing_df

    before_filter = len(new_df)
    valid_mask = new_df.apply(lambda r: is_valid_cafe_row(r, query_map), axis=1)
    new_df_clean = new_df[valid_mask].copy()
    print(f"[Filter] Menyaring hasil baru: {before_filter} -> {len(new_df_clean)} kafe valid.")

    combined = pd.concat([existing_df, new_df_clean], ignore_index=True)

    if "location/lat" in combined.columns:
        lat_num = pd.to_numeric(combined["location/lat"], errors="coerce").fillna(0.0)
        combined = combined[lat_num != 0.0].copy()

    if "placeId" in combined.columns and combined["placeId"].notna().any():
        with_pid = combined[combined["placeId"].notna()].drop_duplicates(subset=["placeId"], keep="last")
        without_pid = combined[combined["placeId"].isna()]
        combined = pd.concat([with_pid, without_pid], ignore_index=True)

    if "url" in combined.columns and combined["url"].notna().any():
        combined = combined.drop_duplicates(subset=["url"], keep="last")

    if "title" in combined.columns and "address" in combined.columns:
        combined = combined.drop_duplicates(subset=["title", "address"], keep="last")

    return combined.reset_index(drop=True)


def main():
    token = os.environ.get("APIFY_API_TOKEN", "").strip()
    if not token:
        print("[Info] APIFY_API_TOKEN belum diatur di environment/GitHub Secrets. Melewati proses scraping.")
        sys.exit(0)

    if os.path.exists(CSV_PATH):
        existing_df = pd.read_csv(CSV_PATH, low_memory=False)
        print(f"[Dataset] Jumlah kafe saat ini: {len(existing_df)} baris.")
    else:
        existing_df = pd.DataFrame()
        print("[Dataset] Berkas apify_dataset.csv belum ada, membuat baru.")

    batch_size = int(os.environ.get("BATCH_CITIES", "4"))
    max_per_query = int(os.environ.get("MAX_PLACES_PER_CITY", "50"))
    queries, query_map = pick_next_queries(existing_df, batch_size=batch_size)

    try:
        new_df = run_apify_scraper(token, queries=queries, max_per_query=max_per_query)
        print(f"[Apify] Berhasil menarik {len(new_df)} baris mentah.")
    except urllib.error.HTTPError as err:
        print(f"[Warning] Gagal memanggil Apify API (HTTP {err.code}): {err.reason}. Dataset lama dipertahankan.")
        sys.exit(0)
    except Exception as exc:
        print(f"[Warning] Terjadi kendala saat scraping: {exc}. Dataset lama dipertahankan.")
        sys.exit(0)

    merged_df = merge_datasets(existing_df, new_df, query_map)
    if len(merged_df) >= len(existing_df) and len(merged_df) > 0:
        merged_df.to_csv(CSV_PATH, index=False)
        print(f"[Sukses] Dataset diperbarui: {len(existing_df)} -> {len(merged_df)} titik kafe.")
    else:
        print("[Info] Tidak ada penambahan kafe valid baru.")


if __name__ == "__main__":
    main()
