import mysql.connector
from mysql.connector import Error
from time import sleep

class MySQLWrapper:
    def __init__(self, host, user, password, database):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.connection = None

    def connect(self):
        """Establish a connection to the MySQL database."""
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                autocommit=True,  # Enable autocommit
                buffered=False,   # Disable result buffering
                pool_reset_session=True  # Reset session variables
            )
            if self.connection.is_connected():
                print("Connected to MySQL database")
        except Error as e:
            print(f"Error: {e}")

    def ensure_connection(self):
        """Check if the connection is still active, reconnect if necessary."""
        try:
            if self.connection and self.connection.is_connected():
                # Ping the server to verify connection
                self.connection.ping(reconnect=True, attempts=3, delay=5)
            else:
                print("Reconnecting to the database...")
                self.connect()
        except Error:
            print("Reconnecting to the database...")
            self.connect()

    def execute_query(self, query, params=None):
        """Execute a single query (INSERT, UPDATE, DELETE)."""
        try:
            self.ensure_connection()
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                self.connection.commit()
        except Error as e:
            print(f"Error executing query: {e}")
            self.handle_connection_error()
            self.execute_query(query, params)

    def fetch_all(self, query, params=None, dictionary=False):
        """Fetch all results for a SELECT query."""
        try:
            self.ensure_connection()
            # Close any existing cursor
            if hasattr(self, '_cursor') and self._cursor:
                self._cursor.close()
            
            # Force the connection to reconnect
            self.connection.cmd_reset_connection()
            
            with self.connection.cursor(dictionary=dictionary, buffered=False) as cursor:
                cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")  # Allows reading uncommitted changes
                cursor.execute(query, params)
                result = cursor.fetchall()
                self.connection.commit()  # Commit to ensure fresh data next time
                return result
        except Error as e:
            print(f"Error fetching data: {e}")
            self.handle_connection_error()
            return self.fetch_all(query, params)  # Retry once after reconnection
        
    def fetch_one(self, query, params=None):
        """Fetch a single result for a SELECT query."""
        try:
            self.ensure_connection()
            # Force the connection to reconnect
            self.connection.cmd_reset_connection()
            
            with self.connection.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
                cursor.execute(query, params)
                result = cursor.fetchone()
                self.connection.commit()
                return result
        except Error as e:
            print(f"Error fetching data: {e}")
            self.handle_connection_error()
            return self.fetch_one(query, params)  # Retry once after reconnection

    def close(self):
        """Close the MySQL connection."""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("MySQL connection is closed")

    def handle_connection_error(self):
        """Handles MySQL connection errors by attempting a reconnection."""
        if not self.connection or not self.connection.is_connected():
            self.connect()
            if self.connection.is_connected():
                print("Reconnected to MySQL database")
            else:
                print("Failed to reconnect. Retrying in 5 seconds...")
                sleep(5)
                self.handle_connection_error()
