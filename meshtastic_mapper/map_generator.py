"""Generate HTML map visualizations from GPS messages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .parser import GpsMessage


def generate_map_html(
    messages: list[GpsMessage],
    output_path: Path,
    title: str = "Meshtastic GPS Messages",
) -> None:
    """Generate an HTML file with an interactive map showing GPS coordinates."""
    if not messages:
        raise ValueError("No GPS messages to map")

    # Calculate center and bounds
    lats = [msg.lat for msg in messages]
    lons = [msg.lon for msg in messages]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    # Generate markers and polyline data
    markers_js = []
    polyline_coords = []

    for i, msg in enumerate(messages):
        # Create popup content
        popup_lines = [
            f"<strong>Point {i + 1}</strong>",
            f"Coordinates: {msg.lat:.6f}, {msg.lon:.6f}",
        ]
        if msg.satellites is not None:
            popup_lines.append(f"Satellites: {msg.satellites}")
        if msg.hdop is not None:
            popup_lines.append(f"HDOP: {msg.hdop:.1f}")
        if msg.sent_at:
            popup_lines.append(f"Sent: {msg.sent_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if msg.received_at:
            popup_lines.append(f"Received: {msg.received_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if msg.delay_seconds is not None:
            popup_lines.append(f"Delay: {msg.delay_seconds:.3f}s")

        popup_content = "<br>".join(popup_lines)
        # Use JSON encoding to safely escape the popup content
        popup_json = json.dumps(popup_content)

        markers_js.append(
            f"L.marker([{msg.lat}, {msg.lon}])"
            f".addTo(map)"
            f".bindPopup({popup_json});"
        )

        polyline_coords.append(f"[{msg.lat}, {msg.lon}]")

    markers_code = "\n        ".join(markers_js)
    polyline_code = ", ".join(polyline_coords)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
        }}
        #map {{
            height: 100vh;
            width: 100%;
        }}
        .info {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            z-index: 1000;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="info">
        <strong>{title}</strong><br>
        Total points: {len(messages)}<br>
        <small>Click markers for details</small>
    </div>
    <div id="map"></div>
    <script>
        const map = L.map('map').setView([{center_lat}, {center_lon}], 13);
        
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);

        // Add markers
        {markers_code}

        // Add polyline connecting points
        const polyline = L.polyline([
            {polyline_code}
        ], {{
            color: 'blue',
            weight: 3,
            opacity: 0.7
        }}).addTo(map);

        // Fit map to show all points
        const bounds = L.latLngBounds([
            {polyline_code}
        ]);
        map.fitBounds(bounds, {{ padding: [20, 20] }});
    </script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        file.write(html_content)
