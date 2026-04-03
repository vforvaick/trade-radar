# fight-tres Pumpradar Runbook

## Current Service State

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
