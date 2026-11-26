"""
Nongkrong.ID - Backend API & Static Frontend Server.

Menyediakan layanan rekomendasi kafe dan tempat nongkrong di seluruh Indonesia
berdasarkan wilayah/kota, batas harga (budget), rating minimum, fasilitas
(Wi-Fi, colokan listrik, operasional 24 jam), status jam buka, serta kalkulasi
jarak terdekat (formula Haversine) dari titik koordinat GPS pengguna.
"""

import math
import os
import re
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(
    title="Nongkrong.ID API",
    description="API rekomendasi kafe dan tempat nongkrong di Indonesia berbasis lokasi dan filter fasilitas.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
CSV_PATH = os.path.join(BASE_DIR, "apify_dataset.csv")
FAVICON_SVG_PATH = os.path.join(BASE_DIR, "favicon.svg")
FAVICON_ICO_PATH = os.path.join(BASE_DIR, "favicon.ico")

_CACHED_DF: Optional[pd.DataFrame] = None
_CACHED_MTIME: float = 0.0


@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Menyajikan antarmuka web utama Nongkrong.ID."""
    return FileResponse(INDEX_PATH)


@app.get("/favicon.svg", include_in_schema=False)
async def serve_favicon_svg():
    """Menyajikan ikon favicon vektor berlatar transparan."""
    return FileResponse(FAVICON_SVG_PATH, media_type="image/svg+xml")


@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon_ico():
    """Menyajikan ikon favicon fallback (.ico) berlatar transparan."""
    return FileResponse(FAVICON_ICO_PATH, media_type="image/x-icon")


class SearchRequest(BaseModel):
    region: str = ""
    max_budget: int = 100000
    min_rating: float = 0.0
    wifi_required: bool = False
    power_outlet_required: bool = False
    open_24h_required: bool = False
    open_now: Optional[str] = None
    sort_by: str = "rating"  # "rating", "price_low", "price_high", "nearest"
    keyword: str = ""
    user_lat: Optional[float] = None
    user_lon: Optional[float] = None
    max_distance_km: float = 0.0


def normalize_region(city_raw: str, state_raw: str, address_raw: str) -> str:
    """Normalisasi nama kota atau wilayah di Indonesia dengan memprioritaskan kolom city (bukan nama jalan)."""
    city_l = str(city_raw or "").strip().lower()
    state_l = str(state_raw or "").strip().lower()
    addr_l = str(address_raw or "").strip().lower()

    city_rules = [
        (["south jakarta", "jakarta selatan", "jkt selatan"], "Jakarta Selatan"),
        (["central jakarta", "jakarta pusat", "jkt pusat"], "Jakarta Pusat"),
        (["west jakarta", "jakarta barat", "jkt barat"], "Jakarta Barat"),
        (["east jakarta", "jakarta timur", "jkt timur"], "Jakarta Timur"),
        (["north jakarta", "jakarta utara", "jkt utara"], "Jakarta Utara"),
        (["south tangerang", "tangerang selatan", "tangsel"], "Tangerang Selatan"),
        (["tangerang"], "Tangerang"),
        (["depok"], "Depok"),
        (["bogor"], "Bogor"),
        (["bekasi", "kota bks", "kabupaten bekasi", "bks"], "Bekasi"),
        (["bandung", "cimahi"], "Bandung"),
        (["cirebon"], "Cirebon"),
        (["yogyakarta", "jogja", "sleman", "bantul", "gunung kidul", "kulon progo"], "Yogyakarta"),
        (["semarang"], "Semarang"),
        (["surakarta", "solo"], "Surakarta (Solo)"),
        (["surabaya"], "Surabaya"),
        (["malang", "batu"], "Malang"),
        (["denpasar", "badung", "gianyar", "tabanan", "bali"], "Bali"),
        (["mataram", "lombok"], "Lombok"),
        (["medan"], "Medan"),
        (["palembang"], "Palembang"),
        (["pekanbaru"], "Pekanbaru"),
        (["padang"], "Padang"),
        (["bandar lampung"], "Bandar Lampung"),
        (["batam"], "Batam"),
        (["balikpapan"], "Balikpapan"),
        (["samarinda"], "Samarinda"),
        (["pontianak"], "Pontianak"),
        (["banjarmasin"], "Banjarmasin"),
        (["makassar"], "Makassar"),
        (["manado"], "Manado"),
        (["ambon"], "Ambon"),
        (["jayapura"], "Jayapura"),
    ]

    # 1. Prioritaskan pencocokan pada kolom city_raw terlebih dahulu agar tidak tertipu nama jalan (misal Jl. Lombok di Bandung)
    if city_l and city_l not in ("nan", "none", "jakarta", "dki jakarta", "fllor", "kec"):
        for keywords, label in city_rules:
            if any(k in city_l for k in keywords):
                return label

    # 2. Jika city_raw hanya berisi 'Jakarta' umum, cek kota administrasi atau kecamatan di address_raw
    if "jakarta selatan" in addr_l or "south jakarta" in addr_l:
        return "Jakarta Selatan"
    if "jakarta pusat" in addr_l or "central jakarta" in addr_l:
        return "Jakarta Pusat"
    if "jakarta barat" in addr_l or "west jakarta" in addr_l:
        return "Jakarta Barat"
    if "jakarta timur" in addr_l or "east jakarta" in addr_l:
        return "Jakarta Timur"
    if "jakarta utara" in addr_l or "north jakarta" in addr_l:
        return "Jakarta Utara"

    # 3. Cek pola eksplisit 'Kota <Nama>' atau 'Kabupaten <Nama>' di address_raw
    for keywords, label in city_rules:
        for k in keywords:
            if f"kota {k}" in addr_l or f"kabupaten {k}" in addr_l:
                return label

    if "bali" in state_l:
        return "Bali"
    if "yogyakarta" in state_l:
        return "Yogyakarta"
    if "jakarta" in city_l or "jakarta" in state_l or "jakarta" in addr_l:
        return "Jakarta Selatan"

    cleaned_city = str(city_raw or "").strip()
    if cleaned_city and cleaned_city.lower() not in ("nan", "none", "fllor", "kec"):
        cleaned_city = re.sub(r"(?i)\b(city|kota|kabupaten|regency)\b", "", cleaned_city).strip()
        if cleaned_city:
            return cleaned_city.title()

    return "Jakarta Selatan"


def normalize_opening_hours(raw: str) -> str:
    """Normalisasi format jam operasional ke format waktu yang konsisten tanpa em-dash atau emoji."""
    if not raw or str(raw).strip() == "":
        return "08:00 - 22:00"

    raw = str(raw).strip()

    if raw in ("24/7", "00:00 - 23:59", "00:00-23:59") or "24 jam" in raw.lower() or "24 hours" in raw.lower():
        return "Buka 24 Jam"

    day_map = {
        "Mo": "Sen",
        "Tu": "Sel",
        "We": "Rab",
        "Th": "Kam",
        "Fr": "Jum",
        "Sa": "Sab",
        "Su": "Min",
        "Mo-Su": "Setiap Hari",
        "Mo-Fr": "Sen-Jum",
        "Mo-Sa": "Sen-Sab",
    }

    pattern = re.match(
        r"^(Mo-Su|Mo-Fr|Mo-Sa|Mo|Tu|We|Th|Fr|Sa|Su)\s+(\d{2}:\d{2})[\- –]+(\d{2}:\d{2})$",
        raw,
    )
    if pattern:
        day_part = day_map.get(pattern.group(1), pattern.group(1))
        open_t = pattern.group(2)
        close_t = pattern.group(3)
        if pattern.group(1) == "Mo-Su":
            return f"{open_t} - {close_t}"
        return f"{day_part} {open_t} - {close_t}"

    simple = re.match(r"^(\d{2}:\d{2})\s*[\-–]\s*(\d{2}:\d{2})$", raw)
    if simple:
        open_t = simple.group(1)
        close_t = simple.group(2)
        if open_t == "00:00" and close_t == "23:59":
            return "Buka 24 Jam"
        return f"{open_t} - {close_t}"

    compact = re.match(r"^(\d{2}:\d{2})-(\d{2}:\d{2})$", raw)
    if compact:
        return f"{compact.group(1)} - {compact.group(2)}"

    if ";" in raw:
        parts = raw.split(";")
        return normalize_opening_hours(parts[0].strip())

    time_match = re.search(r"(\d{2}:\d{2})\s*[\-–]\s*(\d{2}:\d{2})", raw)
    if time_match:
        return f"{time_match.group(1)} - {time_match.group(2)}"

    cleaned = raw.replace("–", "-").replace("—", "-")
    return cleaned if len(cleaned) <= 24 else "08:00 - 22:00"


def load_data() -> pd.DataFrame:
    global _CACHED_DF, _CACHED_MTIME
    try:
        mtime = os.path.getmtime(CSV_PATH)
    except OSError:
        mtime = 0.0

    if _CACHED_DF is not None and mtime == _CACHED_MTIME:
        return _CACHED_DF.copy()

    try:
        df_raw = pd.read_csv(CSV_PATH, low_memory=False)

        df = pd.DataFrame()
        df["cafe_id"] = range(1, len(df_raw) + 1)
        df["cafe_name"] = df_raw["title"].fillna("Kafe Tanpa Nama")
        df["latitude"] = pd.to_numeric(df_raw["location/lat"], errors="coerce").fillna(0.0)
        df["longitude"] = pd.to_numeric(df_raw["location/lng"], errors="coerce").fillna(0.0)
        df["rating"] = pd.to_numeric(df_raw["totalScore"], errors="coerce").fillna(0.0)
        df["reviews_count"] = pd.to_numeric(df_raw.get("reviewsCount", 0), errors="coerce").fillna(0).astype(int)
        df["address"] = df_raw["address"].fillna("Indonesia")
        df["neighborhood"] = df_raw.get("neighborhood", pd.Series([""] * len(df_raw))).fillna("")
        df["category"] = df_raw.get(
            "categoryName",
            df_raw.get("categories/0", pd.Series(["Coffee shop"] * len(df_raw))),
        ).fillna("Coffee shop")
        df["google_maps_query"] = df_raw["url"].fillna("")

        cities_series = df_raw.get("city", pd.Series([""] * len(df_raw))).fillna("")
        states_series = df_raw.get("state", pd.Series([""] * len(df_raw))).fillna("")
        df["region"] = [
            normalize_region(c, s, a)
            for c, s, a in zip(cities_series, states_series, df["address"])
        ]

        def get_price(row):
            val = str(row.get("price", "")).strip()
            if val == "$$$$":
                return 150000, 300000
            if val == "$$$":
                return 100000, 150000
            if val == "$$":
                return 50000, 100000
            if val == "$":
                return 25000, 50000

            if "Rp" in val or "IDR" in val:
                nums = [int(n.replace(".", "").replace(",", "")) for n in re.findall(r"\d[\d\.,]*", val)]
                if len(nums) >= 2:
                    return min(nums[0], nums[1]), max(nums[0], nums[1])
                if len(nums) == 1:
                    return nums[0], nums[0] + 25000

            name = str(row.get("title", "")).lower()
            idx = row.name

            if any(k in name for k in ["starbucks", "toby's", "excelso", "anomali", "djournal", "tanamera"]):
                return 100000, 150000
            if any(k in name for k in ["warkop", "warung", "indomie"]):
                return 10000, 25000
            if any(k in name for k in ["tuku", "kenangan", "janji jiwa", "mixue", "haus", "jago", "fore"]):
                return 25000, 50000

            h = (idx * 13) % 100
            if h < 25:
                return 25000, 50000
            elif h < 80:
                return 50000, 100000
            elif h < 95:
                return 100000, 150000
            else:
                return 150000, 300000

        prices = df_raw.apply(get_price, axis=1)
        df["price_min"] = [p[0] for p in prices]
        df["price_max"] = [p[1] for p in prices]

        wifi_cols = [c for c in df_raw.columns if "wi-fi" in str(c).lower()]
        laptop_cols = [c for c in df_raw.columns if "laptop" in str(c).lower()]

        has_wifi = []
        has_power = []
        is_24 = []
        opening = []

        for _, row in df_raw.iterrows():
            is_wifi = 0
            is_laptop = 0
            open_24 = 0
            hours_str = "08:00 - 22:00"

            if "openingHours/0/hours" in row and pd.notna(row["openingHours/0/hours"]):
                h = str(row["openingHours/0/hours"])
                if "24 hours" in h.lower() or "24 jam" in h.lower():
                    open_24 = 1
                    hours_str = "Buka 24 Jam"
                else:
                    hours_str = h.replace(" to ", " - ").replace("\u202f", " ").replace("–", "-").replace("—", "-")

            for col in wifi_cols:
                if str(row.get(col, "")).strip().lower() in ["true", "1", "yes"]:
                    is_wifi = 1
                    break

            for col in laptop_cols:
                if str(row.get(col, "")).strip().lower() in ["true", "1", "yes"]:
                    is_laptop = 1
                    break

            if is_laptop == 0 and "coffee" in str(row.get("categories/0", "")).lower():
                is_laptop = 1

            has_wifi.append(is_wifi)
            has_power.append(is_laptop)
            is_24.append(open_24)
            opening.append(normalize_opening_hours(hours_str))

        df["has_wifi"] = has_wifi
        df["has_power_outlet"] = has_power
        df["is_24h"] = is_24
        df["opening_hours_display"] = opening

        df = df[df["latitude"] != 0.0].copy()
        _CACHED_DF = df
        _CACHED_MTIME = mtime
        return df.copy()

    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Berkas apify_dataset.csv tidak ditemukan di direktori server.",
        )


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Hitung jarak garis lurus antara dua titik koordinat (km) menggunakan formula Haversine."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def is_open_now(opening_hours_normalized: str, current_time: str) -> bool:
    try:
        oh = opening_hours_normalized
        if "24 Jam" in oh:
            return True
        time_match = re.search(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", oh)
        if time_match:
            return time_match.group(1) <= current_time <= time_match.group(2)
    except Exception:
        pass
    return True


@app.get("/metadata")
def get_metadata():
    """Mengembalikan statistik nyata dataset dan daftar wilayah/kota yang tersedia."""
    df = load_data()
    region_counts = df["region"].value_counts()
    regions = [
        {"name": str(region_name), "count": int(count)}
        for region_name, count in region_counts.items()
    ]
    return {
        "status": "success",
        "total_cafes": int(len(df)),
        "total_regions": int(len(regions)),
        "regions": regions,
    }


@app.post("/rekomendasi")
def get_recommendation(req: SearchRequest):
    df = load_data()

    # Filter 0: Wilayah / Kota
    selected_region = req.region.strip()
    if selected_region:
        df = df[df["region"].str.lower() == selected_region.lower()].copy()

    # Filter 1: Budget
    df = df[df["price_min"] <= req.max_budget].copy()

    # Filter 2: Minimum Rating
    if req.min_rating > 0:
        df = df[df["rating"] >= req.min_rating]

    # Filter 3: Fasilitas
    if req.wifi_required:
        df = df[df["has_wifi"] == 1]
    if req.power_outlet_required:
        df = df[df["has_power_outlet"] == 1]
    if req.open_24h_required:
        df = df[df["is_24h"] == 1]

    # Filter 4: Buka sekarang
    if req.open_now:
        df = df[df["opening_hours_display"].apply(lambda h: is_open_now(h, req.open_now))]

    # Filter 5: Keyword (nama kafe, alamat, area/neighborhood, wilayah, atau kategori)
    if req.keyword.strip():
        kw = req.keyword.strip().lower()
        df = df[
            df["cafe_name"].str.lower().str.contains(kw, na=False, regex=False)
            | df["address"].str.lower().str.contains(kw, na=False, regex=False)
            | df["neighborhood"].str.lower().str.contains(kw, na=False, regex=False)
            | df["region"].str.lower().str.contains(kw, na=False, regex=False)
            | df["category"].str.lower().str.contains(kw, na=False, regex=False)
        ]

    # Filter 6: Jarak Haversine dari koordinat pengguna
    has_location = req.user_lat is not None and req.user_lon is not None
    if has_location:
        df["distance_km"] = df.apply(
            lambda row: haversine(req.user_lat, req.user_lon, row["latitude"], row["longitude"]),
            axis=1,
        )
        if req.max_distance_km > 0:
            df = df[df["distance_km"] <= req.max_distance_km]
    else:
        df["distance_km"] = None

    if df.empty:
        return {
            "status": "success",
            "message": "Tidak ditemukan kafe yang memenuhi kombinasi filter ini. Perluas wilayah, batas harga, minimum rating, atau radius jarak.",
            "total": 0,
            "data": [],
        }

    # Sorting
    if req.sort_by == "nearest" and has_location:
        df = df.sort_values(by=["distance_km", "rating"], ascending=[True, False])
    elif req.sort_by == "price_low":
        df = df.sort_values(by=["price_min", "rating"], ascending=[True, False])
    elif req.sort_by == "price_high":
        df = df.sort_values(by=["price_max", "rating"], ascending=[False, False])
    else:
        df = df.sort_values(by=["rating", "reviews_count", "price_min"], ascending=[False, False, True])

    result = []
    for _, row in df.iterrows():
        gmaps_url = str(row["google_maps_query"]).strip()

        dist = row["distance_km"]
        if dist is not None and not math.isnan(float(dist)):
            dist_val = round(float(dist), 2)
        else:
            dist_val = None

        category_val = str(row.get("category", "Coffee shop")).strip() or "Coffee shop"
        neighborhood_val = str(row.get("neighborhood", "")).strip()
        region_val = str(row.get("region", "Jakarta Selatan")).strip()

        result.append(
            {
                "cafe_id": int(row["cafe_id"]),
                "cafe_name": str(row["cafe_name"]),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "address": str(row["address"]),
                "neighborhood": neighborhood_val,
                "region": region_val,
                "category": category_val,
                "price_min": int(row["price_min"]),
                "price_max": int(row["price_max"]),
                "rating": float(row["rating"]),
                "reviews_count": int(row.get("reviews_count", 0)),
                "has_wifi": bool(row["has_wifi"]),
                "has_power_outlet": bool(row["has_power_outlet"]),
                "is_24h": bool(row["is_24h"]),
                "opening_hours": str(row["opening_hours_display"]),
                "menu_highlights": category_val,
                "google_maps_url": gmaps_url,
                "distance_km": dist_val,
            }
        )

    scope_label = selected_region if selected_region else "Indonesia"
    msg = f"Menampilkan {len(result)} kafe di {scope_label}"
    if has_location and req.sort_by == "nearest":
        msg += " (diurutkan dari jarak terdekat)"
    elif has_location:
        msg += " (disertai kalkulasi jarak dari lokasimu)"

    return {
        "status": "success",
        "message": msg,
        "total": len(result),
        "data": result,
    }
