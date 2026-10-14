import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from typing import Any
import asyncio
import httpx
import os
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
port = int(os.getenv("PORT", 8085))
mcp = FastMCP("weather", host="0.0.0.0", port=port)

# Constants
WEATHERAPI_BASE = "https://api.weatherapi.com/v1"
USER_AGENT = "weather-app/1.0"

from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# Get API keys from environment variable (supports both WeatherAPI and OpenWeatherMap)
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_APIKEY") or os.getenv("OPENWEATHER_API_KEY")
API_KEY = WEATHERAPI_KEY

async def make_weather_request(endpoint: str, params: dict[str, str]) -> dict[str, Any] | None:
    """Make a request to the WeatherAPI with proper error handling."""
    if not WEATHERAPI_KEY:
        return None
        
    headers = {
        "User-Agent": USER_AGENT,
    }
    params["key"] = WEATHERAPI_KEY
    url = f"{WEATHERAPI_BASE}/{endpoint}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code}: {e.response.text}")
            return None
        except httpx.RequestError as e:
            print(f"Request Error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

async def get_weather_from_openweather(city: str) -> str | None:
    """Fetch current weather from OpenWeatherMap API."""
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric"}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            name = data.get("name", city)
            country = data.get("sys", {}).get("country", "")
            main = data.get("main", {})
            temp_c = main.get("temp", 0)
            temp_f = round(temp_c * 9/5 + 32, 1)
            feels_c = main.get("feels_like", 0)
            feels_f = round(feels_c * 9/5 + 32, 1)
            weather_desc = data.get("weather", [{}])[0].get("description", "").title()
            humidity = main.get("humidity", 0)
            wind_speed_ms = data.get("wind", {}).get("speed", 0)
            wind_kph = round(wind_speed_ms * 3.6, 1)
            wind_mph = round(wind_kph / 1.60934, 1)
            pressure = main.get("pressure", 0)
            vis_km = round(data.get("visibility", 10000) / 1000, 1)
            
            return f"""
Current Weather for {name}, {country}:

Temperature: {temp_c}°C ({temp_f}°F)
Feels like: {feels_c}°C ({feels_f}°F)
Condition: {weather_desc}
Humidity: {humidity}%
Wind: {wind_kph} km/h ({wind_mph} mph)
Pressure: {pressure} mb
Visibility: {vis_km} km
"""
        except Exception as e:
            print(f"OpenWeather current weather error: {e}")
            return None

async def get_forecast_from_openweather(city: str, days: int = 3) -> str | None:
    """Fetch weather forecast from OpenWeatherMap API."""
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric"}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            city_name = data.get("city", {}).get("name", city)
            country = data.get("city", {}).get("country", "")
            
            days_dict = defaultdict(list)
            for item in data.get("list", []):
                dt_txt = item.get("dt_txt", "")
                date = dt_txt.split(" ")[0]
                days_dict[date].append(item)
            
            forecasts = [f"Weather Forecast for {city_name}, {country}:"]
            for date, items in list(days_dict.items())[:days]:
                max_c = round(max(it["main"]["temp_max"] for it in items), 1)
                min_c = round(min(it["main"]["temp_min"] for it in items), 1)
                max_f = round(max_c * 9/5 + 32, 1)
                min_f = round(min_c * 9/5 + 32, 1)
                cond = items[len(items)//2]["weather"][0]["description"].title()
                pop = int(max(it.get("pop", 0) for it in items) * 100)
                max_wind = round(max(it.get("wind", {}).get("speed", 0) for it in items) * 3.6, 1)
                
                forecast = f"""
{date}:
High: {max_c}°C ({max_f}°F)
Low: {min_c}°C ({min_f}°F)
Condition: {cond}
Chance of Rain: {pop}%
Max Wind: {max_wind} km/h
"""
                forecasts.append(forecast)
            return "\n---\n".join(forecasts)
        except Exception as e:
            print(f"OpenWeather forecast error: {e}")
            return None

@mcp.tool()
async def get_current_weather(city: str) -> str:
    """Get current weather conditions for a city.

    Args:
        city: City name (e.g., "Hanoi", "Haiphong", "Danang", "Brisbane", "Sydney")
    """
    if OPENWEATHER_KEY:
        ow_res = await get_weather_from_openweather(city)
        if ow_res:
            return ow_res

    params = {
        "q": city,
        "aqi": "no"
    }
    
    data = await make_weather_request("current.json", params)

    if not data:
        if not WEATHERAPI_KEY and not OPENWEATHER_KEY:
            return f"❌ Weather API key not configured. Please set OPENWEATHER_APIKEY or WEATHERAPI_KEY in .env"
        return f"Unable to fetch current weather data for {city}. Please check the city name and API key configuration."

    current = data["current"]
    location = data["location"]
    
    return f"""
Current Weather for {location['name']}, {location['region']}, {location['country']}:

Temperature: {current['temp_c']}°C ({current['temp_f']}°F)
Feels like: {current['feelslike_c']}°C ({current['feelslike_f']}°F)
Condition: {current['condition']['text']}
Humidity: {current['humidity']}%
Wind: {current['wind_kph']} km/h ({current['wind_mph']} mph) {current['wind_dir']}
Pressure: {current['pressure_mb']} mb
UV Index: {current['uv']}
Visibility: {current['vis_km']} km

Last updated: {current['last_updated']}
"""

@mcp.tool()
async def get_forecast(city: str, days: int = 3) -> str:
    """Get weather forecast for a city.

    Args:
        city: City name (e.g., "Hanoi", "Haiphong", "Danang", "Brisbane", "Sydney", "Melbourne")
        days: Number of days to forecast (1-3 for free tier, max 10 for paid)
    """
    days = min(days, 3)
    
    if OPENWEATHER_KEY:
        ow_res = await get_forecast_from_openweather(city, days)
        if ow_res:
            return ow_res

    params = {
        "q": city,
        "days": str(days),
        "aqi": "no",
        "alerts": "no"
    }
    
    data = await make_weather_request("forecast.json", params)

    if not data:
        if not WEATHERAPI_KEY and not OPENWEATHER_KEY:
            return f"❌ Weather API key not configured. Please set OPENWEATHER_APIKEY or WEATHERAPI_KEY in .env"
        return f"Unable to fetch forecast data for {city}. Please check the city name and API key configuration."

    location = data["location"]
    forecast_days = data["forecast"]["forecastday"]
    
    forecasts = []
    forecasts.append(f"Weather Forecast for {location['name']}, {location['region']}, {location['country']}:")
    
    for day in forecast_days:
        day_data = day["day"]
        date = day["date"]
        
        forecast = f"""
{date}:
High: {day_data['maxtemp_c']}°C ({day_data['maxtemp_f']}°F)
Low: {day_data['mintemp_c']}°C ({day_data['mintemp_f']}°F)
Condition: {day_data['condition']['text']}
Chance of Rain: {day_data['daily_chance_of_rain']}%
Max Wind: {day_data['maxwind_kph']} km/h
UV Index: {day_data['uv']}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)

@mcp.tool()
async def health_check() -> str:
    """Health check endpoint for deployment verification."""
    return "✅ Weather MCP Server is running! Ready to provide weather data for Australian cities and worldwide."

print("✅ MCP server initialized with Streamable HTTP transport")
print("🔧 Available tools: get_current_weather, get_forecast, health_check")

if __name__ == "__main__":
    if "--stdio" in sys.argv:
        print("Starting FastMCP server in stdio mode for local client", file=sys.stderr)
        mcp.run()
    else:
        print(f"🚀 Starting MCP server on http://0.0.0.0:{port}/mcp")
        mcp.run(transport="streamable-http")