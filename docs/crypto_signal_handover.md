# Handover Document: Crypto-Signal (Pumpradar Replica) Bot

**Date:** April 3, 2026
**Project:** Crypto-Signal (Pumpradar Replica)
**Current Environment:** `fight-tres` (VPS), Local Dev Environment

---

## 1. Latar Belakang dan Tujuan (Background & Objectives)

Sistem ini dibangun untuk **mereplikasi sinyal trading dari grup premium "Pumpradar"** berdasarkan hasil *reverse engineering* terhadap 49 sinyal historis yang dibagikan pada bulan Februari - Maret 2026.

Tujuan utama dari bot ini adalah:
- Mengidentifikasi pola setup teknikal (momentum/reversal, indikator volume, MACD, RSI, dll) yang selaras dengan sinyal asli Pumpradar.
- Menjalankan berbagai "Passport" (varian strategi berdasarkan bobot indikator yang berbeda) secara paralel di pasar Binance Futures.
- Melakukan papertrading otomatis 24/7 dan mengirimkan notifikasi *entry* serta realisasi P&L (take profit/stop loss) langsung ke Telegram.
- Membuktikan bahwa edge dari grup sinyal berbayar bisa di-kuantifikasi dan diotomatisasi secara mandiri.

---

## 2. Kondisi Strategi Saat Ini (Current State of Strategies)

Bot sedang menjalankan mode **Multi-Passport**, di mana berbagai variasi strategi berjalan bersamaan untuk melihat mana yang secara empiris paling mendekati atau melebihi performa sinyal aslinya.

Berdasarkan pengecekan logs pada server `fight-tres` per April 2026 (hari ke-3 sejak *live paper-trading*), performa `Multi-Passport` menunjukkan hasil berikut:
- 🔄 **Pumpradar Reversal**: Drawdown paling parah (**-30.2%** P&L). Sinyal *over-trading* (120 *trades* dalam 3 hari). Ini mengindikasikan sensitivitas yang terlalu tinggi atau ketiadaan filter tren makro yang memadai.
- 🎯 **Pumpradar Dynamic**: Terdampak cukup lumayan (**-17.0%** P&L).
- 🏆 **Pumpradar OG** & 🚀 **Pumpradar Momentum**: Mengalami *mild drawdown* (**-7.5%** hingga **-7.8%** P&L). Menunjukkan *resilience* yang lebih baik dibanding Reversal namun masih belum net-positif.
- 💎 **Pumpradar HiddenGem**: Drawdown kecil (**-3.0%** P&L) dengan tingkat aktivitas *trading* yang sangat rendah.

**Kesimpulan Sementara:** Pergerakan *choppy* pada market 3 hari ke belakang berhasil "menipu" varian Reversal, sehingga mengeksekusi banyak *fakeouts*. Varian OG dan Momentum lebih stabil.

---

## 3. Apakah Sudah Achieve atau Belum? (Achievements vs Roadmap)

**Yang Sudah Tercapai (Achieved):**
✅ **Core Trading Engine:** Sistem sanggup memindai ~200+ *pairs* Binance USDT Perpetuals dan melakukan kalkulasi indikator kompleks secara paralel.
✅ **Position Management:** Sistem 70/20/10 *TP Cascade* dan *SL Breakeven* sudah berjalan persis sesuai dengan rumus *risk management* yang diobservasi dari grup asli.
✅ **Telegram Integration:** Notifikasi *entry* yang kaya konteks (konfluensi AI, tren BTC) dan pelaporan *exit* (SL Hit, TP1/2/3 Hit) berjalan dengan sangat baik dan andal.

**Yang Belum Tercapai & Perlu Dieksplorasi (To-Do / To-Explore):**
❌ **Net Profitability/Edge Matching:** Hasil *paper trading/forward testing* saat ini (drawdown) belum mereplikasi simulasi P&L +29.6% yang didapat pada backtest statis. 
🔍 **Eksplorasi Berikutnya:**
   - **Strategy Discovery Engine & Walk-Forward Validation:** Ini adalah *missing link* saat ini. Perlu mematangkan *pipeline* optimasi parameter yang dinamis alih-alih mengandalkan parameter statis dari 49 sampel *trade* historis.
   - **Market Regime Filter:** Membutuhkan filter kuat terhadap pergerakan *sideways/choppy* BTC (Market Regime Detection) yang menyebabkan bot Reversal mengalami banyak SLA (*Stop Loss*).*

---

## 4. Status Deployment (Deployment State & Gaps)

**Tahap Deployment Saat Ini:**
- **Lokasi:** Deploy ke VPS `fight-tres` (Akses direct IP: `fight-tres-d` apabila ada masalah dengan jalur Cloudflare).
- **Process Manager:** Berjalan sebagai daemon systemd via `pumpradar.service` (PID ~ `1362071`).
- **Mode:** Paper trading *live* menggunakan token dan chat ID Telegram fiktif (sebagai log notifikasi).

**Kurang Apa (The Gaps):**
- 🔴 **Status Codebase Asynchronous:** Versi codebase yang di-*deploy* di server `fight-tres` saat ini adalah **versi lama (v1.0)**. Versi tersebut menyimpan *state* posisi hanya di RAM (in-memory).
- 🔴 **Missing Persistence:** Kode ter-update (v2.0) dengan `StateStore.py` (sistem *persistence database* SQLite untuk *resume state* bot jika ter-restart atau *crash*) sudah di-develop di lokal komputer ini ([/Users/faiqnau/fight/trading/crypto-signal/bot/state_store.py](file:///Users/faiqnau/fight/trading/crypto-signal/bot/state_store.py)), tetapi **belum di-push/di-deploy ke server `fight-tres`**.
- 🔴 **Log Drift:** Bot pada server mengeksekusi *stdout* ke socket systemd; akses data analitik saat ini cukup sulit dan murni bergantung eksklusif ke log Telegram atau `journalctl`. Belum ada eksportir (seperti Grafana/Prometheus atau Dashboard SQLite).

---

## 5. Pesan Untuk Agent Penerus (Message for the Next Agent)

1. **Sinkronisasi Kode (Highest Priority):** Langkah pertama Anda sebaiknya melakukan pembaruan kode di server `fight-tres`. Terapkan [StateStore](file:///Users/faiqnau/fight/trading/crypto-signal/bot/state_store.py#7-189) (SQLite) agar bot tidak kehilangan data `realized_pnl` dan posisi gantung apabila VPS mengalami *reboot*.
2. **Jalankan [run_discovery.py](file:///Users/faiqnau/fight/trading/crypto-signal/run_discovery.py):** Di mesin lokal ini, sistem [run_discovery.py](file:///Users/faiqnau/fight/trading/crypto-signal/run_discovery.py) dan [walk_forward.py](file:///Users/faiqnau/fight/trading/crypto-signal/bot/walk_forward.py) sedang dalam tahap finalisasi implementasi. Fokuskan pada *tuning* proses ini untuk menemukan varian "Passport" baru yang kebal terhadap *choppy market*.
3. **Optimisasi Reversal:** Passport Reversal saat ini adalah kelemahan terbesar (terlalu banyak transaksi rugi). Anda bisa mempertimbangkan untuk mematikan atau mengkarantina passport ini di *config* server hingga optimasinya lebih baik.
