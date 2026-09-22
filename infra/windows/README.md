# Windows host supervision

The live GPU host is intentionally kept behind an outbound Cloudflare Tunnel.
Install [NSSM](https://nssm.cc/) on the laptop, keep it plugged in and awake,
then run `install-flypoker-services.ps1` from an elevated PowerShell prompt.
The script creates restart-on-failure services for the FastAPI process and
`cloudflared`; it does not open an inbound router port.

Set the production values in the script or in the process environment before
installation. The API remains the authoritative source of the live table and
the browser can continue showing uploaded replays while these services are
offline.
