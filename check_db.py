
import sqlite3

# Connect to your database file
conn = sqlite3.connect("zyra.db")
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:", tables)

# If User table exists, show its columns
cursor.execute("PRAGMA table_info(User);")
columns = cursor.fetchall()
print("User table columns:", columns)

conn.close()
