# Meshtastic Pinger

Send GPS fixes from a USB GPS module to a Meshtastic radio over USB without any additional command-line flags. The script detects the
configured Meshtastic device, reads NMEA sentences from the GPS module, formats the latest coordinates, and sends them as a direct
message to a configured target radio.

## Quick start

1. Install dependencies (inside the workspace or a virtual environment):

   ```bash
   python -m pip install -r requirements.txt
   ```

2. Create a `meshtastic_pinger.json` file in the project root. The file should at least define `target_node`. Example:

   ```json
   {
     "target_node": "ABCDEFG12345",
     "meshtastic_port": "COM7",
     "gps_port": "COM4",
     "send_interval_seconds": 60,
     "gps_timeout_seconds": 15,
     "message_template": "GPS {lat:.5f},{lon:.5f} sats {satellites} hdop {hdop:.1f} {time}",
     "radio_mode": "longfast"
   }
   ```

   Only `target_node` is required; all other values honor sensible defaults or can be provided through environment variables.

3. Plug in the Meshtastic radio and the USB GPS module. The radio port will be auto-detected by matching its description (e.g., “Meshtastic”, “T-Beam”, “USB Serial”) unless you set `meshtastic_port`, and the GPS module can be explicitly configured via
   `gps_port` or automatically detected if its description contains GPS-related keywords.

4. Run the pinger with:

   ```bash
   python meshtastic_pinger.py
   ```

   The script will continuously read the GPS device and DM the formatted coordinates to the configured target node. It handles reconnecting to
   the radio automatically after each message and prints helpful logs to the console.

## Configuration

You can override defaults via environment variables:

- `MESHTASTIC_PINGER_CONFIG` – path to a JSON file (defaults to `meshtastic_pinger.json`).
- `MESHTASTIC_PINGER_TARGET_NODE` – radio ID or alias to DM.
- `MESHTASTIC_PINGER_RADIO_PORT` – serial port for the Meshtastic radio.
- `MESHTASTIC_PINGER_GPS_PORT` – serial port for the GPS module.
- `MESHTASTIC_PINGER_INTERVAL` – seconds between transmissions.
- `MESHTASTIC_PINGER_GPS_TIMEOUT` – seconds to wait for a GPS fix.
- `MESHTASTIC_PINGER_TEMPLATE` – message template (can refer to `lat`, `lon`, `hdop`, `satellites`, `fix_quality`, `time`, `date`, `timestamp`, or `snr`).
- `MESHTASTIC_PINGER_RADIO_MODE` – Meshtastic modem preset (e.g., `longfast`, `mediumslow`, `shortturbo`). Defaults to `longfast`.

Default template: `GPS {lat:.6f},{lon:.6f} sats {satellites} hdop {hdop:.1f} {time}`.

## Testing

Run the unit tests with:

```bash
python -m pytest
```

