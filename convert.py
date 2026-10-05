import os
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.panel import Panel
from rich.progress import track

console = Console()

def parse_coordinates(coords_text):
    """Parse KML coordinate string into a list of [lon, lat] floats."""
    coords = []
    for point in coords_text.strip().split():
        parts = point.split(',')
        if len(parts) >= 2:
            coords.append([float(parts[0]), float(parts[1])])
    return coords

def load_kml_to_geojson(kml_path):
    """Safely extract geometries from KML using standard XML parsing."""
    try:
        tree = ET.parse(kml_path)
        root = tree.getroot()
        
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

        features = []
        
        for placemark in root.findall('.//Placemark'):
            name = placemark.findtext('name', default='Untitled_Feature')
            geometry = None
            
            point = placemark.find('.//Point')
            if point is not None:
                coords_text = point.findtext('.//coordinates')
                if coords_text:
                    parsed = parse_coordinates(coords_text)
                    if parsed:
                        geometry = {"type": "Point", "coordinates": parsed[0]}

            linestring = placemark.find('.//LineString')
            if linestring is not None:
                coords_text = linestring.findtext('.//coordinates')
                if coords_text:
                    parsed = parse_coordinates(coords_text)
                    if parsed:
                        geometry = {"type": "LineString", "coordinates": parsed}

            polygon = placemark.find('.//Polygon')
            if polygon is not None:
                coords_text = polygon.findtext('.//coordinates')
                if coords_text:
                    parsed = parse_coordinates(coords_text)
                    if parsed:
                        geometry = {"type": "Polygon", "coordinates": [parsed]}
            
            if geometry:
                features.append({
                    "type": "Feature",
                    "properties": {"name": name},
                    "geometry": geometry
                })
                
        return {"type": "FeatureCollection", "features": features}
    except Exception as e:
        console.print(f"[bold red]Error parsing KML:[/bold red] {e}")
        return None

def save_json(data, filepath, is_gov=False):
    """Helper to save dictionary as JSON file with optional Gov validation and sanitization."""
    if is_gov:
        errors = []
        
        # Valid GeoJSON type validation
        valid_types = ["FeatureCollection", "Feature", "Polygon", "LineString"]
        if data.get("type") not in valid_types:
            errors.append(f"Invalid GeoJSON type: '{data.get('type')}'. Must be one of {valid_types}.")
            
        # Required property validation (only applicable to FeatureCollections)
        if data.get("type") == "FeatureCollection" and "features" not in data:
            errors.append("Missing required property: 'features'")
            
        if errors:
            console.print(f"\n[bold red]Validation Error on {Path(filepath).name}:[/bold red] {', '.join(errors)}")
            return False

        # Remove the 'name' field for government compliance
        if data.get("type") == "FeatureCollection":
            for feature in data.get("features", []):
                if "properties" in feature and "name" in feature["properties"]:
                    del feature["properties"]["name"]
        elif data.get("type") == "Feature":
            if "properties" in data and "name" in data["properties"]:
                del data["properties"]["name"]

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return True

def main():
    console.print(Panel.fit(
        "[bold cyan]Robust KML to GeoJSON Converter[/bold cyan]\n"
        "Safely handles modern KML styles and extracts Features or Geometries.",
        border_style="cyan"
    ))

    while True:
        kml_path = Prompt.ask("[bold yellow]Enter the path to your input KML file[/bold yellow]")
        if os.path.isfile(kml_path) and kml_path.lower().endswith('.kml'):
            break
        console.print("[bold red]Invalid file or not a KML.[/bold red] Please try again.")

    out_dir = Prompt.ask("[bold yellow]Enter the output directory[/bold yellow]", default="./output")
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    is_gov = Confirm.ask("\n[bold yellow]Are you converting this KML to GeoJSON for a US government website (e.g., Earth Explorer, NOAA Digital Coast)?[/bold yellow]")

    console.print("\n[bold green]Export Options:[/bold green]")
    console.print("  [1] [cyan]Single FeatureCollection[/cyan] (One file containing everything)")
    console.print("  [2] [cyan]Individual Features[/cyan] (One .geojson file per Placemark)")
    console.print("  [3] [cyan]Individual Geometries[/cyan] (One .geojson file containing just the Polygon/LineString/Point)")
    
    mode = IntPrompt.ask("Choose your output format", choices=["1", "2", "3"], default=1)

    console.print("\n[dim]Parsing KML...[/dim]")
    geojson_data = load_kml_to_geojson(kml_path)
    
    if not geojson_data or not geojson_data.get("features"):
        console.print("[bold red]No valid features found in the KML file. Exiting.[/bold red]")
        return

    features = geojson_data["features"]
    base_name = Path(kml_path).stem
    console.print(f"[bold green]Successfully loaded {len(features)} features![/bold green]\n")

    if mode == 1:
        out_file = os.path.join(out_dir, f"{base_name}_Collection.geojson")
        if save_json(geojson_data, out_file, is_gov):
            console.print(f"[bold blue]Saved complete FeatureCollection to:[/bold blue] {out_file}")
        else:
            console.print("[bold red]Export failed due to invalid GeoJSON parameters.[/bold red]")
            
    elif mode == 2:
        saved_count = 0
        for i, feature in track(enumerate(features), description="Saving Features...", total=len(features)):
            feat_name = feature.get("properties", {}).get("name", f"feature_{i+1}")
            clean_name = "".join(c for c in feat_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            out_file = os.path.join(out_dir, f"{base_name}_{clean_name}.geojson")
            if save_json(feature, out_file, is_gov):
                saved_count += 1
        console.print(f"\n[bold blue]Successfully saved {saved_count} Feature files to:[/bold blue] {out_dir}")

    elif mode == 3:
        saved_count = 0
        for i, feature in track(enumerate(features), description="Saving Geometries...", total=len(features)):
            geometry = feature.get("geometry")
            if not geometry:
                continue
            geom_type = geometry.get("type", "Unknown")
            feat_name = feature.get("properties", {}).get("name", f"geom_{i+1}")
            clean_name = "".join(c for c in feat_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            out_file = os.path.join(out_dir, f"{base_name}_{geom_type}_{clean_name}.geojson")
            if save_json(geometry, out_file, is_gov):
                saved_count += 1
        console.print(f"\n[bold blue]Successfully saved {saved_count} Geometry files to:[/bold blue] {out_dir}")

if __name__ == "__main__":
    main()