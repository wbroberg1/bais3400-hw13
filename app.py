from flask import Flask, request, render_template, redirect, url_for
from flask_paginate import Pagination, get_page_args
import pymysql
import math
import os
import logging
import platform
from dotenv import load_dotenv
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

# 11/23/2023 MWC
## TODO: format pagination on movies.html
## TODO: add a footer

# load environment variables
load_dotenv()


# create logger
logging.basicConfig(
    level=logging.INFO,
    filename="log_file.log",
    filemode="a",  # append to the log file
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logging.info("Loading variables from Azure Key Vault")
AZURE_KEY_VAULT_URL = os.environ["AZURE_KEY_VAULT_URL"]
print(AZURE_KEY_VAULT_URL)

credential = DefaultAzureCredential()
client = SecretClient(vault_url=AZURE_KEY_VAULT_URL, credential=credential)

_dbhostname = client.get_secret("HW13-DBHOSTNAME")
_dbusername = client.get_secret("HW13-DBUSERNAME")
_dbpassword = client.get_secret("HW13-DBPASSWORD")
_dbname = client.get_secret("HW13-DBNAME")
_secret = client.get_secret("HW13-SECRET-KEY")

############## database class ######################


class DB:
    def __init__(self):
        self.host = _dbhostname.value
        self.username = _dbusername.value
        self.password = _dbpassword.value
        self.dbname = _dbname.value
        self.ssl = {"ca": "./DigiCertGlobalRootCA.crt.pem"}
        self.conn = None

    def __connect__(self):
        """Connect to MySQL database."""
        try:
            if self.conn is None:
                self.conn = pymysql.connect(
                    host=self.host,
                    user=self.username,
                    password=self.password,
                    db=self.dbname,
                    ssl=self.ssl,
                    cursorclass=pymysql.cursors.DictCursor,
                )

                self.cur = self.conn.cursor()
        except pymysql.Error as e:
            logging.error(f"Error connecting to the database: {e}")
            raise
        finally:
            logging.info("Successfully connected to the database")

    def __disconnect__(self):
        """Disconnect from MySQL database."""
        if self.conn is not None:
            self.cur.close()
            self.conn.close()
            logging.info("Disconnected from the database")

    def fetch_all(self, query, param_dict=None):
        try:
            self.__connect__()
            logging.info(query)
            # get the total number of movies in the database
            self.cur.execute("SELECT * FROM movies")
            count = self.cur.rowcount

            # get the movies for the current page
            self.cur.execute(query, param_dict)
            result = self.cur.fetchall()

            self.__disconnect__()

            logging.info("Retrieved data for movies from the database")
            return count, result
        except pymysql.Error as e:
            logging.error(f"Error retrieving movie data: {e}")
            raise

    def fetch_search(self, query, param_dict=None):
        try:
            self.__connect__()
            logging.info(query)
            # get the total number of movies in the database
            self.cur.execute(
                "SELECT * FROM movies WHERE title LIKE %(search)s OR releaseYear LIKE %(search)s",
                param_dict,
            )
            count = self.cur.rowcount

            # get the movies for the current page
            self.cur.execute(query, param_dict)
            result = self.cur.fetchall()
            self.__disconnect__()
            logging.info("Retrieved data for movies from the database")
            return count, result
        except pymysql.Error as e:
            logging.error(f"Error retrieving movie data: {e}")
            raise

    def fetch_one(self, query, movie_id):
        try:
            self.__connect__()
            self.cur.execute(query, (movie_id,))
            result = self.cur.fetchone()
            self.__disconnect__()
            if result:
                logging.info(f"Retrieved movie with ID {movie_id} from the database")
            else:
                logging.warning(f"No movie found with ID {movie_id}")
            return result
        except pymysql.Error as e:
            logging.error(f"Error retrieving movie with ID {movie_id}: {e}")
            raise


####################################################


logging.info("Starting Flask app")

app = Flask(__name__)
app.config["SECRET_KEY"] = _secret.value


######## Routes ########
@app.route("/", methods=["GET"])
def index():
    logging.info("Index page")
    return render_template("index.html")


@app.route("/movie/<movie_id>", methods=["GET", "POST"])
def movie_details(movie_id):
    db = DB()
    query = "SELECT * FROM movies WHERE movieId = %s"
    movie = db.fetch_one(query, movie_id)
    return render_template("movie-details.html", movie=movie)


@app.route("/movies", methods=["GET"])
def movies(page=1, per_page=10, offset=0):
    logging.info("All movies page")
    db = DB()
    page, per_page, offset = get_page_args(
        page_parameter="page", per_page_parameter="per_page"
    )

    query = "SELECT * FROM movies ORDER BY title ASC LIMIT %(limit)s OFFSET %(offset)s"
    param_dict = {"limit": per_page, "offset": offset}

    total_rows, results = db.fetch_all(query, param_dict)
    if results:
        logging.info("Search results found.")
        logging.info(f"Total movies: {total_rows}")
        total_pages = math.ceil(total_rows / per_page)
        logging.info(f"Total pages: {total_pages}")

        pagination = Pagination(
            page=page, per_page=per_page, total=total_rows, css_framework="bootstrap5"
        )
        return render_template(
            "movies.html",
            movies=results,
            page_heading=f"All movies",
            page=page,
            per_page=per_page,
            pagination=pagination,
            total=total_rows,
        )
    else:
        logging.info("Error getting all movies")
        return render_template("movies.html", no_match="Error getting results.")


@app.route("/search", methods=["GET"])
def search(page=1, per_page=10, offset=0):
    search_string = request.args.get(
        "search_string", ""
    )  # Retrieve search_value from query parameters
    logging.info(f"Search string: {search_string}")

    if search_string:
        db = DB()
        page, per_page, offset = get_page_args(
            page_parameter="page",
            per_page_parameter="per_page",
            offset_parameter="offset",
        )
        logging.info(f"Search string: {search_string}")
        query = "SELECT * FROM movies WHERE title LIKE %(search)s OR releaseYear LIKE %(search)s LIMIT %(limit)s OFFSET %(offset)s"
        param_dict = {
            "search": "%" + search_string + "%",
            "limit": per_page,
            "offset": offset,
        }
        total_rows, search_results = db.fetch_search(query, param_dict)
        if search_results:
            logging.info("Search results found.")
            logging.info(f"Total search results: {total_rows}")
            total_pages = math.ceil(total_rows / per_page)
            logging.info(f"Total pages: {total_pages}")

            pagination = Pagination(
                page=page,
                per_page=per_page,
                total=total_rows,
                css_framework="bootstrap5",
                search_string=search_string,
            )
            return render_template(
                "movies.html",
                movies=search_results,
                page_heading=f'"{search_string}" search results',
                page=page,
                per_page=per_page,
                pagination=pagination,
                total=total_rows,
            )
        else:
            logging.info("No matches found for search.")
            return render_template(
                "movies.html", no_match="No matches found for your search."
            )
    else:
        logging.info("No search string provided.")
        return redirect(url_for("index"))


@app.route("/diagnostics", methods=["GET"])
def diagnostics():
    # borrowed from https://github.com/balarsen/FlaskStatus
    # borrowed from https://github.com/practisec/pwnedhub/blob/master/pwnedhub/views/core.py

    platform_stats = {
        "architecture": platform.architecture(),
        "machine": platform.machine(),
        "node": platform.node(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python_branch": platform.python_branch(),
        "python_build": platform.python_build(),
        "python_compiler": platform.python_compiler(),
        "python_implementation": platform.python_implementation(),
        "python_revision": platform.python_revision(),
        "python_version": platform.python_version(),
        "python_version_tuple": platform.python_version_tuple(),
        "release": platform.release(),
        "system": platform.system(),
        "uname": platform.uname(),
        "version": platform.version(),
        "java_ver": platform.java_ver(),
        "win32_ver": platform.win32_ver(),
        "mac_ver": platform.mac_ver(),
        "libc_ver": platform.libc_ver(),
        "load_average": os.getloadavg(),
    }

    log_stats = []
    log_files = [
        #     "/tmp/gunicorn-pwnedapi.log",
        #     "/tmp/gunicorn-pwnedhub.log",
        #     "/tmp/gunicorn-pwnedspa.log",
        #     "/tmp/gunicorn-pwnedsso.log",
        #     "/var/log/nginx/access.log",
        "./log_file.log",
    ]
    for log_file in log_files:
        if os.path.exists(log_file):
            data = {
                "name": log_file,
                "size": os.path.getsize(log_file),
                "mtime": os.path.getmtime(log_file),
                "ctime": os.path.getctime(log_file),
                "tail": [],
            }
            with open(log_file) as fp:
                data["tail"] = "".join(fp.readlines()[-20:])
            log_stats.append(data)

    return render_template(
        "diagnostics.html", platform_stats=platform_stats, log_stats=log_stats
    )

    # return render_template("diagnostics.html", platform_stats=platform_stats)
