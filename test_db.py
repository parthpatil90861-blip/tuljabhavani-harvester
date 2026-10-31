from db import get_db_connection

try:
    connection = get_db_connection()

    if connection.is_connected():
        print("MySQL Connected Successfully!")

        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")

        print("\nAvailable Tables:")

        for table in cursor.fetchall():
            print(table[0])

        cursor.close()
        connection.close()

except Exception as error:
    print("Database Connection Failed!")
    print(error)
