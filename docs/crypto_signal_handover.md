# Handover Document: Crypto-Signal (Pumpradar Replica) Bot

**Date:** April 3, 2026
**Project:** Crypto-Signal (Pumpradar Replica)
**Current Environment:** `fight-tres` (VPS), Local Dev Environment

---

## 1. Latar Belakang dan Tujuan (Background & Objectives)

Sistem ini dibangun untuk **mereplikasi sinyal trading dari grup premium "Pumpradar"** berdasarkan hasil *reverse engineering* terhadap 49 sinyal historis yang dibagikan pada bulan Februari - Maret 2026.

Tujuan utama dari bot ini adalah:
- Mengidentifikasi pola setup teknikal (momentum/reversal, indikator volume, MACD, RSI, dll) yang selaras dengan sinyal asli Pumpradar.
- Menjalankan berbagai "Passport" (varian strategi berdasarkan bobot indikator yang berbeda) dalam satu proses, dengan scan passport dan symbol yang serial per cycle di pasar Binance Futures.
- Melakukan papertrading otomatis 24/7 dan mengirimkan notifikasi *entry* serta realisasi P&L (take profit/stop loss) langsung ke Telegram.
- Membuktikan bahwa edge dari grup sinyal berbayar bisa di-kuantifikasi dan diotomatisasi secara mandiri.

---

## 2. Kondisi Strategi Saat Ini (Current State of Strategies)

Bot sedang menjalankan mode **Multi-Passport**, di mana beberapa variasi strategi dieksekusi berurutan dalam satu scan cycle untuk melihat mana yang secara empiris paling mendekati atau melebihi performa sinyal aslinya.

Berdasarkan `journalctl` pada server `fight-tres`, **deployment lama v1 pre-cutover** berjalan sejak **2026-03-31 11:46:01 UTC**. Snapshot summary terakhir sebelum migrasi v2 pada **2026-04-03 09:48:49 UTC** menunjukkan:
- 🔄 **Pumpradar Reversal**: performa terburuk (**-59.3%**), dengan **337** total trades dan **185** posisi masih open. Ini sinyal *over-trading* dan risk exposure yang tidak terkendali.
- 🎯 **Pumpradar Dynamic**: **-16.9%**, dengan **34** total trades dan **9** posisi masih open.
- 🏆 **Pumpradar OG**: **+5.2%** pada snapshot summary, **63** total trades, **29** open; setelah itu ada event TP pada **2026-04-03 10:00:21 UTC** yang menaikkan equity OG ke **$1,128**.
- 🚀 **Pumpradar Momentum**: **-9.5%**, **32** total trades, **9** open.
- 💎 **Pumpradar HiddenGem**: **-3.0%**, hanya **2** total trades, **1** open.
- 🎯 **Pumpradar Sniper** dan 📊 **Pumpradar VolumeKing**: belum membuka posisi pada snapshot tersebut.

**Catatan Operasional:** `Pumpradar Reversal` harus tetap `enabled=false` di production sampai fixes dari **Task 2, Task 3, dan Task 7** benar-benar ter-deploy. Jangan mengaktifkannya kembali hanya karena backtest lokal terlihat membaik; baseline live di `fight-tres` masih menunjukkan over-trading dan drawdown paling buruk.

**Kesimpulan Sementara:** Pergerakan *choppy* pada market 3 hari ke belakang berhasil "menipu" varian Reversal, sehingga mengeksekusi banyak *fakeouts*. Varian OG dan Momentum lebih stabil.

---

## 3. Apakah Sudah Achieve atau Belum? (Achievements vs Roadmap)

**Yang Sudah Tercapai (Achieved):**
✅ **Core Trading Engine:** Sistem sanggup memindai ~200+ *pairs* Binance USDT Perpetuals dan menjalankan kalkulasi indikator kompleks secara periodik. Scan passport dan symbol di runtime production saat ini masih serial per cycle.
✅ **Position Management:** Sistem 70/20/10 *TP Cascade* dan *SL Breakeven* sudah berjalan persis sesuai dengan rumus *risk management* yang diobservasi dari grup asli.
✅ **Telegram Integration:** Notifikasi *entry* yang kaya konteks (konfluensi AI, tren BTC) dan pelaporan *exit* (SL Hit, TP1/2/3 Hit) berjalan dengan sangat baik dan andal.

**Yang Belum Tercapai & Perlu Dieksplorasi (To-Do / To-Explore):**
❌ **Net Profitability/Edge Matching:** Hasil *paper trading/forward testing* saat ini belum mereplikasi baseline historis **+29.6% return** dengan **13.6% max drawdown** dari [analysis_report.md](analysis_report.md). Baseline ini dihitung dari [data/validated_ledger.csv](../data/validated_ledger.csv) dan [data/all_messages.json](../data/all_messages.json) untuk periode **2026-02-18 s.d. 2026-03-30**, memakai simulasi **3% fixed risk per trade** dan exit cascade **70/20/10**.
🔍 **Eksplorasi Berikutnya:**
   - **Strategy Discovery Engine & Walk-Forward Validation:** Pipeline [`run_discovery.py`](../run_discovery.py) + [`bot/discovery_engine.py`](../bot/discovery_engine.py) + [`bot/walk_forward.py`](../bot/walk_forward.py) sudah ada. PR berikutnya adalah mematangkan kualitas eksperimen, menjalankan WF rutin, dan mempromosikan passport JSON yang lolos tanpa bergantung pada parameter statis dari 49 sampel *trade* historis.
   - **Market Regime Filter:** Membutuhkan filter kuat terhadap pergerakan *sideways/choppy* BTC (Market Regime Detection) yang menyebabkan bot Reversal mengalami banyak SLA (*Stop Loss*).*

---

## 4. Status Deployment (Deployment State & Gaps)

**Tahap Deployment Saat Ini:**
- **Lokasi:** Deploy ke VPS `fight-tres` (Akses direct IP: `fight-tres-d` apabila ada masalah dengan jalur Cloudflare).
- **Process Manager:** Berjalan sebagai daemon systemd via `pumpradar.service` (PID `1429812`, restart v2 pada **2026-04-03 16:23:19 UTC**).
- **Mode:** Paper trading *live* multi-passport via `python3 -m bot.main_multi --interval=1h`. `pumpradar.service` membaca `.env` lewat `EnvironmentFile=`, sedangkan kode bot mengambil `PUMPRADAR_TG_TOKEN`/`PUMPRADAR_TG_CHAT` dari process env dengan opsi override CLI. Tidak ada dotenv loader di Python.

**Kurang Apa (The Gaps):**
- 🟢 **V2 Persistence Deployed:** Server `fight-tres` sekarang sudah menjalankan kode v2 dengan [`bot/state_store.py`](../bot/state_store.py). Lokasi DB default adalah `state.db` yang di-resolve relatif ke repo root, dan bisa dioverride lewat `PUMPRADAR_STATE_DB`.
- 🟠 **State Reset During Cutover:** Karena deployment lama v1 tidak punya `state.db`, semua posisi dan equity runtime in-memory dari proses lama memang reset pada restart **2026-04-03 16:23:19 UTC**. Ini trade-off yang tidak bisa dihindari pada migrasi v1→v2.
- 🟠 **Persistence Semantics:** Open positions, equity snapshots, dan Telegram message IDs dipulihkan dari SQLite. `signal_count` dan `trade_count` adalah counter in-memory, jadi reset saat restart. `trade_log` saat ini hanya mencatat event `SL_HIT`, `SL_BREAKEVEN`, dan `TP3_HIT`.
- 🔴 **Log Drift:** Bot pada server mengeksekusi *stdout* ke socket systemd; akses data analitik saat ini cukup sulit dan murni bergantung eksklusif ke log Telegram atau `journalctl`. Belum ada eksportir (seperti Grafana/Prometheus atau Dashboard SQLite).
- 🟢 **Reversal Quarantined in Production:** Journal setelah restart menunjukkan `Skipping disabled passport config: reversal.json`, dan SQLite `positions` tidak memiliki row untuk `Pumpradar Reversal`. Jika ada row open di DB, `PassportRunner` tetap akan restore posisi itu untuk monitoring, tetapi passport disabled tidak dipakai untuk scan baru.
- 🟢 **Position Caps Active:** General passport cap adalah `50`. `reversal.json` sendiri memakai cap `20` dan `REVERSAL_SIDEWAYS_MAX_OPEN_POSITIONS_PER_PASSPORT=5`. Absennya Reversal dari summary/passport aktif setelah restart terjadi karena config disabled dan tidak ada open row di DB, bukan karena cap 50.
- 🟠 **Historical Market Revalidation Blocked Locally:** `scripts/validate_market.py` saat ini bisa menghasilkan `entry_valid=0/57` karena Binance Futures API mengembalikan HTTP 403 dari environment lokal. Jika ingin meregenerasi kolom revalidation, jalankan script dari egress host yang diizinkan (kemungkinan `fight-tres`) atau siapkan fallback data source.
- 🟢 **Telegram Commands:** Bot menerima `/summary` dan `/stats` untuk ringkasan performa, `/status` untuk status runtime dan DB path, serta `/ping` untuk health check poller.
- 🟢 **Legacy Path Note:** [`bot/main.py`](../bot/main.py) adalah path legacy stateless single-passport. Runtime multi-passport yang dipakai production ada di [`bot/main_multi.py`](../bot/main_multi.py).

---

## 5. Pesan Untuk Agent Penerus (Message for the Next Agent)

1. **Monitor cycle berikutnya:** Karena interval scan `1h`, cycle kedua setelah cutover seharusnya mulai sekitar **2026-04-03 17:23 UTC**. Cek apakah `state.db` mulai punya `equity_snapshots`/`trade_log` saat ada TP/SL event, dan validasi bahwa open positions, equity, serta Telegram thread IDs restore setelah restart. `signal_count` dan `trade_count` memang reset karena masih in-memory.
2. **Jalankan [`run_discovery.py`](../run_discovery.py):** Di mesin lokal ini, pipeline [`run_discovery.py`](../run_discovery.py) + [`walk_forward.py`](../bot/walk_forward.py) sudah diperbaiki dari sisi config mapping/backtest summary. Gunakan flag yang sekarang didukung, misalnya `python3 run_discovery.py --interval=1h --pairs=15 --workers=4 --top-n=20 --train-days=120 --test-days=60`, lalu lanjutkan eksperimen untuk menurunkan false positives di market *sideways*.
3. **Optimisasi Reversal:** `Pumpradar Reversal` tetap `enabled=false` di production sampai ada bukti forward-test baru yang mengalahkan drawdown historisnya. Jangan re-enable hanya dari satu backtest lokal.
