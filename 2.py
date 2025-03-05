import streamlit as st
st.set_page_config(page_title="Weather App", page_icon="🌦️")

import requests
from datetime import datetime, timedelta
from meteostat import Point, Daily
import plotly.express as px
import pandas as pd 
import numpy as np
import plotly.graph_objects as go
import base64
import json
import os
import folium
from streamlit_folium import st_folium
import time
from streamlit_cookies_manager import EncryptedCookieManager
# from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

# API Key for Visual Crossing
API_key = "EN8XLY62ZBDXB9DMYF3PXWTH2"

# history_file= "search_history.json"

# Set up cookies manager.
cookie_password = os.environ.get("COOKIE_PASSWORD", "default_fallback_password")
cookies= EncryptedCookieManager(prefix='2', password= cookie_password)
if not cookies.ready():
    st.stop() # Wait until the cookies are ready

# Instead of using a JSON file for persistent storage, we'll initialize a session state variable
if 'search_history' in cookies:
    try:
        cookie_history= json.loads(cookies['search_history'])
    except Exception:
        cookie_history= []
else:
    cookie_history= []

if 'search_history' not in st.session_state:
    st.session_state['search_history']= cookie_history

# Save the (updated) history back into cookies
def update_cookies(history):
    cookies['search_history']= json.dumps(history)

def save_history(city):
    # Prevent duplicates
    if city in [entry["City"] for entry in st.session_state['search_history']]:
        return  # City is already in history, no need to add again

    # Add valid city to history
    st.session_state['search_history'].insert(0, {"City": city})
    st.session_state['search_history'] = st.session_state['search_history'][:10]  # Keep last 10 searches

    update_cookies(st.session_state['search_history'])  # Save updated history

# Save search to history
# def save_history(city, start_date, end_date):
#     # Check for duplicates
#     for entry in st.session_state['search_history']:
#         if (entry["City"] == city and entry["Start Date"] == str(start_date) and entry["End Date"] == str(end_date)):
#             # st.warning("This search is already in history.")
#             return
    
#     # Update Weather Data structure (remove icon_path and add relevant fields)
#     new_entry= {
#         "City": city,
#         "Start Date": str(start_date),
#         "End Date": str(end_date),
#         "Timestamp": datetime.now().strftime("%H:%M:%S")
#     }
#     st.session_state['search_history'].insert(0, new_entry)
#     st.session_state['search_history']= st.session_state['search_history'][:10]

#     update_cookies(st.session_state['search_history'])

# Display search history
# def display_history():
#     if st.session_state['search_history']:
#         with st.sidebar:
#             st.markdown("### Search History")
#             df = pd.DataFrame(st.session_state['search_history'])

#             gb = GridOptionsBuilder.from_dataframe(df[["City", "Start Date", "End Date", "Timestamp"]])
#             gb.configure_selection(selection_mode='single', use_checkbox=True)
#             gridOptions = gb.build()

#             # Render the AgGrid
#             grid_response = AgGrid(
#                 df[["City", "Start Date", "End Date", "Timestamp"]],
#                 gridOptions=gridOptions,
#                 update_mode=GridUpdateMode.SELECTION_CHANGED,
#                 height=250,
#                 theme='streamlit'
#             )

#         # Handle selection
#         selected_rows = grid_response.get("selected_rows", [])
#         if selected_rows:
#             selected_city = selected_rows[0]["City"].strip()

#             # ✅ Only update if city changes
#             if selected_city and selected_city != st.session_state.get("city_input", ""):
#                 st.session_state["city_input"] = selected_city
#                 st.session_state["weather_needs_update"] = True
#                 st.session_state["weather_updated"] = False  # Ensure update happens
#                 st.sidebar.success(f"✅ Weather updated for: {selected_city}")
#                 st.rerun()

#     else:
#         st.sidebar.info("No search history available.")

# Clear search history
def clear_history():
    st.session_state['search_history']= []
    update_cookies(st.session_state['search_history'])

    # Re-add detected location after clearing history
    detected_city = fetch_user_location()
    save_history(detected_city)

    st.sidebar.success("Search history cleared.")
    # st.rerun()  # Ensure UI updates immediately

def fetch_coordinates(city):
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}?unitGroup=metric&key={API_key}"
    try:
        response = requests.get(url).json()
        if 'latitude' in response and 'longitude' in response:
            return response['latitude'], response['longitude']
        else:
            st.error(f"Error: Could not find coordinates for '{city}'. Please check the city name.")
            return None, None
    except Exception as e:
        st.error(f"Error fetching coordinates: {e}")
        return None, None

def estimate_relative_humidity(tavg, tmin, tmax):
    if tmax != tmin:
        rh = 100 * (tavg - tmin) / (tmax - tmin)
        return max(0, min(rh, 100))  # Clamp RH between 0 and 100%
    else:
        return np.nan

def calculate_dew_point(tavg, rh):
    if pd.notnull(rh) and pd.notnull(tavg):
        a = 17.27
        b = 237.7
        gamma = np.log(rh / 100) + (a * tavg) / (b + tavg)
        dew_point = (b * gamma) / (a - gamma)
        return round(dew_point, 2)
    else:
        return np.nan

def fetch_historical_data(city, start_date, end_date):
    lat, lon = fetch_coordinates(city)
    if lat is None or lon is None:
        return None

    location = Point(lat, lon)
    data = Daily(location, start_date, end_date)
    data = data.fetch()

    if data.empty:
        st.error("No historical data available for the selected date range.")
        return None

    # Reset index to have 'time' as a column
    data = data.reset_index()

    # Calculate Relative Humidity
    data['Relative Humidity (%)'] = data.apply(
        lambda row: estimate_relative_humidity(row['tavg'], row['tmin'], row['tmax'])
        if pd.notnull(row['tavg']) and pd.notnull(row['tmin']) and pd.notnull(row['tmax'])
        else np.nan,
        axis=1
    )

    # Calculate Dew Point
    data['Dew Point (°C)'] = data.apply(
        lambda row: calculate_dew_point(row['tavg'], row['Relative Humidity (%)']),
        axis=1
    )

    return data

# Function to display weather card
def weather_card(weather_data):

    # Create individual cards
    cards_html = "".join([
        f"""
        <div class="weather-card1">
            <div class="weather-card-content">
                <p class="weather-time">{hour['time']}</p>
                <img src="data:image/png;base64,{hour['icon_path']}" class="weather-icon2" alt="weather icon">
                <p class="weather-temp">{hour['temperature']}°</p>
            </div>
        </div>
        """ for hour in weather_data
    ])
    
    # Style and display the entire container
    st.markdown(
        f"""
        <style>
            .weather-container2 {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                background-color: black;
                padding: 20px;
                border-radius: 10px;
                max-width: 900px;
                margin: 20px auto;
                overflow-x: auto;
            }}
            .weather-card1 {{
                display: inline-block;
                width: 100px;
                padding: 10px 0px;
                border-radius: 10px;
                text-align: center;
                vertical-align: top;
            }}
            .weather-card-content {{
                width:100px;
                text-align: center;
            }}
            .weather-time {{
                margin: 5px;
                font-size: 20px !important;
                font-weight: bold;
                color: #ffffff;
            }}
            .weather-icon2 {{
                width: 40px;
                height: 40px;
            }}
            .weather-temp {{
                margin: 5px;
                font-size: 20px !important;
                font-weight: bold;
                color: #ffffff;
            }}
        </style>
        <div class="weather-container2">
            {cards_html}
        </div>
        """,
        unsafe_allow_html=True
    )

# Function to fetch weather data
def fetch_weather_data(city, unit= 'C'):
    API_key = "2XFY5XGE5W4USB74EQQJN78NC"  
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}?key={API_key}&unitGroup=metric"
    
    try:
        response = requests.get(url)
        data = response.json()

        # Extract hourly forecast data
        hourly_data = data['days'][0].get('hours', [])

        # Get the current hour
        current_time= datetime.now().strftime("%H:%M:%S")
        current_hour= datetime.strptime(current_time, "%H:%M:%S").hour

        # Filter the data to start from the current hour
        hourly_data= [hour for hour in hourly_data if int(hour['datetime'].split(':')[0]) >= current_hour]

        # If there are fewer than 24 hours left in today, add missing hours from tomorrow
        if len(hourly_data) < 24:
            next_day_hour= data['days'][1].get('hours', []) # Get next day's hourly data
            remaining_hour= 24 - len(hourly_data)
            hourly_data.extend(next_day_hour[:remaining_hour])
        
        # Convert to required format
        weather_data = []
        for hour in hourly_data:
            time = datetime.strptime(hour['datetime'], "%H:%M:%S").strftime("%I %p")
            temperature = hour.get('temp', 'N/A')
            humidity = hour.get('humidity', 'N/A')
            precipitation = hour.get('precip', 'N/A')
            rain_prob = hour.get('precipprob', 0)
            snow_prob = hour.get('snowprob', 0)
            fog_prob = hour.get('fog', 0)
            conditions = hour.get('conditions', 'N/A')
            icon = hour.get('icon', 'clear-day')  # Default icon if not available

            if unit == 'F':
                temperature= convert_to_fahrenheit(temperature)
            
            # Assume icon_path is base64-encoded icon; replace with correct method for real icons
            icon_file_path = f"E:/Python.0/Weather live graph/Icon/{icon}.png"
            try:
                with open(icon_file_path, "rb") as img_file:
                    icon_base64 = base64.b64encode(img_file.read()).decode("utf-8")
            except FileNotFoundError:
                icon_base64 = ""  # Default to empty if the file is not found
            
            weather_data.append({
            "time": time,
            "temperature": temperature,
            "humidity": humidity,
            "precipitation": precipitation,
            "conditions": conditions,
            "rain_probability": rain_prob,
            "snow_probability": snow_prob,
            "fog_probability": fog_prob,
            "icon_path": icon_base64
        })

        return weather_data

    except Exception as e:
        st.error(f"Error fetching weather data: {e}")
        return []

def display_notification(forecast_data):
    # Analyze probabilities for rain or snow
    rain_prob = max(hour['rain_probability'] for hour in forecast_data if 'rain_probability' in hour)
    snow_prob = max(hour['snow_probability'] for hour in forecast_data if 'snow_probability' in hour)

    # Extract unique weather conditions
    unique_condition= set(hour['conditions'] for hour in forecast_data if 'condtions' in hour)

    if rain_prob >= 1:
        st.warning(f"🌧️ Chance of rain today ({rain_prob}%). Don't forget your umbrella!")
    elif snow_prob >= 1:
        st.warning(f"❄️ Chance of snow today ({snow_prob}%). Dress warmly!")
    elif "Thunderstorm" in unique_condition:
        st.warning("⛈️ Thunderstorms expected today. Stay indoors if possible!")
    elif "Fog" in unique_condition:
        st.warning("🌫️ Expect foggy conditions today. Drive safely!")
    elif "Clear" in unique_condition:
        st.warning("☀️ Clear skies today! Enjoy your day!")
    else:
        st.info("🌤️ Looks like moderate weather today! Enjoy your day!")

def current_weather(city, unit= 'C'):
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}?key={API_key}&unitGroup=metric"
    try:
        response = requests.get(url)
        data = response.json()
        weather = data.get('currentConditions', {})
        if weather:
            # temp = weather.get('temp')
            # reported_humidity = weather.get('humidity', None)

            # if temp and reported_humidity:
                # Declare variables for temperature, humidity, and other conditions
                # st.write(f"🏠 Results for: {data.get('resolvedAddress', 'N/A')}",  f"Local Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            temperature = weather.get('temp', 'N/A')
            humidity = weather.get('humidity', 'N/A')
            dew_point = weather.get('dew', 'N/A')
            precipitation = weather.get('precip', '0')
            wind_speed = weather.get('windspeed', 'N/A')
            conditions = weather.get('conditions', 'N/A')
            icon = weather.get('icon', 'default')  # Ensure this matches the image filenames
            sunrise = data['days'][0].get('sunrise', 'N/A')
            sunset = data['days'][0].get('sunset', 'N/A')

            if unit == 'F':
                temperature= convert_to_fahrenheit(temperature)

            # def encode_image_to_base64(file_path):
            #     try:
            #         with open(file_path, "rb") as img_file:
            #             return base64.b64encode(img_file.read()).decode("utf-8")
            #     except FileNotFoundError:
            #         return None

            # Generate dynamic image
            if icon != 'N/A':
                icon_url = f"https://raw.githubusercontent.com/Kevinsheta/PROJECT/main/Icon/{icon}.png"
                image_html = f'<img src="{icon_url}" alt="Weather Icon" class="weather-icon1">'
            else:
                image_html = '<p>No Icon Available</p>'

            # HTML for layout
            st.markdown(
                f"""    
                🏠 Results for: {data.get('resolvedAddress', 'N/A')} | Local Time: {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}\n
                **Sunrise:** {sunrise} | **Sunset:** {sunset}
                <style>
                    .weather-container1 {{
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        background-color: black;
                        color: white;
                        padding: 20px;
                        border-radius: 10px;
                        font-family: Arial, sans-serif;
                        max-width: 900px;
                        margin: 20px auto;
                        gap: 15px;
                    }}
                    .icon-temperature-container {{
                        display: flex;
                        align-items: center;
                    }}
                    .weather-icon1 {{
                        width: 80px;
                        height: auto;
                        margin-right: 8px;
                    }}
                    .temperature {{
                        font-size: 35px !important;
                        font-weight: bold;
                    }}
                    .details-container {{
                        flex: 20px;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        font-size: 13px;
                    }}
                    .details {{
                        font-size: 16px;
                        color: #ccc;
                        margin: 5px 0;
                    }}
                    .right-section {{
                        text-align: right;
                        flex: 1;
                    }}
                    .right-section p {{
                        margin: 5px 0;
                        font-size: 16px;
                    }}
                </style>
                <div class="weather-container1">
                    <!-- Icon and Temperature Container -->
                    <div class="icon-temperature-container">
                        {image_html}
                        <p class="temperature">{temperature}°{unit}</p>
                    </div>
                    <!-- Details Container -->
                    <div class="details-container">
                        <p class="details"><b>Precipitation:</b> {precipitation}%</p>
                        <p class="details"><b>Humidity:</b> {humidity}%</p>
                        <p class="details"><b>Wind Speed:</b> {wind_speed} km/h</p>
                        <p class="details"><b>Dew Point:</b> {dew_point}°C</p>
                    </div>
                    <!-- Right Section -->
                    <div class="right-section">
                        <p>{datetime.now().strftime('%A, %I:%M %p')}</p>
                        <p>Weather: {icon}</p>
                        <p>{conditions}</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Save current weather data to history
            weather_data = {
                "Temperature (°C)": temperature,
                "Humidity (%)": humidity,
                "Dew Point (°C)": dew_point,
                "Precipitation (mm)": precipitation,
                "Wind Speed (km/h)": wind_speed,
                "Conditions": conditions,
            }
            return weather_data

        else:
            st.error("Weather data unavailable. Check the city name and API key.")
    except Exception as e:
        st.error(f"Error: {e}")

def display_map(city, lat, lon, weather_data):
    # Initialize the map at the city's location
    weather_map= folium.Map(location=[lat, lon], zoom_start= 10)

    # Add a marker with weather details
    popup_content= f"""
    <b>City:</b> {city}<br>
    <b>Temperature:</b> {weather_data.get('Temperature (°C)', 'N/A')}(°C)<br>
    <b>Humidity:</b> {weather_data.get('Humidity (%)', 'N/A')}%<br>
    <b>Conditions:</b> {weather_data.get('Conditions', 'N/A')}<br>
"""
    folium.Marker(
        location=[lat,lon],
        tooltip= popup_content,
        # tooltip= f"{city} Weather",
        icon= folium.Icon(color= 'blue', icon= 'cloud'),
    ).add_to(weather_map)

    # Handle map interaction using st_folium
    map_data= st_folium(weather_map, height=500, width=800, returned_objects=["last_clicked"])

    # Update session state with clicked location if it exists
    if map_data and map_data.get("last_clicked"):
        st.session_state['map_click']= map_data["last_clicked"]['lat'], map_data["last_clicked"]['lng']

def convert_to_fahrenheit(celsius):
    return round((celsius * 9/5) + 32, 2)

def fetch_forcast_data(city):
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}?unitGroup=metric&key={API_key}"
        try: 
            response= requests.get(url)
            data= response.json()
            forecast_data= data.get('days', [])[:7]

            if not forecast_data:
                st.error('Forecast data unavailable.')
                return []
            
            processed_forecast= []
            for day in forecast_data:  
                processed_forecast.append({
                    'Date': day.get('datetime', 'N/A'),
                    'Tempmax': day.get('tempmax', 'N/A'),
                    'Tempmin': day.get('tempmin', 'N/A'),
                    'Humidity': day.get('humidity', 'N/A'),
                    'Conditions': day.get('conditions', 'N/A'),
                    'Feelslike': day.get('feelslike', 'N/A'),
                    'Wind': day.get('windspeed', 'N/A'),
                    'Wind Direction': day.get('winddir', 'N/A'),
                    'icon': day.get('icon', 'defualt')
                })
            return processed_forecast
        except Exception as e:
            st.error(f'Error fetching forecast data: {e}')
            return []

def fetch_past_weather_data(city):
    # Get today's date
    today = datetime.now().date()
    past_start_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')

    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}/{past_start_date}/{today}?unitGroup=metric&key={API_key}"
    
    try:
        response = requests.get(url)
        data = response.json()
        past_weather_data = data.get('days', [])[:7]

        if not past_weather_data:
            st.error('Past weather data unavailable.')
            return []

        processed_past_data = []
        for day in past_weather_data:
            processed_past_data.append({
                'Date': day.get('datetime', 'N/A'),
                'Tempmax': day.get('tempmax', 'N/A'),
                'Tempmin': day.get('tempmin', 'N/A'),
                'Humidity': day.get('humidity', 'N/A'),
                'Conditions': day.get('conditions', 'N/A'),
                'Feelslike': day.get('feelslike', 'N/A'),
                'Wind': day.get('windspeed', 'N/A'),
                'Wind Direction': day.get('winddir', 'N/A'),
                'icon': day.get('icon', 'default')
            })
        return processed_past_data
    except Exception as e:
        st.error(f'Error fetching past weather data: {e}')
        return []

def display_weather_data(weather_data, city, unit='C', data_type='forecast'):
    if weather_data:
        # Set header title based on data type.
        if data_type.lower() == 'forecast':
            st.markdown(f'### 🌤 1 Week Extended Forecast in {city}')
            today_date = datetime.now().date()
        elif data_type.lower() == 'past':
            st.markdown(f'### ⏳ 1 Week Past Weather in {city}')
            today_date = None  # Not needed for past data
        else:
            st.markdown(f'### Weather Data in {city}')
            today_date = None

        # Create header row with columns for each metric.
        header_day, header_condition, header_temp, header_feels, header_wind, header_winddir = st.columns(6)
        with header_day:
            st.markdown('**Day**')
        with header_condition:
            st.markdown('**Condition**')
        with header_temp:
            st.markdown('**Temperature**')
        with header_feels:
            st.markdown('**Feels Like**')
        with header_wind:
            st.markdown('**Wind**')
        with header_winddir:
            st.markdown('**Wind Direction**')

        # Mapping wind direction abbreviations to arrows.
        wind_arrow = {
            'N': '↑', 'NE': '↗', 'E': '→', 'SE': '↘', 
            'S': '↓', 'SW': '↙', 'W': '←', 'NW': '↖'
        }

        for day in weather_data:
            # Convert the date string to a date object.
            date_str = day.get('Date', 'N/A')
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            except Exception:
                date_obj = None

            # Determine the day name: if forecast and date is today, label as "Today".
            if data_type.lower() == 'forecast' and today_date and date_obj == today_date:
                day_name = 'Today'
            elif date_obj:
                day_name = date_obj.strftime('%A')
            else:
                day_name = 'N/A'

            # Retrieve the icon and attempt to read the corresponding image file.
            icon = day.get('icon', 'default')
            icon_path = fr'E:\Python.0\Weather live graph\Icon\{icon}.png'
            try:
                with open(icon_path, 'rb') as img_file:
                    icon_base64 = base64.b64encode(img_file.read()).decode('utf-8')
            except FileNotFoundError:
                icon_base64 = ''

            # Process wind direction.
            wind_direction = day.get('Wind Direction', 'N/A')
            if wind_direction != 'N/A':
                try:
                    wind_dir_degrees = int(float(wind_direction))
                    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
                    index = round(wind_dir_degrees / 45) % 8
                    wind_dir_text = directions[index]
                    wind_arrow_symbol = wind_arrow.get(wind_dir_text, '❓')
                except Exception:
                    wind_arrow_symbol = '❓'
                    wind_dir_text = 'Unknown'
            else:
                wind_arrow_symbol = '❓'
                wind_dir_text = 'Unknown'

            # Handle temperature conversion if needed.
            if unit == 'F':
                Tempmax = int(convert_to_fahrenheit(day.get('Tempmax', 0)))
                Tempmin = int(convert_to_fahrenheit(day.get('Tempmin', 0)))
            else:
                Tempmax = day.get('Tempmax', 'N/A')
                Tempmin = day.get('Tempmin', 'N/A')

            # Create a row using columns.
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.markdown(f'**{day_name}**')
            with col2:
                if icon_base64:
                    st.markdown(
                        f'<img src="data:image/png;base64,{icon_base64}" alt="{day.get("Conditions", "N/A")}" style="width: 30px; height: 30px; vertical-align: middle;"> {day.get("Conditions", "N/A")}',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(f'{day.get("Conditions", "N/A")}')
            with col3:
                st.markdown(f'{Tempmin}°{unit} / {Tempmax}°{unit}')
            with col4:
                st.markdown(f'{day.get("Feelslike", "N/A")}°C')
            with col5:
                st.markdown(f'{day.get("Wind", "N/A")} km/h')
            with col6:
                st.markdown(f'{wind_arrow_symbol} {wind_dir_text} ({wind_direction}°)')
    else:
        st.info('No weather data available.')

def show_more_news():
    st.session_state["news_page"] = True

def back_to_main():
    st.session_state["news_page"] = False

def filter_relevant_articles(articles):
    """
    Filters articles to only include those with relevant weather terms in the title or description.
    """
    relevant_terms = ["weather", "forecast", "storm", "rain", "hurricane", "snow", "climate", "temperature"]
    filtered_articles = []

    for article in articles:
        title = article.get("title", "").lower()
        description = article.get("description", "").lower()
        
        if any(term in title or term in description for term in relevant_terms):
            filtered_articles.append(article)

    return filtered_articles

def fetch_weather_news():
    # Replace with your own NewsAPI key
    NEWS_API_KEY = "d670d7f8666742a18e8cbb401c9a32b5"
    # Query for weather-related news in English, sorted by latest published
    url = f"https://newsapi.org/v2/everything?q=weather&language=en&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            articles = data.get("articles", [])
            # Filter articles to ensure relevance
            filtered_articles = filter_relevant_articles(articles)
            return filtered_articles
        else:
            st.error("Error fetching weather news: " + response.text)
            return []
    except Exception as e:
        st.error(f"Exception occurred while fetching news: {e}")
        return []

def display_weather_news_summary(articles):
    st.markdown("## 🌦 Weather News")
    
    if articles:
        # Display only the first 5 articles
        for article in articles[:5]:
            title = article.get("title", "No Title")
            description = article.get("description", "No description available.")
            url = article.get("url", "#")
            image_url = article.get("urlToImage", None)
            published_at = article.get("publishedAt", "")
            
            st.markdown(f"### [{title}]({url})")
            if image_url:
                st.image(image_url, width=400)
            st.write(description)
            if published_at:
                try:
                    published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    st.write(f"*Published at: {published_dt.strftime('%Y-%m-%d %I:%M %p')}*")
                except Exception:
                    st.write(f"*Published at: {published_at}*")
            st.markdown("---")
        
    else:
        st.info("No weather news available at this time.")

def display_all_news(articles):
    if articles:
        # Display all articles
        for article in articles:
            title = article.get("title", "No Title")
            description = article.get("description", "No description available.")
            url = article.get("url", "#")
            image_url = article.get("urlToImage", None)
            published_at = article.get("publishedAt", "")
            
            st.markdown(f"### [{title}]({url})")
            if image_url:
                st.image(image_url, width=400)
            st.write(description)
            if published_at:
                try:
                    published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    st.write(f"*Published at: {published_dt.strftime('%Y-%m-%d %I:%M %p')}*")
                except Exception:
                    st.write(f"*Published at: {published_at}*")
            st.markdown("---")
    else:
        st.info("No weather news available at this time.")

def get_forecast_data(city):
    # url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}/next90days?unitGroup=metric&key={API_key}"
    url= f'https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}?unitGroup=metric&key={API_key}'
    response = requests.get(url).json()

    if 'days' in response:
        forecast_data = pd.DataFrame(response['days'])
        return forecast_data
    else:
        st.error("Failed to fetch forecast data.")
        return None
    
def process_forecast_data(forecast_data):
    forecast_data['date'] = pd.to_datetime(forecast_data['datetime'])
    forecast_data.set_index('date', inplace=True)
    forecast_data.rename(columns={
        'temp': 'Average Temperature (°C)',
        'tempmin': 'Minimum Temperature (°C)',
        'tempmax': 'Maximum Temperature (°C)',
        'precip': 'Precipitation (mm)',
        'snow': 'Snowfall (mm)',
        'windspeed': 'Wind Speed (m/s)',
        "wdir": "Wind Direction (°)",
        "pres": "Pressure (hPa)",
        'humidity': 'Relative Humidity (%)',
        'dew': 'Dew Point (°C)'
    }, inplace=True)
    return forecast_data

def plot_weather_graph(city, unit):
    st.write('## Weather Data Visualization')

    # Initialize session state for weather type if not set
    if "weather_type" not in st.session_state:
        st.session_state["weather_type"] = "Forecast Weather"  # Default value

    weather_type= st.radio('Select Weather Date Type:', ('Historical Weather', 'Forecast Weather'))

    # Initialize variables to avoid UnboundLocalError
    # start_date = None
    # end_date = None

    if weather_type == 'Forecast Weather':
        # Fetch and process forecast data
        forecast_data= get_forecast_data(city)

        if forecast_data is not None:
            forecast_data= process_forecast_data(forecast_data)

            # Convert temperatures to Fahrenheit if selected
            if unit == "F":
                if "Average Temperature (°C)" in forecast_data.columns:
                    forecast_data["Average Temperature (°F)"] = convert_to_fahrenheit(forecast_data["Average Temperature (°C)"])
                if "Minimum Temperature (°C)" in forecast_data.columns:
                    forecast_data["Minimum Temperature (°F)"] = convert_to_fahrenheit(forecast_data["Minimum Temperature (°C)"])
                if "Maximum Temperature (°C)" in forecast_data.columns:
                    forecast_data["Maximum Temperature (°F)"] = convert_to_fahrenheit(forecast_data["Maximum Temperature (°C)"])

                # Drop Celsius columns and rename Fahrenheit columns
                forecast_data.drop(columns=["Average Temperature (°C)", "Minimum Temperature (°C)", "Maximum Temperature (°C)"], inplace=True)
                temp_unit = "(°F)"
            else:
                temp_unit = "(°C)"

            st.write('### Forecast Data')

            # Available columns for forecast visualization
            forecast_columns = [
                f"Average Temperature {temp_unit}",
                f"Minimum Temperature {temp_unit}",
                f"Maximum Temperature {temp_unit}",
                "Precipitation (mm)",
                "Snowfall (mm)",
                "Wind Speed (m/s)",
                "Wind Direction (°)",   
                "Pressure (hPa)",
                "Relative Humidity (%)",
                "Dew Point (°C)"
            ]

            # Filter related columns dynamically
            related_columns = {
                f"Average Temperature {temp_unit}": [f"Average Temperature {temp_unit}", f"Minimum Temperature {temp_unit}", f"Maximum Temperature {temp_unit}", "Precipitation (mm)"],
                f"Minimum Temperature {temp_unit}": [f"Average Temperature {temp_unit}", f"Minimum Temperature {temp_unit}", f"Maximum Temperature {temp_unit}", "Precipitation (mm)"],
                f"Maximum Temperature {temp_unit}": [f"Average Temperature {temp_unit}", f"Minimum Temperature {temp_unit}", f"Maximum Temperature {temp_unit}", "Precipitation (mm)"],
                "Precipitation (mm)": ["Precipitation (mm)", "Snowfall (mm)", f"Average Temperature {temp_unit}"],
                "Snowfall (mm)": ["Precipitation (mm)", "Snowfall (mm)", f"Average Temperature {temp_unit}"],
                "Wind Speed (km/h)": ["Wind Speed (km/h)", "Wind Direction (°)", "Pressure (hPa)"],
                "Wind Direction (°)": ["Wind Speed (km/h)", "Wind Direction (°)", "Pressure (hPa)"],
                "Pressure (hPa)": ["Pressure (hPa)", "Wind Speed (km/h)", "Wind Direction (°)"],
                "Relative Humidity (%)": ["Relative Humidity (%)", "Dew Point (°C)", "Snowfall (mm)"],
                "Dew Point (°C)": ["Relative Humidity (%)", "Dew Point (°C)", "Snowfall (mm)"]
            }
            
            st.success("Forecast weather data fetched successfully.")

            # Allow user to select a primary column
            primary_column = st.selectbox("Select a primary column to visualize:", forecast_columns)
            related_selected_columns= related_columns.get(primary_column, [primary_column])
            related_selected_columns= [col for col in related_selected_columns if col in forecast_columns]
            # Allow user to select multiple columns
            selected_column = st.multiselect("Select columns to visualize:", related_selected_columns, default=related_selected_columns)

            # Display forecast data
            if selected_column:
                st.write("### Forecast Weather Data")
                st.dataframe(forecast_data[selected_column])
                plot_graph(forecast_data, city, temp_unit, datetime.now(), datetime.now() + timedelta(days= 7), primary_column, selected_column, 'forecast')
            else:
                st.warning("No valid columns selected for visualization.")
    
        else:
            st.info("No forecast data available. Displaying historical weather data instead.")

    elif weather_type == 'Historical Weather':
        # Fetch historical data only if user selects a date range
        st.sidebar.markdown("### Historical Data")

        start_date = st.sidebar.date_input("Start Date", datetime.now() - timedelta(days=30))
        end_date = st.sidebar.date_input("End Date", datetime.now())

        # Convert to datetime objects
        start_date = datetime.combine(start_date, datetime.min.time())
        end_date = datetime.combine(end_date, datetime.min.time())

        if start_date > end_date:
            st.error("Start date must be before end date.")
        else:
            data = fetch_historical_data(city, start_date, end_date)

            if data is not None and not data.empty: 
                with st.spinner("Just Wait!!"):
                    time.sleep(3)
                # st.dataframe(data.head()) # Display first few rows of data
                

                # Rename columns for better readability
                data = data.rename(columns={
                    "time": "datetime",
                    "tavg": f"Average Temperature (°C)",
                    "tmin": f"Minimum Temperature (°C)",
                    "tmax": f"Maximum Temperature (°C)",
                    "prcp": "Precipitation (mm)",
                    "snow": "Snowfall (mm)",
                    "wspd": "Wind Speed (km/h)",
                    "wdir": "Wind Direction (°)",
                    "pres": "Pressure (hPa)",
                    'humidity': 'Relative Humidity (%)',
                    'dew': 'Dew Point (°C)'
                })

                # Convert historical temperatures to Fahrenheit if selected
                if unit == "F":
                    data["Average Temperature (°F)"] = convert_to_fahrenheit(data["Average Temperature (°C)"])
                    data["Minimum Temperature (°F)"] = convert_to_fahrenheit(data["Minimum Temperature (°C)"])
                    data["Maximum Temperature (°F)"] = convert_to_fahrenheit(data["Maximum Temperature (°C)"])

                    # Drop Celsius columns
                    data.drop(columns=["Average Temperature (°C)", "Minimum Temperature (°C)", "Maximum Temperature (°C)"], inplace=True)
                    temp_unit = "(°F)"
                else:
                    temp_unit = "(°C)"

                # Move "Date" column to the first position
                data = data[["datetime"] + [col for col in data.columns if col != "datetime"]]

                st.write('### Historical Data')
                # Visualization
                available_columns = [
                    f"Average Temperature {temp_unit}",
                    f"Minimum Temperature {temp_unit}",
                    f"Maximum Temperature {temp_unit}",
                    "Precipitation (mm)",
                    "Snowfall (mm)",
                    "Wind Speed (km/h)",
                    "Wind Direction (°)",   
                    "Pressure (hPa)",
                    "Relative Humidity (%)",
                    "Dew Point (°C)"
                ]

                # Filter related columns dynamically
                column_groups = {
                    f"Average Temperature {temp_unit}": [f"Average Temperature {temp_unit}", f"Minimum Temperature {temp_unit}", f"Maximum Temperature {temp_unit}", "Precipitation (mm)"],
                    f"Minimum Temperature {temp_unit}": [f"Average Temperature {temp_unit}", f"Minimum Temperature {temp_unit}", f"Maximum Temperature {temp_unit}", "Precipitation (mm)"],
                    f"Maximum Temperature {temp_unit}": [f"Average Temperature {temp_unit}", f"Minimum Temperature {temp_unit}", f"Maximum Temperature {temp_unit}", "Precipitation (mm)"],
                    "Precipitation (mm)": ["Precipitation (mm)", "Snowfall (mm)", f"Average Temperature {temp_unit}"],
                    "Snowfall (mm)": ["Precipitation (mm)", "Snowfall (mm)", f"Average Temperature {temp_unit}"],
                    "Wind Speed (km/h)": ["Wind Speed (km/h)", "Wind Direction (°)", "Pressure (hPa)"],
                    "Wind Direction (°)": ["Wind Speed (km/h)", "Wind Direction (°)", "Pressure (hPa)"],
                    "Pressure (hPa)": ["Pressure (hPa)", "Wind Speed (km/h)", "Wind Direction (°)"],
                    "Relative Humidity (%)": ["Relative Humidity (%)", "Dew Point (°C)", "Snowfall (mm)"],
                    "Dew Point (°C)": ["Relative Humidity (%)", "Dew Point (°C)", "Snowfall (mm)"]
                }

                st.success("Historical weather data fetched successfully.")
                # Prompt user to select the primary column
                primary_columns = st.selectbox("Select a primary column to visualize:", available_columns)

                # Dynamically filter available columns based on the primary column
                filter_columns = column_groups.get(primary_columns, [primary_columns])

                # Ensure default values are a subset of filtered columns
                default_columns = [col for col in filter_columns if col in available_columns]

                selected_columns = st.multiselect("Select columns to visualize.", filter_columns, default=default_columns)

                if selected_columns:
                    selected_columns_with_date = ["datetime"] + [col for col in selected_columns if col in data.columns]
                    st.write("### Historical Weather Data")
                    st.dataframe(data[selected_columns_with_date])

                    # Ensure plot_graph() is called
                    if selected_columns_with_date:
                        plot_graph(data, city, temp_unit, start_date, end_date, primary_columns, selected_columns_with_date, 'historical')
                    else:
                        st.warning("No valid columns selected for visualization.")
    else:
        st.error("No historical and forecast data available. Please try again!!")

    # Save the search history (ensure start_date and end_date are not None)
    # if start_date is not None and end_date is not None:
    #     save_history(city, start_date, end_date)

def plot_graph(data, city, temp_unit, start_date, end_date, primary_columns, selected_columns, data_type):
    # Convert start_date and end_date to datetime if they are strings
    if isinstance(start_date, str):
        start_date = pd.to_datetime(start_date)
    if isinstance(end_date, str):
        end_date = pd.to_datetime(end_date)

    # Check if only one column is selected
    if len(selected_columns) == 1:
        column = selected_columns[0]
        plot_type = st.selectbox("Select Plot Type", ["line", "scatter"], key= f'plot_type_select_{primary_columns}_{data_type}')

        data[column] = data[column].interpolate()

        if plot_type == "line":
            fig = px.line(
                data_frame=data,
                x="datetime",
                y=column,
                title=f"{column} in {city}: {start_date.date()} to {end_date.date()}",
                labels={"value": "Weather", "variable": "Category"},
            )
            fig.update_traces(mode= 'markers+lines')

        elif plot_type == "scatter":
            fig = px.scatter(
                data_frame=data,
                x="datetime",
                y=column,
                title=f"{column} in {city}: {start_date.date()} to {end_date.date()}",
                labels={"value": "Weather", "variable": "Category"}
            )
            fig.update_traces(mode= 'markers')
        fig.update_layout(
            template= 'plotly_dark',
            hovermode= 'x unified'
        )
        st.plotly_chart(fig)

    # Multi-column visualization logic
    if len(selected_columns) > 1:
        st.write("Visualizing multiple columns...")
        
        if primary_columns == f"Average Temperature {temp_unit}":
            with st.spinner("Just Wait!!"):
                time.sleep(3)
            st.write('### Graph 1: Temperature Overview')
            plot_type= st.selectbox("Select plot type:", ['line', 'scatter'], key=f'avg_temp_plot1_{primary_columns}_{data_type}')

            data[[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}']] = data[[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}']].interpolate()
            
            if plot_type == 'line':
                fig1= px.line(
                    data_frame=data,
                    x='datetime',
                    y= [f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}'],
                    title= f"Temperature in {city}: {start_date.date()} to {end_date.date()}",
                    labels={'value': f'Temperature {temp_unit}', 'variable': 'Category'},
                    color_discrete_sequence= ['red', 'green', 'blue']
                )
                fig1.update_traces(mode= 'markers+lines')
            
            elif plot_type == 'scatter':
                fig1= px.scatter(
                    data_frame=data,
                    x= 'datetime',
                    y= [f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}'],
                    title= f"Temperature in {city}: {start_date.date()} to {end_date.date()}",
                    labels= {'value': f'Temerature {temp_unit}', 'variable': 'Category'},
                    color_discrete_sequence= ['red', 'green', 'blue']
                )
                fig1.update_traces(mode= 'markers')

            fig1.update_layout(
                template= 'plotly_dark',
                showlegend= True,
                xaxis_type= 'date',
                legend_title= "Temperature Type",
                hovermode= 'x unified',
                xaxis= dict(
                    showgrid= True,
                    gridcolor= "gray",
                    gridwidth= 0.5
                ),
                yaxis= dict(
                    showgrid= True,
                    gridcolor= 'gray',
                    gridwidth= 0.5
                )
            )
            st.plotly_chart(fig1)

            st.write('### Graph 2: Average Temperature and Precipitation')
            plot_type= st.selectbox('Select plot type:', ['line', 'scatter'], key=f'avgpre_{primary_columns}_{data_type}')
                
            data[[f'Average Temperature {temp_unit}', "Precipitation (mm)"]] = data[[f'Average Temperature {temp_unit}', 'Precipitation (mm)']].interpolate()

            if plot_type == 'line':
                fig2= px.line(
                    data_frame= data,
                    x= 'datetime',
                    y= [f'Average Temperature {temp_unit}', 'Precipitation (mm)'],
                    title= f'Average Temerature and Precipitation in {city}: {start_date.date()} to {end_date.date()}',
                    labels= {'value': 'Weather', 'variable': 'Category'}
                )
                fig2.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig2= px.scatter (
                    data_frame= data,
                    x= 'datetime',
                    y= [f'Average Temperature {temp_unit}', 'Precipitation (mm)'],
                    title= f'Average Temerature and Precipitation in {city}: {start_date.date()} to {end_date.date()}',
                    labels= {'value': 'Weather', 'variable': 'Category'}
                )
                fig2.update_traces(mode= 'markers')

            fig2.update_layout(
                template= 'plotly_dark',
                showlegend= True,
                xaxis_type= 'date',
                legend_title= "Weather Type",
                hovermode= 'x unified'
            )
            st.plotly_chart(fig2)
        
        elif primary_columns == f"Minimum Temperature {temp_unit}":
            # Graph 1: Combination of three temperature columns and precipitation
            with st.spinner("Just Wait!!"):
                time.sleep(3)
            st.write("### Graph 1: Temperature Overview")
            plot_type = st.selectbox("Select plot type:", ["line", "scatter"], key= f'min_temp_plot1_{primary_columns}_{data_type}')
            data[[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}']] = data[[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}']].interpolate()

            if plot_type == "line":
                fig1 = px.line(
                    data_frame=data,
                    x='datetime',
                    y=[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}'],
                    title=f"Temperature in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"value": "Temperature (°C)", "variable": "Category"},
                    color_discrete_sequence=['red','green','blue'])
                fig1.update_traces(mode= 'markers+lines')
            elif plot_type == "scatter":
                fig1 = px.scatter(
                    data_frame=data,
                    x='datetime',
                    y=[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}'],
                    title=f"Temperature in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"x": "Date/Time", "value": "Metric", "variable": "Category"},
                    color_discrete_sequence=['red','green','blue'])
                fig1.update_traces(mode= 'markers')

            fig1.update_layout(
                template= 'plotly_dark',
                showlegend=True,
                xaxis_type='date',
                hovermode= 'x unified',
                xaxis= dict(
                    showgrid= True,
                    gridcolor= "gray",
                    gridwidth= 0.5
                ),
                yaxis= dict(
                    showgrid= True,
                    gridcolor= 'gray',
                    gridwidth= 0.5
                )
                )
            st.plotly_chart(fig1)

            # Graph 2: Minimum Temperature and Precipitation
            st.write("### Graph 2: Minimum Temperature and Precipitation")
            plot_type = st.selectbox("Select plot type:", ["line", "scatter"], key= f"min_temp_precip_{primary_columns}_{data_type}")
            data[[f"Minimum Temperature {temp_unit}", "Precipitation (mm)"]] = data[[f"Minimum Temperature {temp_unit}", "Precipitation (mm)"]].interpolate()

            if plot_type == "line":
                fig2 = px.line(
                    data_frame=data,
                    x="datetime",
                    y=[f"Minimum Temperature {temp_unit}", "Precipitation (mm)"],
                    title=f"Minimum Temperature and Precipitation in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"value": "Weather", "variable": "Category"}
                )
                fig2.update_traces(mode= 'markers+lines')

            elif plot_type == "scatter":
                fig2 = px.scatter(
                    data_frame=data,
                    x="datetime",
                    y=[f"Minimum Temperature {temp_unit}", "Precipitation (mm)"],
                    title=f"Minimum Temperature and Precipitation in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"value": "Weather", "variable": "Category"}
                )
                fig2.update_traces(mode= 'markers')
            fig2.update_layout(
                template= 'plotly_dark',
                showlegend= True,
                xaxis_type= 'date',
                legend_title= "Weather Type",
                hovermode= 'x unified'
            )
            st.plotly_chart(fig2)

        elif primary_columns == f"Maximum Temperature {temp_unit}":
            # Graph 1: Combination of three temperature columns and precipitation
            with st.spinner("Just Wait!!"):
                time.sleep(3)
            st.write("### Graph 1: Temperature Overview")
            plot_type = st.selectbox("Select plot type:", ["line", "scatter"], key= f'max_temp_plot1_{primary_columns}_{data_type}')
            data[[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}']] = data[[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}']].interpolate()

            if plot_type == "line":
                fig1 = px.line(
                    data_frame=data,
                    x='datetime',
                    y=[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}'],
                    title=f"Temperature in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"value": "Temperature (°C)", "variable": "Category"},
                    color_discrete_sequence=['red','green','blue'])
                fig1.update_traces(mode= 'markers+lines')
            
            elif plot_type == "scatter":
                fig1 = px.scatter(
                    data_frame=data,
                    x='datetime',
                    y=[f'Maximum Temperature {temp_unit}', f'Average Temperature {temp_unit}',  f'Minimum Temperature {temp_unit}'],
                    title=f"Temperature in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"x": "Date/Time", "value": "Metric", "variable": "Category"},
                    color_discrete_sequence=['red','green','blue'])
                fig1.update_traces(mode= 'markers')

            fig1.update_layout(
                template= 'plotly_dark',
                showlegend=True,
                xaxis_type='date',
                hovermode= 'x unified',
                xaxis= dict(
                    showgrid= True,
                    gridcolor= "gray",
                    gridwidth= 0.5
                ),
                yaxis= dict(
                    showgrid= True,
                    gridcolor= 'gray',
                    gridwidth= 0.5
                )
                )
            st.plotly_chart(fig1)

            # Graph 2: Maximum Temperature and Precipitation
            st.write("### Graph 2: Maximum Temperature and Precipitation")
            plot_type = st.selectbox("Select plot type:", ["line", "scatter"], key= f"max_temp_precip_{primary_columns}_{data_type}")
            data[[f"Maximum Temperature {temp_unit}", "Precipitation (mm)"]] = data[[f"Maximum Temperature {temp_unit}", "Precipitation (mm)"]].interpolate()

            if plot_type == "line":
                fig2 = px.line(
                    data_frame=data,
                    x="datetime",
                    y=[f"Maximum Temperature {temp_unit}", "Precipitation (mm)"],
                    title=f"Maximum Temperature and Precipitation in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"value": "Weather", "variable": "Category"}
                )
                fig2.update_traces(mode= 'markers+lines')
            elif plot_type == "scatter":
                fig2 = px.scatter(
                    data_frame=data,
                    x="datetime",
                    y=[f"Maximum Temperature {temp_unit}", "Precipitation (mm)"],
                    title=f"Maximum Temperature and Precipitation in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"value": "Weather", "variable": "Category"}
                )
                fig2.update_traces(mode= 'markers')
            fig2.update_layout(
                template= 'plotly_dark',
                showlegend= True,
                xaxis_type= 'date',
                legend_title= "Weather Type",
                hovermode= 'x unified'
            )
            st.plotly_chart(fig2)

        elif primary_columns == "Precipitation (mm)":
            # Graph 1: Precipitation and Snowfall
            st.write("### Graph 1: Precipitation and Snowfall")
            plot_type = st.selectbox("Select plot type:", ["line", "scatter"], key= f"precip_snowfall_{primary_columns}_{data_type}")
            data[['Precipitation (mm)', 'Snowfall (mm)']] = data[['Precipitation (mm)', 'Snowfall (mm)']].interpolate()

            if plot_type == 'line':
                fig1 = px.line(
                    data_frame=data,
                    x='datetime',
                    y=['Precipitation (mm)', 'Snowfall (mm)'],
                    title=f"Precipitation and Snowfall in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"x": "Date/Time", "value": "Weather", "variable": "Category"}
                )
                fig1.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig1 = px.scatter(
                    data_frame=data,
                    x='datetime',
                    y=['Precipitation (mm)', 'Snowfall (mm)'],
                    title=f"Precipitation and Snowfall in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"x": "Date/Time", "value": "Weather", "variable": "Category"}
                )
                fig1.update_traces(mode= 'markers')
            fig1.update_layout(
                template= 'plotly_dark',
                showlegend=True,
                xaxis_type='date',
                hovermode= 'x unified',
                xaxis= dict(
                    showgrid= True,
                    gridcolor= "gray",
                    gridwidth= 0.5
                ),
                yaxis= dict(
                    showgrid= True,
                    gridcolor= 'gray',
                    gridwidth= 0.5
                )
                )
            st.plotly_chart(fig1)

            # Graph 2: Precipitation and Average Temperature
            st.write("### Graph 2: Precipitation and Average Temperature")
            plot_type = st.selectbox("Select plot type:", ["line", "scatter"], key= f"precip_temp_{primary_columns}_{data_type}")
            data[[f"Average Temperature {temp_unit}", "Precipitation (mm)"]] = data[[f"Average Temperature {temp_unit}", "Precipitation (mm)"]].interpolate()

            if plot_type == "line":
                fig2 = go.Figure()
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data["Precipitation (mm)"],
                    name= "Precipitation (mm)",
                    mode= "lines",
                    line= dict(color= 'blue', width= 2)))
                
                fig2.add_trace(go.Line(
                    x=data.index,
                    y= data[f"Average Temperature {temp_unit}"],
                    name= f"Average Temperature {temp_unit}",
                    mode= "lines",
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'))
                fig2.update_traces(mode= 'markers+lines')

            elif plot_type == "scatter":
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data["Precipitation (mm)"],
                    name= "Precipitation (mm)",
                    mode= "markers",
                    marker= dict(color= 'blue', size= 8)))
                
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data[f"Average Temperature {temp_unit}"],
                    name= f"Average Temperature {temp_unit}",
                    mode= "markers",
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'))
                fig2.update_traces(mode= 'markers')

            # Add layout for secondary y-axis
            fig2.update_layout(
                template= 'plotly_dark',
                title=f"Precipitation and Average Temperature in {city}: {start_date.date()} to {end_date.date()}",
                xaxis=dict(title="Date"),
                yaxis=dict(title="Precipitation (mm)"),
                yaxis2=dict(
                    title=f"Average Temperature {temp_unit}",
                    overlaying='y',
                    side='right'),
                legend=dict(
                    x=1.0,
                    xanchor='left',
                    y=1.1),
                hovermode= 'x unified'
            )
            st.plotly_chart(fig2)

        elif primary_columns == "Snowfall (mm)":
            # Graph 1: Snowfall and Precipitation
            st.write("### Graph 1: Snowfall and Precipitation")
            plot_type = st.selectbox("Select plot type:", ["line", "scatter"], key= f"snowfall_precip_{primary_columns}_{data_type}")
            data[['Precipitation (mm)', 'Snowfall (mm)']] = data[['Precipitation (mm)', 'Snowfall (mm)']].interpolate()

            if plot_type == 'line':
                fig1 = px.line(
                    data_frame=data,
                    x='datetime',
                    y=['Precipitation (mm)', 'Snowfall (mm)'],
                    title=f"Snowfall and Precipitation in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"x": "Date/Time", "value": "Weather", "variable": "Category"}
                )
                fig1.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig1 = px.scatter(
                    data_frame=data,
                    x='datetime',
                    y=['Precipitation (mm)', 'Snowfall (mm)'],
                    title=f"Snowfall and Precipitation in {city}: {start_date.date()} to {end_date.date()}",
                    labels={"x": "Date/Time", "value": "Weather", "variable": "Category"}
                )
                fig1.update_traces(mode= 'markers')
            fig1.update_layout(
                template= 'plotly_dark',
                showlegend=True,
                xaxis_type='date',
                hovermode= 'x unified',
                xaxis= dict(
                    showgrid= True,
                    gridcolor= "gray",
                    gridwidth= 0.5
                ),
                yaxis= dict(
                    showgrid= True,
                    gridcolor= 'gray',
                    gridwidth= 0.5
                ))
            st.plotly_chart(fig1)

            # Graph 2: Snowfall and Average Temperature
            st.write("### Graph 2: Snowfall and Average Temperature")
            plot_type = st.selectbox("Select plot type:", ["line", "scatter"], key= f"snowfall_temp_{primary_columns}_{data_type}")
            data[[f"Average Temperature {temp_unit}", "Snowfall (mm)"]] = data[[f"Average Temperature {temp_unit}", "Snowfall (mm)"]].interpolate()

            if plot_type == "line":
                fig2 = go.Figure()
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data["Snowfall (mm)"],
                    name= "Snowfall (mm)",
                    mode= "lines",
                    line= dict(color= 'blue', width= 2)))
                
                fig2.add_trace(go.Line(
                    x=data.index,
                    y= data[f"Average Temperature {temp_unit}"],
                    name= f"Average Temperature {temp_unit}",
                    mode= "lines",
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'))
                fig2.update_traces(mode= 'markers+lines')
                
            elif plot_type == "scatter":
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data["Snowfall (mm)"],
                    name= "Snowfall (mm)",
                    mode= "markers",
                    marker= dict(color= 'blue', size= 8)))
                
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data[f"Average Temperature {temp_unit}"],
                    name= f"Average Temperature {temp_unit}",
                    mode= "markers",
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'))
                fig2.update_traces(mode= 'markers')

            # Add layout for secondary y-axis
            fig2.update_layout(
                template= 'plotly_dark',
                title=f"Snowfall and Average Temperature in {city}: {start_date.date()} to {end_date.date()}",
                xaxis=dict(title="Date"),
                yaxis=dict(title="Snowfall (mm)"),
                yaxis2=dict(
                    title=f"Average Temperature {temp_unit}",
                    overlaying='y',
                    side='right'),
                legend=dict(
                    x=1.0,
                    xanchor='left',
                    y=1.1),
                hovermode= 'x unified'
            )
            st.plotly_chart(fig2)


        elif primary_columns == 'Wind Speed (km/h)':
            st.write('### Graph 1: Wind Speed and Wind Direction')
            plot_type= st.selectbox("Select plot type:", ['line', 'scatter'], key= f'wsdir_{primary_columns}_{data_type}')
            data[['Wind Direction (°)','Wind Speed (km/h)']] = data[['Wind Direction (°)','Wind Speed (km/h)']].interpolate()
            
            fig1= go.Figure()
            if plot_type == 'line':
                fig1.add_trace(go.Line(
                    x= data.index,
                    y= data['Wind Direction (°)'],
                    name= 'Wind Direction (°)',
                    mode= 'lines',
                    line= dict(color= 'blue', width= 2)
                ))
                fig1.add_trace(go.Line(
                    x= data.index,
                    y= data['Wind Speed (km/h)'],
                    name= 'Wind Speed (km/h)',
                    mode= 'lines',
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'
                ))
                fig1.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig1.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Wind Direction (°)'],
                    name= 'Wind Direction (°)',
                    mode= 'markers',
                    marker= dict(color= 'blue', size= 8)
                ))
                fig1.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Wind Speed (km/h)'],
                    name= 'Wind Speed (km/h)',
                    mode= 'markers',
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'
                ))
                fig1.update_traces(mode= 'markers')

            fig1.update_layout(
                template= 'plotly_dark',
                title= f'Wind Data Visualization in {city}: {start_date.date()} to {end_date.date()}',
                xaxis= dict(title= "Date",
                            showgrid= True),
                yaxis= dict(title= 'Wind Direction (°)', showgrid= True),
                yaxis2= dict(
                    title= 'Wind Speed (km/h)',
                    overlaying= 'y',
                    side= 'right',
                    showgrid= False
                ),
                legend= dict(
                    x= 1.0,
                    xanchor= 'left',
                    y= 1.1
                ),
                hovermode= 'x unified'
            )
            st.plotly_chart(fig1)

            st.write('### Graph 2: Wind Speed and Pressure')
            plot_type= st.selectbox("Select plot type", ['line', 'scatter'], key= f'wpre{primary_columns}_{data_type}')
            data[['Wind Speed (km/h)', 'Pressure (hPa)']] = data[['Wind Speed (km/h)', 'Pressure (hPa)']].interpolate()

            fig2= go.Figure()
            if plot_type == 'line':
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Wind Speed (km/h)'],
                    name= 'Wind Speed (km/h)',
                    mode= 'lines',
                    line= dict(color= 'blue', width= 2)
                ))
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Pressure (hPa)'],
                    name= 'Pressure (hPa)',
                    mode= 'lines',
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Wind Speed (km/h)'],
                    name= 'Wind Speed (km/h)',
                    mode= 'markers',
                    marker= dict(color= 'blue', size= 8)
                ))
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Pressure (hPa)'],
                    name= 'Pressure (hPa)',
                    mode= 'markers',
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers')

            fig2.update_layout(
                template= 'plotly_dark',
                title= f'Wind Speed and Pressure in {city}: {start_date.date()} to {end_date.date()}',
                xaxis_title= 'Date',
                yaxis_title= 'Wind Speed (km/h)',
                yaxis2= dict(title= 'Pressure (hPa)',
                            overlaying= 'y',
                            side= 'right',
                            showgrid= False),
                legend= dict(x= 1.0,
                            xanchor= 'left',
                            y= 1.1),
                hovermode= 'x unified'
                )
            st.plotly_chart(fig2)
        
        elif primary_columns == 'Wind Direction (°)':
            st.write('### Graph 1: Wind Direction and Wind Speed')
            plot_type= st.selectbox('Select plot type:', ['line', 'scatter'], key= f'wind_dir_plot1_{primary_columns}_{data_type}')
            data[['Wind Direction (°)', 'Wind Speed (km/h)']] = data[['Wind Direction (°)', 'Wind Speed (km/h)']].interpolate()                

            fig1= go.Figure()
            if plot_type== 'line':
                fig1.add_trace(go.Line(
                    x= data.index,
                    y= data['Wind Direction (°)'],
                    name= 'Wind Direction (°)',
                    mode= 'lines',
                    line= dict(color= 'blue', width= 2)
                ))

                fig1.add_trace(go.Line(
                    x= data.index,
                    y= data['Wind Speed (km/h)'],
                    name= 'Wind Speed (km/h)',
                    mode= 'lines',
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'
                ))
                fig1.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig1.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Wind Direction (°)'],
                    name= 'Wind Direction (°)',
                    mode= 'markers',
                    marker= dict(color= 'blue', size= 8)
                ))
                fig1.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Wind Speed (km/h)'],
                    name= 'Wind Speed (km/h)',
                    mode= 'markers',
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'
                ))
                fig1.update_traces(mode= 'markers')

            fig1.update_layout(
                template= 'plotly_dark',
                title= f'Wind Direction and Wind Speed in {city}: {start_date.date()} to {end_date.date()}',
                xaxis= dict(title= 'Date',
                            showgrid= True),
                yaxis= dict(title= 'Wind Direction (°)'),
                yaxis2= dict(title= 'Wind Speed (km/h)',
                            overlaying= 'y',
                            side= 'right',
                            showgrid= False),
                legend= dict(x= 1.0,
                            xanchor= 'left',
                            y= 1.1),
                hovermode= 'x unified'
            )   
            st.plotly_chart(fig1)

            st.write('### Graph 2: Wind Direction and Pressure')
            plot_type= st.selectbox('Select plot type:', ['line', 'scatter'], key= f'wdpr_{primary_columns}_{data_type}')
            data[['Wind Direction (°)', 'Pressure (hPa)']] = data[['Wind Direction (°)', 'Pressure (hPa)']].interpolate()

            fig2= go.Figure()
            if plot_type== 'line':
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Wind Direction (°)'],
                    name= 'Wind Direction (°)',
                    mode= 'lines',
                    line= dict(color= 'blue', width= 2)
                ))
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Pressure (hPa)'],
                    name= 'Pressure (hPa)',
                    mode= 'lines',
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Wind Direction (°)'],
                    name= 'Wind Direction (°)',
                    mode= 'markers',
                    marker= dict(color= 'blue', size= 8)
                ))
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Pressure (hPa)'],
                    name= 'Pressure (hPa)',
                    mode= 'markers',
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers')

            fig2.update_layout(
                template= 'plotly_dark',
                title= f'Wind Direction and Pressure in {city}: {start_date.date()} to {end_date.date()}',
                xaxis= dict(title= 'Date'),
                yaxis= dict(title= 'Wind Direction (°)'),
                yaxis2= dict(title= 'Pressure (hPa)',
                            overlaying= 'y',
                            side= 'right'),
                legend= dict(x= 1.0,
                            xanchor= 'left',
                            y= 1.1),
                hovermode= 'x unified'
            )   
            st.plotly_chart(fig2)
        
        elif primary_columns == 'Pressure (hPa)':
            st.write('### Graph 1: Pressure')
            plot_type= st.selectbox('Select plot type:', ['line', 'scatter'], key= f'pressure_plot1_{primary_columns}_{data_type}')
            data[['Pressure (hPa)']] = data[['Pressure (hPa)']].interpolate()

            if plot_type == 'line':
                fig1= px.line(
                    data_frame= data,
                    x= 'datetime',
                    y= ['Pressure (hPa)'],
                    title= f'Pressure in {city}: {start_date.date()} to {end_date.date()}',
                    labels= {'value': 'Pressure (hPa)', 'variable': 'Category'}
                )
                fig1.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig1= px.scatter(
                    data_frame= data,
                    x= 'datetime',
                    y= ['Pressure (hPa)'],
                    title= f'Pressure in {city}: {start_date.date()} to {end_date.date()}',
                    labels= {'value': 'Pressure (hPa)', 'variable': 'Category'}
                )
                fig1.update_traces(mode= 'markers')

            fig1.update_layout(
                template= 'plotly_dark',
                showlegend=True,
                xaxis_type='date',
                hovermode= 'x unified',
                xaxis= dict(
                    showgrid= True,
                    gridcolor= "gray",
                    gridwidth= 0.5
                ),
                yaxis= dict(
                    showgrid= True,
                    gridcolor= 'gray',
                    gridwidth= 0.5
                ))
            st.plotly_chart(fig1)

            st.write('### Graph 2: Pressure and Wind Speed')
            plot_type= st.selectbox('Select plot type:', ['line', 'scatter'], key= f'pws_{primary_columns}_{data_type}')
            data[['Pressure (hPa)', 'Wind Speed (km/h)']] = data[['Pressure (hPa)', 'Wind Speed (km/h)']].interpolate()

            fig2= go.Figure()
            if plot_type == 'line':
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Pressure (hPa)'],
                    name= 'Pressure',
                    mode= 'lines',
                    line= dict(color= 'blue', width= 2)
                ))
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Wind Speed (km/h)'],
                    name= 'Wind Speed (km/h)',
                    mode= 'lines',
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Pressure (hPa)'],
                    name= 'Pressure (hPa)',
                    mode= 'markers',
                    marker= dict(color= 'blue', size= 8)
                ))
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Wind Speed (km/h)'],
                    name= 'Wind Speed (km/h)',
                    mode= 'markers',
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers')

            fig2.update_layout(
                template= 'plotly_dark',
                title= f'Pressure and Wind Speed in {city}: {start_date.date()} to {end_date.date()}',
                xaxis= dict(title= 'Date'),
                yaxis= dict(title= 'Pressure (hPa)'),
                yaxis2= dict(title= 'Wind Speed (km/h)',
                            overlaying= 'y',
                            side= 'right',
                            showgrid= False),
                legend= dict(x= 1.0,
                            xanchor= 'left',
                            y= 1.1),
                hovermode= 'x unified'
            )
            st.plotly_chart(fig2)

            st.write('### Graph 3: Pressure and Wind Direction')
            plot_type= st.selectbox('Select plot type:', ['line', 'scatter'], key= f'prwd_{primary_columns}_{data_type}')
            data[['Pressure (hPa)', 'Wind Direction (°)']]= data[['Pressure (hPa)', 'Wind Direction (°)']].interpolate()

            if plot_type == 'line':
                fig3= go.Figure()
                fig3.add_trace(go.Line(
                    x= data.index,
                    y= data['Pressure (hPa)'],
                    name= 'Pressure (hPa)',
                    mode= 'lines',
                    line= dict(color= 'blue', width= 2)
                ))
                fig3.add_trace(go.Line(
                    x= data.index,
                    y= data['Wind Direction (°)'],
                    name= 'Wind Direction (°)',
                    mode= 'lines',
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'
                ))
                fig3.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig3= go.Figure()
                fig3.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Pressure (hPa)'],
                    name= 'Pressure (hPa)',
                    mode= 'markers',
                    marker= dict(color= 'blue', size= 8)
                ))
                fig3.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Wind Direction (°)'],
                    name= 'Wind Direction (°)',
                    mode= 'markers',
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'
                ))
                fig3.update_traces(mode= 'markers')

            fig3.update_layout(
                template= 'plotly_dark',
                title= f'Pressure and Wind Direction in {city}: {start_date.date()} to {end_date.date()}',
                xaxis= dict(title= 'Date'),
                yaxis= dict(title= 'Pressure'),
                yaxis2= dict(title= 'Wind Direction',
                            overlaying= 'y',
                            side= 'right',
                            showgrid= False),
                legend= dict(x= 1.0,
                            xanchor= 'left',
                            y= 1.1),
                hovermode= 'x unified'
            )
            st.plotly_chart(fig3)

        elif primary_columns == 'Relative Humidity (%)':
            st.write('### Graph 1: Relative Humidity and Dew Point')
            plot_type= st.selectbox("Select Plot Type", ["line", "scatter"], key= f'rh_dp_plot1_{primary_columns}_{data_type}')
            data[['Relative Humidity (%)', 'Dew Point (°C)']] = data[['Relative Humidity (%)', 'Dew Point (°C)']].interpolate()

            fig1= go.Figure()
            if plot_type == 'line':
                # Add the first trace for Wind Direction
                fig1.add_trace(go.Line(
                    x=data.index,
                    y=data['Relative Humidity (%)'],
                    name='Relative Humidity (%)',
                    mode='lines',
                    line=dict(color='blue', width=2)))
                
                # Add the second trace for Wind Speed with a secondary y-axis
                fig1.add_trace(go.Line(
                    x=data.index,
                    y=data['Dew Point (°C)'],
                    name='Dew Point (°C)',
                    mode='lines',
                    line=dict(color='red', width=2),
                    yaxis='y2'))
                fig1.update_traces(mode= 'markers+lines')
                
            elif plot_type == 'scatter':
                fig1.add_trace(go.Scatter(
                    x=data.index,
                    y=data['Relative Humidity (%)'],
                    name="Relative Humidity (%)",
                    mode='markers',
                    marker=dict(color='blue', size=8)))
                fig1.add_trace(go.Scatter(
                    x=data.index,
                    y=data['Dew Point (°C)'],
                    name="Dew Point (°C)",
                    mode='markers',
                    marker=dict(color='red', size=8),
                    yaxis='y2'))
                fig1.update_traces(mode= 'markers')
                
            # Add layout for secondary y-axis
            fig1.update_layout(
                template= 'plotly_dark',
                title=f"Relative Humidity and Dew Point in {city}: {start_date.date()} to {end_date.date()}",
                xaxis=dict(title="Date", showgrid= True),  # Corrected x-axis title
                yaxis=dict(title="Relative Humidity (%)", showgrid= True),  # Primary y-axis title
                yaxis2=dict(
                    title="Dew Point (°C)",  # Secondary y-axis title
                    overlaying='y',  # Overlay secondary y-axis on primary y-axis
                    side='right',
                    showgrid= False),  # Place secondary y-axis on the right
                legend=dict(
                    x=1.0,
                    xanchor='left',
                    y=1.1),
                hovermode= 'x unified')
                
            st.plotly_chart(fig1)

            st.write('### Graph 2: Relative Humidity and Snowfall')
            plot_type= st.selectbox('Select plot type:', ['line', 'scatter'], key= f'rhs_{primary_columns}_{data_type}')
            data[['Relative Humidity (%)', 'Snowfall (mm)']] = data[['Relative Humidity (%)', 'Snowfall (mm)']].interpolate()

            fig2= go.Figure()
            if plot_type == 'line':
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Relative Humidity (%)'],
                    name= 'Relative Humidity (%)',
                    mode= 'lines',
                    line= dict(color= 'blue', width= 2)
                ))
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Snowfall (mm)'],
                    name= 'Snowfall (mm)',
                    mode= 'lines',
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers+lines')
                
            elif plot_type == 'scatter':
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Relative Humidity (%)'],
                    name= 'Relative Humidity (%)',
                    mode= 'markers',
                    marker= dict(color= 'blue', size= 8)
                ))
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Snowfall (mm)'],
                    name= 'Snowfall (mm)',
                    mode= 'markers',
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers')

            fig2.update_layout(
                template= 'plotly_dark',
                title= f"Relative Humidity and Snowfall in {city}: {start_date.date()} to {end_date.date()}",
                xaxis= dict(title= 'Date'),
                yaxis= dict(title= 'Relative Humidity (%)'),
                yaxis2= dict(title= 'Snowfall (mm)',
                            overlaying= 'y',
                            side= 'right',
                            showgrid= False),
                legend= dict(x= 1.0,
                            xanchor= 'left',
                            y= 1.1),
                hovermode= 'x unified'
            )
            st.plotly_chart(fig2)

        elif primary_columns == 'Dew Point (°C)':
            st.write('### Graph 1: Dew Point and Relative Humidity')
            plot_type= st.selectbox('Select plot type:', ['line', 'scatter'], key= f'dw_rh_plot1_{primary_columns}_{data_type}')
            data[['Dew Point (°C)', 'Relative Humidity (%)']] = data[['Dew Point (°C)', 'Relative Humidity (%)']].interpolate()

            if plot_type == 'line':
                fig1= go.Figure()
                fig1.add_trace(go.Line(
                    x= data.index,
                    y= data['Dew Point (°C)'],
                    name= 'Dew Point (°C)',
                    mode= 'lines',
                    line= dict(color= 'blue', width= 2)
                ))

                fig1.add_trace(go.Line(
                    x= data.index,
                    y= data['Relative Humidity (%)'],
                    name= 'Relative Humidity (%)',
                    mode= 'lines',
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'
                ))
                fig1.update_traces(mode= 'markers+lines')

            elif plot_type == 'scatter':
                fig1= go.Figure() 
                fig1.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Dew Point (°C)'],
                    name= 'Dew Point (°C)',
                    mode= 'markers',
                    marker= dict(color= 'blue', size= 8)
                ))
                fig1.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Snowfall (mm)'],
                    name= 'Snowfall (mm)',
                    mode= 'markers',
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'
                ))
                fig1.update_traces(mode= 'markers')

            fig1.update_layout(
                template= 'plotly_dark',
                title= f'Dew Point and Relative Humidity in {city}: {start_date.date()} to {end_date.date()}',
                xaxis= dict(title= 'Date', showgrid= True),
                yaxis= dict(title= 'Dew Point', showgrid= True),
                yaxis2= dict(title= 'Relative Humidity',
                            overlaying= 'y',
                            side= 'right',
                            showgrid= False),
                legend= dict(x= 1.0,
                            xanchor= 'left',
                            y= 1.1),
                hovermode= 'x unified'
            )
            st.plotly_chart(fig1)

            st.write("### Graph 2: Dew Point and Snowfall")
            plot_type= st.selectbox('Select plot type:', ['line', 'scatter'], key= f'dps_{primary_columns}_{data_type}')
            data[['Dew Point (°C)', 'Snowfall (mm)']] = data[['Dew Point (°C)', 'Snowfall (mm)']].interpolate()

            if plot_type == 'line':
                fig2 = go.Figure()
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Dew Point (°C)'],
                    name= 'Dew Point (°C)',
                    mode= 'lines',
                    line= dict(color= 'blue', width= 2)
                ))
                fig2.add_trace(go.Line(
                    x= data.index,
                    y= data['Snowfall (mm)'],
                    name= 'Snowfall (mm)',
                    mode= 'lines',
                    line= dict(color= 'red', width= 2),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers+lines')
            elif plot_type == 'scatter':
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Dew Point (°C)'],
                    name= 'Dew Point (°C)',
                    mode= 'markers',
                    marker= dict(color= 'blue', size= 8)
                ))
                fig2.add_trace(go.Scatter(
                    x= data.index,
                    y= data['Snowfall (mm)'],
                    name= 'Snowfall (mm)',
                    mode= 'markers',
                    marker= dict(color= 'red', size= 8),
                    yaxis= 'y2'
                ))
                fig2.update_traces(mode= 'markers')
            fig2.update_layout(
                template= 'plotly_dark',
                title= f'Dew Point and Snowfall in {city}: {start_date.date()} to {end_date.date()}',
                xaxis= dict(title= 'Date'),
                yaxis= dict(title= 'Dew Point'),
                yaxis2= dict(title= 'Snowfall',
                            overlaying= 'y',
                            side= 'right',
                            showgrid= False),
                legend= dict(x= 1.0,
                            xanchor= 'left',
                            y= 1.1),
                hovermode= 'x unified'
            )
            st.plotly_chart(fig2)

# Function to fetch user's IP address and location
def fetch_user_location():
    # st.write("Fetching your IP address...")
    ip_request = requests.get("https://get.geojs.io/v1/ip.json")
    ip_data = ip_request.json()
    ip_address = ip_data.get("ip", "Unavailable")
    
    # st.success(f"Your IP Address: {ip_address}")

    # st.write("Fetching your location details...")
    geo_url = f"https://get.geojs.io/v1/ip/geo/{ip_address}.json"
    geo_request = requests.get(geo_url)
    geo_data = geo_request.json()

    if geo_data:
        city = geo_data.get('city', 'N/A')
        # st.subheader("Your Location Details 📍")
        # st.write(f"**City:** {city}")
        return city
    else:
        st.error("Could not fetch location details. Try again!")
        return None
    
def main():
    # initialize_histoy_file() # Ensure history file exists
    
    if 'map_click' not in st.session_state:
        st.session_state['map_click']= None

    if "view" not in st.session_state:
        st.session_state["view"] = "Weather Data"

    if "city_input" not in st.session_state:
        st.session_state["city_input"] = fetch_user_location()
        # Save the detected city into the search history
        save_history(st.session_state["city_input"])
        
    # Ensure weather updates when a new city is selected
    if st.session_state.get("weather_needs_update", False):
        st.session_state["weather_needs_update"] = False  # Reset flag AFTER updating weather data
        st.rerun()

    st.title("🌦 Weather Data Analysis")
    # Use a single radio button to switch between views
    st.session_state["view"] = st.radio(
        "Select View",
        ["Weather Data", "Weather News"],
        index=0
    )
    
    # Check if we are on the "news" page or the main page
    if st.session_state["view"] == "Weather Data":

        # Sidebar: Search for another city
        st.sidebar.title("🔍 Search Another City")
        search_city = st.sidebar.text_input("Enter city name:", placeholder="E.g., Tokyo, Berlin")
        
        if search_city:
            st.session_state["city_input"] = search_city
            st.session_state["weather_needs_update"] = True
            # Save search history immediately after search
            save_history(search_city)
            st.sidebar.success(f"✅ Showing weather for: {search_city}")
            # time.sleep(2)
            st.rerun()

        if "search_history" in st.session_state and st.session_state["search_history"]:
            selected_city = st.sidebar.selectbox(
                "Search History",
                [entry["City"] for entry in st.session_state["search_history"]],
                index=None,
                key="city_history"
            )

            if selected_city and selected_city != st.session_state["city_input"]:
                st.session_state["city_input"] = selected_city
                st.session_state["weather_needs_update"] = True  #  Mark update needed
                st.sidebar.success(f"✅ Showing weather for: {selected_city}")
                # time.sleep(2)
                st.rerun()
                
        # If user searches a city, update the main input field
        # if search_city:
        #     st.session_state["city_input"] = search_city


    #    # ✅ If user selects a city from history, update session state
    #     selected_city = st.sidebar.selectbox(
    #                     "Search History", 
    #                     [entry["City"] for entry in st.session_state["search_history"]],  # Extract city names from history
    #                     index=None, 
    #                     key="city_history"
    #                 )
    #     if selected_city and selected_city != st.session_state["city_input"]:
    #         st.session_state["city_input"] = selected_city
    #         st.session_state["weather_needs_update"] = True  # ✅ Mark update needed
    #         st.rerun()

        # Display the detected/searched city on the main page
        st.write("##### \n 📍 Your Location")
        city= st.text_input("Fetching your location details..", value=st.session_state["city_input"], disabled= True)

        unit= st.radio('Select Temperature Unit:', ['Celsius (°C)', 'Fahrenheit (°F)'])
        if city and unit:
            unit= unit[0]
            with st.spinner("Just Wait!!"): 
                time.sleep(3)
            
            # if st.sidebar.button("Show Current Weather"):
            st.write(f"Fetching weather data for: {city}")

            weather_data= current_weather(city, unit)

            # Fetch coordinates of the city
            lat, lon= fetch_coordinates(city)        

            if lat and lon and weather_data:
                past_weather_data = fetch_past_weather_data(city)
                forcast_data= fetch_forcast_data(city)

                display_weather_data(past_weather_data, city, unit, data_type= 'past')
                display_weather_data(forcast_data, city, unit, data_type= 'forecast')

                # Display map with weather data 
                st.markdown("### Location Map 🌍")
                display_map(city, lat, lon, weather_data)
                
                # Display notifications, cards, and other details
                hourly_data= fetch_weather_data(city, unit)
                display_notification(hourly_data)

                weather_card(hourly_data)
                
                plot_weather_graph(city, unit)
                        
            else:
                st.error("Could not fetch weather data. Please check the city name or try again later.")
        else:
            st.info('Please enter a city name.')
   
    elif st.session_state["view"] == "Weather News":
        st.title("🌦 Weather News")
        with st.spinner("Fetching weather news..."):
            articles = fetch_weather_news()
        display_all_news(articles)

    # Buttons for displaying and clearing history
    # if st.sidebar("Show History"):
    # display_history()

    # Place the Clear History button in the sidebar using an on_click callback.
    st.sidebar.button("Clear Search History", on_click=clear_history)
    
    # Save cookies once at the end of the run to avoid duplicate component keys.
    cookies.save()


if __name__ == "__main__":
    main()
