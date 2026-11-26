# Nongkrong.ID

**Nongkrong.ID** adalah aplikasi web pencari dan pemberi rekomendasi kafe serta tempat nongkrong di seluruh Indonesia. Pengguna dapat menemukan tempat ngopi, nugas (*Work From Cafe*), atau berkumpul terdekat melalui peta interaktif berdasarkan filter budget, rating ulasan, ketersediaan Wi-Fi, colokan listrik, jam operasional, dan radius jarak GPS.

- **Live Demo:** [https://rekomendasi-nongkrong.vercel.app](https://rekomendasi-nongkrong.vercel.app)

---

## Fitur Utama

1. **Eksplorasi Multi-Kota se-Indonesia**: Mencakup ribuan data kafe terkurasi di berbagai kota besar Indonesia (Jabodetabek, Bandung, Yogyakarta, Semarang, Solo, Surabaya, Malang, Bali, Lombok, Medan, Palembang, Pekanbaru, Padang, Batam, Balikpapan, Samarinda, Pontianak, Banjarmasin, Makassar, Manado, Ambon, hingga Jayapura).
2. **Kalkulasi Jarak GPS (Haversine) & Peta Interaktif**: Menghitung jarak garis lurus dari titik lokasi pengguna ke setiap kafe secara *real-time* dan menampilkannya di atas peta interaktif (Leaflet.js) dengan mode tema Gelap/Terang.
3. **Filter Kebutuhan Lengkap**:
   - **Batas Harga (Budget)**: Mulai dari `< Rp 25.000` hingga `Rp 300.000+`.
   - **Minimum Rating Google Maps**: Filter mulai dari `3.5+` hingga `4.5+`.
   - **Fasilitas WFC & Nongkrong**: Filter wajib ada **Wi-Fi**, **Colokan Listrik**, **Buka 24 Jam**, serta **Sedang Buka Sekarang**.
   - **Pengurutan Fleksibel**: Urutkan berdasarkan *Rating Tertinggi*, *Jarak Terdekat*, *Harga Termurah*, atau *Harga Tertinggi*.
4. **Pembaruan Dataset Otomatis (GitHub Actions + Apify)**: Dilengkapi *workflow* terjadwal dua mingguan (`.github/workflows/update_dataset.yml`) yang memperbarui data kafe secara bertahap dan menyaring tempat non-kafe secara ketat.

---

## Struktur Direktori

```text
nongkrong.id/
├── .github/
│   └── workflows/
│       └── update_dataset.yml   # GitHub Actions cron pipeline untuk update data otomatis
├── scripts/
│   └── update_dataset.py        # Skrip pembaruan & validasi dataset kafe via Apify API
├── apify_dataset.csv            # Dataset utama kafe di Indonesia
├── favicon.ico                  # Favicon fallback berlatar transparan
├── favicon.svg                  # Favicon vektor (SVG) berlatar transparan
├── index.html                   # Antarmuka pengguna (Landing Page, Filter, & Peta Leaflet)
├── main.py                      # Backend API (FastAPI) & pemrosesan filter/jarak
├── requirements.txt             # Daftar dependensi Python
├── vercel.json                  # Konfigurasi deployment serverless Vercel
└── README.md                    # Dokumentasi proyek
```

---

## Teknologi yang Digunakan

- **Backend**: Python, FastAPI, Pandas, Pydantic, Uvicorn
- **Frontend**: HTML5, Tailwind CSS, Vanilla JavaScript, Lucide Icons
- **Peta & Geospasial**: Leaflet.js, OpenStreetMap, Geolocation API, Haversine Distance Formula
- **Data Pipeline & Deployment**: Apify Google Places Crawler, GitHub Actions, Vercel

---

## Endpoint API

| Metode | Endpoint | Deskripsi |
| :--- | :--- | :--- |
| `GET` | `/` | Menyajikan halaman antarmuka utama (`index.html`). |
| `GET` | `/metadata` | Mengembalikan total kafe, total wilayah, dan daftar kota beserta jumlah kafenya. |
| `POST` | `/rekomendasi` | Memproses pencarian kafe berdasarkan parameter wilayah, budget, rating, fasilitas, kata kunci, dan koordinat GPS pengguna. |

---

## Cara Menjalankan di Lokal

1. **Instal dependensi Python**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Jalankan server pengembangan FastAPI**:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

3. **Buka di browser**:
   Akses `http://127.0.0.1:8000`

---

## Lisensi & Hak Cipta

&copy; 2026 **Nongkrong.ID** oleh **Emmanuel Abet Rossi Paays**. All Rights Reserved.
