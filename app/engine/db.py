import mysql.connector
from mysql.connector import Error, pooling
import time

class MySQLWrapper:
    def __init__(self, host, user, password, database, pool_size=5, max_pool_size=10):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self.max_pool_size = max_pool_size
        self.connection_pool = None
        self.connection = None
        self._retry_delay = 1  # Initial retry delay in seconds (for exponential backoff)

    def create_pool(self):
        """Create a connection pool to avoid excessive connections."""
        try:
            self.connection_pool = pooling.MySQLConnectionPool(
                pool_name="mypool",
                pool_size=self.pool_size,
                pool_reset_session=True,
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            print("MySQL connection pool created.")
        except Error as e:
            print(f"Error creating connection pool: {e}")
            self.connection_pool = None

    def get_connection(self):
        """Get a connection from the pool or reconnect if necessary."""
        if not self.connection_pool:
            self.create_pool()
        
        try:
            if self.connection and self.connection.is_connected():
                return self.connection
            else:
                self.connection = self.connection_pool.get_connection()
                return self.connection
        except Error as e:
            print(f"Error getting connection: {e}")
            return None

    def ensure_connection(self):
        """Ensure that the connection is valid. If not, reconnect."""
        connection = self.get_connection()
        if connection is None or not connection.is_connected():
            print("Connection is invalid or not connected. Reconnecting...")
            self.handle_connection_error()

    def execute_query(self, query, params=None):
        """Execute a single query (INSERT, UPDATE, DELETE)."""
        try:
            self.ensure_connection()
            connection = self.get_connection()
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                connection.commit()
        except Error as e:
            print(f"Error executing query: {e}")
            self.handle_connection_error()
            self.execute_query(query, params)

    def fetch_all(self, query, params=None, dictionary=False):
        """Fetch all results for a SELECT query."""
        try:
            self.ensure_connection()
            connection = self.get_connection()
            with connection.cursor(dictionary=dictionary, buffered=False) as cursor:
                cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
                cursor.execute(query, params)
                result = cursor.fetchall()
                connection.commit()  # Commit to ensure fresh data next time
                return result
        except Error as e:
            print(f"Error fetching data: {e}")
            self.handle_connection_error()
            return self.fetch_all(query, params)  # Retry once after reconnection

    def fetch_one(self, query, params=None):
        """Fetch a single result for a SELECT query."""
        try:
            self.ensure_connection()
            connection = self.get_connection()
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
                cursor.execute(query, params)
                result = cursor.fetchone()
                connection.commit()
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
        """Handles MySQL connection errors by attempting a reconnection with exponential backoff."""
        # Retry with exponential backoff to avoid overloading the server
        attempt = 0
        while attempt < 5:  # Limit the number of retry attempts
            attempt += 1
            print(f"Attempt {attempt}: Reconnecting...")
            time.sleep(self._retry_delay)
            self._retry_delay *= 2  # Exponential backoff (e.g., 1, 2, 4, 8, 16 seconds)

            # Attempt to get a new connection from the pool
            self.ensure_connection()

            # If the connection is successful, stop retrying
            if self.connection and self.connection.is_connected():
                print("Reconnected to MySQL database")
                return

        # If we reach here, all attempts have failed
        print("Failed to reconnect after several attempts. Please check the database.")
