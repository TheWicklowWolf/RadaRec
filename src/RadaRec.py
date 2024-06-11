import json
import time
import logging
import os
import random
import threading
import urllib.parse
from flask import Flask, render_template
from flask_socketio import SocketIO
import requests
from thefuzz import fuzz
from unidecode import unidecode
import re
from iso639 import Lang


class DataHandler:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        self.radarec_logger = logging.getLogger()
        self.search_in_progress_flag = False
        self.new_found_movies_counter = 0
        self.clients_connected_counter = 0
        self.config_folder = "config"
        self.recommended_movies = []
        self.radarr_items = []
        self.cleaned_radarr_items = []
        self.stop_event = threading.Event()
        self.stop_event.set()
        if not os.path.exists(self.config_folder):
            os.makedirs(self.config_folder)
        self.load_environ_or_config_settings()
        if self.auto_start:
            try:
                auto_start_thread = threading.Timer(self.auto_start_delay, self.automated_startup)
                auto_start_thread.daemon = True
                auto_start_thread.start()

            except Exception as e:
                self.radarec_logger.error(f"Auto Start Error: {str(e)}")

    def load_environ_or_config_settings(self):
        # Defaults
        default_settings = {
            "radarr_address": "http://192.168.1.2:7878",
            "radarr_api_key": "",
            "root_folder_path": "/data/media/movies/",
            "tmdb_api_key": "",
            "fallback_to_top_result": False,
            "radarr_api_timeout": 120.0,
            "quality_profile_id": 1,
            "metadata_profile_id": 1,
            "search_for_movie": False,
            "dry_run_adding_to_radarr": False,
            "minimum_rating": 5.5,
            "minimum_votes": 50,
            "language_choice": "all",
            "auto_start": False,
            "auto_start_delay": 60,
        }

        # Load settings from environmental variables (which take precedence) over the configuration file.
        self.radarr_address = os.environ.get("radarr_address", "")
        self.radarr_api_key = os.environ.get("radarr_api_key", "")
        self.root_folder_path = os.environ.get("root_folder_path", "")
        self.tmdb_api_key = os.environ.get("tmdb_api_key", "")
        fallback_to_top_result = os.environ.get("fallback_to_top_result", "")
        self.fallback_to_top_result = fallback_to_top_result.lower() == "true" if fallback_to_top_result != "" else ""
        radarr_api_timeout = os.environ.get("radarr_api_timeout", "")
        self.radarr_api_timeout = float(radarr_api_timeout) if radarr_api_timeout else ""
        quality_profile_id = os.environ.get("quality_profile_id", "")
        self.quality_profile_id = int(quality_profile_id) if quality_profile_id else ""
        metadata_profile_id = os.environ.get("metadata_profile_id", "")
        self.metadata_profile_id = int(metadata_profile_id) if metadata_profile_id else ""
        search_for_movie = os.environ.get("search_for_movie", "")
        self.search_for_movie = search_for_movie.lower() == "true" if search_for_movie != "" else ""
        dry_run_adding_to_radarr = os.environ.get("dry_run_adding_to_radarr", "")
        self.dry_run_adding_to_radarr = dry_run_adding_to_radarr.lower() == "true" if dry_run_adding_to_radarr != "" else ""
        minimum_rating = os.environ.get("minimum_rating", "")
        self.minimum_rating = float(minimum_rating) if minimum_rating else ""
        minimum_votes = os.environ.get("minimum_votes", "")
        self.minimum_votes = int(minimum_votes) if minimum_votes else ""
        self.language_choice = os.environ.get("language_choice", "")
        auto_start = os.environ.get("auto_start", "")
        self.auto_start = auto_start.lower() == "true" if auto_start != "" else ""
        auto_start_delay = os.environ.get("auto_start_delay", "")
        self.auto_start_delay = float(auto_start_delay) if auto_start_delay else ""

        # Load variables from the configuration file if not set by environmental variables.
        try:
            self.settings_config_file = os.path.join(self.config_folder, "settings_config.json")
            if os.path.exists(self.settings_config_file):
                self.radarec_logger.info(f"Loading Config via file")
                with open(self.settings_config_file, "r") as json_file:
                    ret = json.load(json_file)
                    for key in ret:
                        if getattr(self, key) == "":
                            setattr(self, key, ret[key])
        except Exception as e:
            self.radarec_logger.error(f"Error Loading Config: {str(e)}")

        # Load defaults if not set by an environmental variable or configuration file.
        for key, value in default_settings.items():
            if getattr(self, key) == "":
                setattr(self, key, value)

        # Save config.
        self.save_config_to_file()

    def automated_startup(self):
        self.request_movies_from_radarr(checked=True)
        items = [x["name"] for x in self.radarr_items]
        self.start(items)

    def connection(self):
        if self.recommended_movies:
            if self.clients_connected_counter == 0:
                if len(self.recommended_movies) > 25:
                    self.recommended_movies = random.sample(self.recommended_movies, 25)
                else:
                    self.radarec_logger.info(f"Shuffling Movies")
                    random.shuffle(self.recommended_movies)
            socketio.emit("more_movies_loaded", self.recommended_movies)

        self.clients_connected_counter += 1

    def disconnection(self):
        self.clients_connected_counter = max(0, self.clients_connected_counter - 1)

    def start(self, data):
        try:
            socketio.emit("clear")
            self.new_found_movies_counter = 1
            self.movies_to_use_in_search = []
            self.recommended_movies = []

            for item in self.radarr_items:
                item_name = item["name"]
                if item_name in data:
                    item["checked"] = True
                    self.movies_to_use_in_search.append(item_name)
                else:
                    item["checked"] = False

            if self.movies_to_use_in_search:
                self.stop_event.clear()
            else:
                self.stop_event.set()
                raise Exception("No Radarr Movies Selected")

        except Exception as e:
            self.radarec_logger.error(f"Startup Error: {str(e)}")
            self.stop_event.set()
            ret = {"Status": "Error", "Code": str(e), "Data": self.radarr_items, "Running": not self.stop_event.is_set()}
            socketio.emit("radarr_sidebar_update", ret)

        else:
            thread = threading.Thread(target=data_handler.find_similar_movies, name="Start_Finding_Thread")
            thread.daemon = True
            thread.start()

    def request_movies_from_radarr(self, checked=False):
        try:
            self.radarec_logger.info(f"Getting Movies from Radarr")
            self.radarr_items = []
            endpoint = f"{self.radarr_address}/api/v3/movie"
            headers = {"X-Api-Key": self.radarr_api_key}
            response = requests.get(endpoint, headers=headers, timeout=self.radarr_api_timeout)

            if response.status_code == 200:
                self.full_radarr_movie_list = response.json()
                self.radarr_items = [{"name": re.sub(r" \(\d{4}\)", "", unidecode(movie["title"], replace_str=" ")), "checked": checked} for movie in self.full_radarr_movie_list]
                self.radarr_items.sort(key=lambda x: x["name"].lower())
                self.cleaned_radarr_items = [item["name"].lower() for item in self.radarr_items]
                status = "Success"
                data = self.radarr_items
            else:
                status = "Error"
                data = response.text

            ret = {"Status": status, "Code": response.status_code if status == "Error" else None, "Data": data, "Running": not self.stop_event.is_set()}

        except Exception as e:
            self.radarec_logger.error(f"Getting Movie Error: {str(e)}")
            ret = {"Status": "Error", "Code": 500, "Data": str(e), "Running": not self.stop_event.is_set()}

        finally:
            socketio.emit("radarr_sidebar_update", ret)

    def request_movie_id(self, movie_name, movie_year=None):
        url = f"https://api.themoviedb.org/3/search/movie"
        params = {"api_key": self.tmdb_api_key, "query": movie_name}
        response = requests.get(url, params=params)
        data = response.json()
        ret = None
        if data:
            for movie in data["results"]:
                if fuzz.ratio(movie_name, movie["original_title"]) > 90 and (movie["release_date"][:4] == movie_year or not movie_year):
                    ret = movie["id"]
                    break
        return ret

    def request_similar_movies(self, movie_id):
        url = f"https://api.themoviedb.org/3/movie/{movie_id}/recommendations"
        params = {"api_key": self.tmdb_api_key}
        response = requests.get(url, params=params)
        data = response.json()
        ret_list = []

        for movie in data["results"]:
            if movie.get("vote_average", 0) >= self.minimum_rating and movie.get("vote_count", 0) >= self.minimum_votes:
                if movie.get("original_language", "en") == self.language_choice or self.language_choice == "all":
                    ret_list.append(movie)

        return ret_list

    def map_genre_ids_to_names(self, genre_ids):
        genre_mapping = {
            28: "Action",
            12: "Adventure",
            16: "Animation",
            35: "Comedy",
            80: "Crime",
            99: "Documentary",
            18: "Drama",
            10751: "Family",
            14: "Fantasy",
            36: "History",
            27: "Horror",
            10402: "Music",
            9648: "Mystery",
            10749: "Romance",
            878: "Science Fiction",
            10770: "TV Movie",
            53: "Thriller",
            10752: "War",
            37: "Western",
        }
        return [genre_mapping.get(genre_id, "Unknown") for genre_id in genre_ids]

    def find_similar_movies(self):
        if self.stop_event.is_set() or self.search_in_progress_flag:
            return
        elif self.new_found_movies_counter > 0:
            try:
                self.radarec_logger.info(f"Searching for new movies")
                self.new_found_movies_counter = 0
                self.search_in_progress_flag = True
                random_movies = random.sample(self.movies_to_use_in_search, min(8, len(self.movies_to_use_in_search)))

                for movie_name in random_movies:
                    if self.stop_event.is_set():
                        break
                    movie_id = self.request_movie_id(movie_name)
                    if not movie_id:
                        continue
                    related_movies = self.request_similar_movies(movie_id)
                    for movie in related_movies:
                        if self.stop_event.is_set():
                            break
                        cleaned_movie = unidecode(movie["title"]).lower()
                        if cleaned_movie in self.cleaned_radarr_items:
                            continue
                        if any(movie["title"] == item["Name"] for item in self.recommended_movies):
                            continue
                        genres = ", ".join(self.map_genre_ids_to_names(movie.get("genre_ids", [])))
                        overview = movie.get("overview", "")
                        popularity = movie.get("popularity", "")
                        original_language_code = movie.get("original_language", "en")
                        original_language = Lang(original_language_code)
                        vote_count = movie.get("vote_count", 0)
                        vote_avg = movie.get("vote_average", 0)
                        img_link = movie.get("poster_path", "")
                        date_string = movie.get("release_date", "0000-01-01")
                        year = date_string.split("-")[0]
                        tmdb_id = movie.get("id", "")
                        if img_link:
                            img_url = f"https://image.tmdb.org/t/p/original/{img_link}"
                        else:
                            img_url = "https://via.placeholder.com/300x200"

                        exclusive_movie = {
                            "Name": movie["title"],
                            "Year": year if year else "0000",
                            "Genre": genres,
                            "Status": "",
                            "Img_Link": img_url,
                            "Votes": f"Votes: {vote_count}",
                            "Rating": f"Rating: {vote_avg}",
                            "Overview": overview,
                            "Language": original_language.name,
                            "Popularity": popularity,
                            "Base_Movie": movie_name,
                            "TMDB_ID": tmdb_id,
                        }
                        self.recommended_movies.append(exclusive_movie)
                        socketio.emit("more_movies_loaded", [exclusive_movie])
                        self.new_found_movies_counter += 1

                if self.new_found_movies_counter == 0:
                    self.radarec_logger.info("Search Exhausted - Try selecting more movies from existing Radarr library")
                    socketio.emit("new_toast_msg", {"title": "Search Exhausted", "message": "Try selecting more movies from existing Radarr library"})

            except Exception as e:
                self.radarec_logger.error(f"TheMovieDB Error: {str(e)}")

            finally:
                self.search_in_progress_flag = False

        elif self.new_found_movies_counter == 0:
            try:
                self.search_in_progress_flag = True
                self.radarec_logger.info("Search Exhausted - Try selecting more movies from existing Radarr library")
                socketio.emit("new_toast_msg", {"title": "Search Exhausted", "message": "Try selecting more movies from existing Radarr library"})
                time.sleep(2)

            except Exception as e:
                self.radarec_logger.error(f"Search Exhausted Error: {str(e)}")

            finally:
                self.search_in_progress_flag = False

    def add_movies(self, data):
        try:
            raw_movie_name, movie_year = data
            movie_name = urllib.parse.unquote(raw_movie_name)
            movie_folder = movie_name.replace("/", " ")
            tmdb_id = None
            for movie in self.recommended_movies:
                if movie["Name"] == movie_name and movie["Year"] == movie_year:
                    tmdb_id = movie["TMDB_ID"]
                    break
            else:
                tmdb_id = self.request_movie_id(movie_name, movie_year)

            if tmdb_id:
                radarr_url = f"{self.radarr_address}/api/v3/movie"
                headers = {"X-Api-Key": self.radarr_api_key}
                payload = {
                    "title": movie_name,
                    "qualityProfileId": self.quality_profile_id,
                    "metadataProfileId": self.metadata_profile_id,
                    "titleSlug": movie_name.lower().replace(" ", "-"),
                    "rootFolderPath": self.root_folder_path,
                    "tmdbId": tmdb_id,
                    "monitored": True,
                    "addOptions": {
                        "monitor": "movieOnly",
                        "searchForMovie": self.search_for_movie,
                    },
                }
                if self.dry_run_adding_to_radarr:
                    response = requests.Response()
                    response.status_code = 201
                else:
                    response = requests.post(radarr_url, headers=headers, json=payload)

                if response.status_code == 201:
                    self.radarec_logger.info(f"Movie: '{movie_name}' added successfully to Radarr.")
                    status = "Added"
                    self.radarr_items.append({"name": movie_name, "checked": False})
                    self.cleaned_radarr_items.append(unidecode(movie_name).lower())
                else:
                    self.radarec_logger.error(f"Failed to add movie '{movie_name}' to Radarr.")
                    error_data = json.loads(response.content)
                    error_message = error_data[0].get("errorMessage", "Unknown Error")
                    self.radarec_logger.error(error_message)
                    if "already exists in the database" in error_message:
                        status = "Already in Radarr"
                        self.radarec_logger.info(f"Movie '{movie_name}' is already in Radarr.")
                    elif "configured for an existing movie" in error_message:
                        status = "Already in Radarr"
                        self.radarec_logger.info(f"'{movie_folder}' folder already configured for an existing movie.")
                    elif "Invalid Path" in error_message:
                        status = "Invalid Path"
                        self.radarec_logger.info(f"Path: {os.path.join(self.root_folder_path, movie_folder, '')} not valid.")
                    elif "ID was not found" in error_message:
                        status = "Invalid Movie ID"
                        self.radarec_logger.info(f"ID: {tmdb_id} for '{movie_folder}' not correct")
                    else:
                        status = "Failed to Add"

            else:
                status = "Failed to Add"
                self.radarec_logger.info(f"No Matching Movie for: '{movie_name}' in The Movie Database.")
                socketio.emit("new_toast_msg", {"title": "Failed to add Movie", "message": f"No Matching Movie for: '{movie_name}' in The Movie Database."})

            for item in self.recommended_movies:
                if item["Name"] == movie_name:
                    item["Status"] = status
                    socketio.emit("refresh_movie", item)
                    break

        except Exception as e:
            self.radarec_logger.error(f"Adding Movie Error: {str(e)}")

    def load_settings(self):
        try:
            data = {
                "radarr_address": self.radarr_address,
                "radarr_api_key": self.radarr_api_key,
                "root_folder_path": self.root_folder_path,
                "tmdb_api_key": self.tmdb_api_key,
            }
            socketio.emit("settings_loaded", data)
        except Exception as e:
            self.radarec_logger.error(f"Failed to load settings: {str(e)}")

    def update_settings(self, data):
        try:
            self.radarr_address = data["radarr_address"]
            self.radarr_api_key = data["radarr_api_key"]
            self.root_folder_path = data["root_folder_path"]
            self.tmdb_api_key = data["tmdb_api_key"]
        except Exception as e:
            self.radarec_logger.error(f"Failed to update settings: {str(e)}")

    def save_config_to_file(self):
        try:
            with open(self.settings_config_file, "w") as json_file:
                json.dump(
                    {
                        "radarr_address": self.radarr_address,
                        "radarr_api_key": self.radarr_api_key,
                        "root_folder_path": self.root_folder_path,
                        "tmdb_api_key": self.tmdb_api_key,
                        "fallback_to_top_result": self.fallback_to_top_result,
                        "radarr_api_timeout": float(self.radarr_api_timeout),
                        "quality_profile_id": self.quality_profile_id,
                        "metadata_profile_id": self.metadata_profile_id,
                        "search_for_movie": self.search_for_movie,
                        "dry_run_adding_to_radarr": self.dry_run_adding_to_radarr,
                        "minimum_rating": self.minimum_rating,
                        "minimum_votes": self.minimum_votes,
                        "language_choice": self.language_choice,
                        "auto_start": self.auto_start,
                        "auto_start_delay": self.auto_start_delay,
                    },
                    json_file,
                    indent=4,
                )

        except Exception as e:
            self.radarec_logger.error(f"Error Saving Config: {str(e)}")


app = Flask(__name__)
app.secret_key = "secret_key"
socketio = SocketIO(app)
data_handler = DataHandler()


@app.route("/")
def home():
    return render_template("base.html")


@socketio.on("side_bar_opened")
def side_bar_opened():
    if data_handler.radarr_items:
        ret = {"Status": "Success", "Data": data_handler.radarr_items, "Running": not data_handler.stop_event.is_set()}
        socketio.emit("radarr_sidebar_update", ret)


@socketio.on("get_radarr_movies")
def get_radarr_movies():
    thread = threading.Thread(target=data_handler.request_movies_from_radarr, name="Radarr_Thread")
    thread.daemon = True
    thread.start()


@socketio.on("adder")
def add_movies(data):
    thread = threading.Thread(target=data_handler.add_movies, args=(data,), name="Add_Movies_Thread")
    thread.daemon = True
    thread.start()


@socketio.on("connect")
def connection():
    data_handler.connection()


@socketio.on("disconnect")
def disconnection():
    data_handler.disconnection()


@socketio.on("load_settings")
def load_settings():
    data_handler.load_settings()


@socketio.on("update_settings")
def update_settings(data):
    data_handler.update_settings(data)
    data_handler.save_config_to_file()


@socketio.on("start_req")
def starter(data):
    data_handler.start(data)


@socketio.on("stop_req")
def stopper():
    data_handler.stop_event.set()


@socketio.on("load_more_movies")
def load_more_movies():
    thread = threading.Thread(target=data_handler.find_similar_movies, name="Find_Similar")
    thread.daemon = True
    thread.start()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
