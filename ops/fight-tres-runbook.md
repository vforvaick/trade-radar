# fight-tres Runbook

## Post-Cryptopass-Overhaul (2026-04-06)

Service renamed: `pumpradar.service` → `cryptopass.service`
Metrics exporter added: `cryptopass-metrics.service` on port 9103

### Service Commands (new)
```bash
ssh fight-tres systemctl status cryptopass.service --no-pager
ssh fight-tres systemctl status cryptopass-metrics.service --no-pager
ssh fight-tres "journalctl -u cryptopass.service -n 100 --no-pager -o short-iso"
```

### Env Vars (updated)
All `PUMPRADAR_*` vars → `CRYPTOPASS_*` on VPS .env
New: `CRYPTOPASS_TG_TRADE_TOPIC_ID` and `CRYPTOPASS_TG_LOG_TOPIC_ID`

### Fresh Start Deploy Steps
```bash
# On VPS fight-tres:
cd /home/vforvaick/pumpradar-bot && git pull
pip install  # if new deps

# Update .env: rename PUMPRADAR_* → CRYPTOPASS_*, add LOG_TOPIC_ID
# Copy new service files
sudo cp ops/cryptopass.service /etc/systemd/system/
sudo cp ops/cryptopass-metrics.service /etc/systemd/system/
sudo systemctl daemon-reload

# Fresh start: clear state.db
python scripts/fresh_start.py --db /home/vforvaick/pumpradar-bot/state.db --confirm

# Swap services
sudo systemctl stop pumpradar.service
sudo systemctl disable pumpradar.service
sudo systemctl enable cryptopass.service
sudo systemctl start cryptopass.service
sudo systemctl enable cryptopass-metrics.service
sudo systemctl start cryptopass-metrics.service

# Verify
systemctl status cryptopass.service --no-pager
curl localhost:9103/health
```

### On fight-uno (Grafana/Prometheus):
1. Update `prometheus.yml` to add:
   ```yaml
   - job_name: 'cryptopass'
     static_configs:
       - targets: ['fight-tres:9103']
   ```
2. Restart Prometheus container: `docker compose -f docker-compose.observability.yml restart prometheus`
3. Import `ops/grafana-cryptopass-dashboard.json` via Grafana UI (+ > Import)

---

## Current Service State (pre-overhaul: pumpradar.service)

- Service: `pumpradar.service`
- Host alias: `fight-tres`
- Working directory: `/home/vforvaick/pumpradar-bot`
- Start time observed after v2 cutover: `2026-04-03 16:23:19 UTC`
- Runtime mode: multi-passport paper trading via `bot.main_multi`
- Observed ExecStart shape: `/home/vforvaick/pumpradar-bot/.venv/bin/python -m bot.main_multi --interval=1h`
- Environment file: `/home/vforvaick/pumpradar-bot/.env` (mode `600`)
- State DB: `/home/vforvaick/pumpradar-bot/state.db`
- Last pre-v2 backup: `/home/vforvaick/pumpradar-bot-backups/pumpradar-bot-20260403T162022Z`

## Read-only inspection

Use these commands to inspect the live service without changing state:

```bash
ssh fight-tres systemctl status pumpradar.service --no-pager
ssh fight-tres systemctl show pumpradar.service --property=Id,ActiveState,SubState,ExecStart,WorkingDirectory,MainPID,User,FragmentPath,UnitFileState,StateChangeTimestamp
ssh fight-tres "journalctl -u pumpradar.service -n 300 --no-pager -o short-iso"
ssh fight-tres "find /home/vforvaick/pumpradar-bot/pumpradar-passports/configs -maxdepth 2 -type f"
```

## Emergency rollback

If Reversal starts expanding open positions or drawdown spikes again:

1. Keep `pumpradar.service` stopped only long enough to quarantine the strategy.
2. Ensure `/home/vforvaick/pumpradar-bot/pumpradar-passports/configs/reversal.json` remains `enabled=false`.
3. Restart the service and confirm the journal no longer shows fresh Reversal entries.
4. Re-check `systemctl status` and the latest summary lines in `journalctl`.

## Post-deploy validation

Run these checks after a code push or service restart:

```bash
ssh fight-tres systemctl show pumpradar.service --property=ActiveState,SubState,MainPID,NRestarts,ExecStart --no-pager
ssh fight-tres "journalctl -u pumpradar.service --since '2026-04-03 16:23:19 UTC' --no-pager -o short-iso"
ssh fight-tres "test -f /home/vforvaick/pumpradar-bot/bot/state_store.py && test -f /home/vforvaick/pumpradar-bot/state.db"
```

Expected after the 2026-04-03 v2 cutover:
- `ExecStart` should not expose Telegram secrets; credentials are sourced from `.env`.
- `journalctl` should show `Skipping disabled passport config: reversal.json`.
- First scan cycle may open up to the cap of 50 positions per passport; Reversal should stay absent from SQLite rows.
- Initial equity/open-position state from the old v1 in-memory process is intentionally reset because the previous deployment had no `state.db`.

## Notes

- The "Read-only inspection" section is safe to run without mutating service state. The "Emergency rollback" section is intentionally mutating and should only be used during incident response.
- The production gap being tracked here is the unsafe Reversal path, not the rest of the passport set.
