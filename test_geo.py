import folium
import requests
from geopy.geocoders import Nominatim
from folium.plugins import MarkerCluster

def find_medical_stores(location):
    # Geocode location to lat/lon
    geolocator = Nominatim(user_agent="med_locator")
    loc = geolocator.geocode(location)
    if not loc:
        return []

    lat, lon = loc.latitude, loc.longitude

    # Query Overpass API for pharmacies
    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["amenity"="pharmacy"](around:3000,{lat},{lon});
      way["amenity"="pharmacy"](around:3000,{lat},{lon});
      relation["amenity"="pharmacy"](around:3000,{lat},{lon});
    );
    out center;
    """
    response = requests.get(overpass_url, params={"data": query})
    data = response.json()

    # Map and store pharmacies
    pharmacies = []
    map_ = folium.Map(location=[lat, lon], zoom_start=14)
    marker_cluster = MarkerCluster().add_to(map_)

    for element in data["elements"]:
        name = element.get("tags", {}).get("name", "Unnamed Pharmacy")
        if "lat" in element and "lon" in element:
            plat, plon = element["lat"], element["lon"]
        elif "center" in element:
            plat, plon = element["center"]["lat"], element["center"]["lon"]
        else:
            continue

        folium.Marker(
            location=[plat, plon],
            popup=name,
            icon=folium.Icon(color="green", icon="plus-sign")
        ).add_to(marker_cluster)

        pharmacies.append((name, f"https://www.openstreetmap.org/?mlat={plat}&mlon={plon}"))

    # Save map
    map_.save("medical_stores_map.html")

    return pharmacies
