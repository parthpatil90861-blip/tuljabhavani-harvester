from flask import (
    
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
import mysql.connector
from mysql.connector import Error
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

app = Flask(__name__)
app.secret_key = "tuljabhavani-harvester-secret-key"

# =========================================================
# DATABASE CONNECTION
# =========================================================
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "7272",
    "database": "tuljabhavani_db",
}


def get_db_connection():
    """Create and return a MySQL connection."""
    return mysql.connector.connect(**DB_CONFIG)


def ensure_harvesting_table():
    """
    Create harvesting_records if it does not exist.
    This does not delete or overwrite existing records.
    """
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS harvesting_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                customer_name VARCHAR(150) NOT NULL,
                crop VARCHAR(100) NOT NULL,
                village VARCHAR(150) NOT NULL,
                acre DECIMAL(10,2) NOT NULL DEFAULT 0,
                land_unit VARCHAR(20) NOT NULL DEFAULT 'acre',
                guntha DECIMAL(10,2) NOT NULL DEFAULT 0,
                goni_quantity DECIMAL(10,2) NOT NULL DEFAULT 0,
                goni_rate DECIMAL(12,2) NULL DEFAULT NULL,
                goni_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
                quantity_unit VARCHAR(20) NOT NULL DEFAULT 'acre',
                quantity DECIMAL(10,2) NOT NULL DEFAULT 0,
                date DATE NOT NULL,
                rate_per_acre DECIMAL(10,2) NOT NULL DEFAULT 0,
                rate_per_unit DECIMAL(12,2) NOT NULL DEFAULT 0,
                total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
                payment_received DECIMAL(12,2) NOT NULL DEFAULT 0,
                payment_type VARCHAR(50) DEFAULT 'Cash',
                due_date DATE NULL DEFAULT NULL,
                remarks TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()
    except Error as error:
        print("Could not verify/create harvesting_records table:", error)
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def migrate_harvesting_table():
    """Add new billing columns to an existing table without deleting records."""
    connection = None
    cursor = None
    additions = {
        "land_unit": "ALTER TABLE harvesting_records ADD COLUMN land_unit VARCHAR(20) NOT NULL DEFAULT 'acre'",
        "guntha": "ALTER TABLE harvesting_records ADD COLUMN guntha DECIMAL(10,2) NOT NULL DEFAULT 0",
        "goni_quantity": "ALTER TABLE harvesting_records ADD COLUMN goni_quantity DECIMAL(10,2) NOT NULL DEFAULT 0",
        "goni_rate": "ALTER TABLE harvesting_records ADD COLUMN goni_rate DECIMAL(12,2) NULL DEFAULT NULL",
        "goni_amount": "ALTER TABLE harvesting_records ADD COLUMN goni_amount DECIMAL(12,2) NOT NULL DEFAULT 0",
        "quantity_unit": "ALTER TABLE harvesting_records ADD COLUMN quantity_unit VARCHAR(20) NOT NULL DEFAULT 'acre'",
        "quantity": "ALTER TABLE harvesting_records ADD COLUMN quantity DECIMAL(10,2) NOT NULL DEFAULT 0",
        "rate_per_unit": "ALTER TABLE harvesting_records ADD COLUMN rate_per_unit DECIMAL(12,2) NOT NULL DEFAULT 0",
        "due_date": "ALTER TABLE harvesting_records ADD COLUMN due_date DATE NULL DEFAULT NULL",
    }
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SHOW COLUMNS FROM harvesting_records")
        columns = {row[0] for row in cursor.fetchall()}
        for name, sql in additions.items():
            if name not in columns:
                cursor.execute(sql)
        connection.commit()
    except Error as error:
        print("Harvesting table migration error:", error)
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def get_decimal(value, field_name, allow_zero=True):
    """Validate a numeric form field and return Decimal."""
    try:
        number = Decimal(str(value or "0").strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a valid number.")
    if not number.is_finite():
        raise ValueError(f"{field_name} must be a valid number.")
    if number < 0 or (not allow_zero and number == 0):
        raise ValueError(f"{field_name} cannot be negative or zero.")
    return number.quantize(Decimal("0.01"))


def get_customer_list():
    """Return customer names and villages for the harvesting form."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT customer_id, customer_name, mobile, village
            FROM customers
            ORDER BY customer_name
            """
        )
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def get_village_options():
    """
    Include villages from BOTH customers and harvesting records.
    This means a newly saved customer village appears in the filter
    even before a harvesting record is entered for that village.
    """
    connection = None
    cursor = None
    villages = []
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT village FROM customers
            WHERE village IS NOT NULL AND TRIM(village) <> ''
            UNION
            SELECT village FROM harvesting_records
            WHERE village IS NOT NULL AND TRIM(village) <> ''
            ORDER BY village
            """
        )
        villages = [row[0] for row in cursor.fetchall()]
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return villages


# =========================================================
# LOGIN / DASHBOARD
# =========================================================
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # Demo login. Change these credentials if required.
        if username == "admin" and password == "admin123":
            session["username"] = username
            session["role"] = "admin"
            flash("Login successful. Welcome to Tuljabhavani Harvester!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")


# =========================================================
# CUSTOMERS
# Expected existing table: customers
# customer_id, customer_name, mobile, village, address, date
# =========================================================
@app.route("/customers", methods=["GET", "POST"])
def customers():
    if "username" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    if request.method == "POST":
        customer_id = request.form.get("customer_id", "").strip()
        customer_name = request.form.get("customer_name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        village = request.form.get("village", "").strip()
        address = request.form.get("address", "").strip()
        customer_date = request.form.get("date", "").strip() or None

        if not customer_name:
            flash("Please enter customer name.", "danger")
            return redirect(url_for("customers"))

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            if customer_id:
                cursor.execute(
                    """
                    UPDATE customers
                    SET customer_name=%s, mobile=%s, village=%s,
                        address=%s, date=%s
                    WHERE customer_id=%s
                    """,
                    (
                        customer_name,
                        mobile,
                        village,
                        address,
                        customer_date,
                        customer_id,
                    ),
                )
                flash("Customer updated successfully.", "success")
            else:
                cursor.execute(
                    """
                    INSERT INTO customers
                        (customer_name, mobile, village, address, date)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (customer_name, mobile, village, address, customer_date),
                )
                flash("Customer saved successfully.", "success")

            connection.commit()
        except Error as error:
            if connection:
                connection.rollback()
            print("Customer save error:", error)
            flash(
                "Customer save failed. Please check the customers table columns "
                "in MySQL. Details are printed in the terminal.",
                "danger",
            )
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

        return redirect(url_for("customers"))

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT customer_id, customer_name, mobile, village, address, date
            FROM customers
            ORDER BY customer_id DESC
            """
        )
        customer_list = cursor.fetchall()
        return render_template("customers.html", customers=customer_list)
    except Error as error:
        print("Customer list error:", error)
        flash("Could not load customers. Check the customers table.", "danger")
        return render_template("customers.html", customers=[])
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/delete-customer/<int:customer_id>", methods=["POST", "GET"])
def delete_customer(customer_id):
    if "username" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM customers WHERE customer_id=%s", (customer_id,)
        )
        connection.commit()
        flash("Customer deleted successfully.", "success")
    except Error as error:
        if connection:
            connection.rollback()
        print("Delete customer error:", error)
        flash(
            "Customer could not be deleted. It may be used in harvesting records.",
            "danger",
        )
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("customers"))


# =========================================================
# HARVESTING RECORDS - LIST / SEARCH / FILTER / EDIT
# =========================================================
@app.route("/harvesting-records", methods=["GET"])
def harvesting_records():
    if "username" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    search = request.args.get("search", "").strip()
    crop_filter = request.args.get("crop", "").strip()
    village_filter = request.args.get("village", "").strip()
    date_filter = request.args.get("date", "").strip()
    edit_id = request.args.get("edit", "").strip()

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Search across customer name, crop, village, remarks, and mobile.
        # LEFT JOIN allows mobile search while keeping existing records visible.
        query = """
            SELECT
                hr.id,
                hr.customer_name,
                hr.crop,
                hr.village,
                CASE WHEN hr.land_unit='split' THEN hr.acre WHEN hr.land_unit='guntha' THEN FLOOR(hr.acre) ELSE FLOOR(hr.acre) END AS display_acre,
                hr.land_unit,
                CASE WHEN hr.land_unit='split' THEN hr.guntha WHEN hr.land_unit='guntha' THEN MOD(hr.guntha,40) ELSE ROUND((hr.acre-FLOOR(hr.acre))*40) END AS display_guntha,
                hr.acre,
                hr.guntha,
                hr.goni_quantity,
                hr.goni_rate,
                hr.goni_amount,
                hr.quantity_unit,
                hr.quantity,
                hr.date,
                hr.rate_per_acre,
                hr.rate_per_unit,
                hr.total_amount,
                hr.payment_received,
                (hr.total_amount - hr.payment_received) AS pending_amount,
                hr.payment_type,
                hr.remarks,
                c.mobile AS customer_mobile
            FROM harvesting_records hr
            LEFT JOIN customers c
                ON c.customer_name = hr.customer_name
            WHERE 1=1
        """
        params = []

        if search:
            like_value = f"%{search}%"
            query += """
                AND (
                    hr.customer_name LIKE %s
                    OR hr.crop LIKE %s
                    OR hr.village LIKE %s
                    OR COALESCE(hr.remarks, '') LIKE %s
                    OR COALESCE(c.mobile, '') LIKE %s
                )
            """
            params.extend([like_value] * 5)

        if crop_filter:
            query += " AND hr.crop = %s"
            params.append(crop_filter)

        if village_filter:
            query += " AND hr.village = %s"
            params.append(village_filter)

        if date_filter:
            query += " AND hr.date = %s"
            params.append(date_filter)

        query += " ORDER BY hr.date DESC, hr.id DESC"
        cursor.execute(query, tuple(params))
        records = cursor.fetchall()

        cursor.execute(
            """
            SELECT DISTINCT crop
            FROM harvesting_records
            WHERE crop IS NOT NULL AND TRIM(crop) <> ''
            ORDER BY crop
            """
        )
        crop_options = [row["crop"] for row in cursor.fetchall()]

        # Always include the standard crop options even when there are no records.
        for standard_crop in ("Wheat", "Soybean", "Rice", "Other"):
            if standard_crop not in crop_options:
                crop_options.append(standard_crop)

        # Villages from customers and records, so new customer villages appear.
        cursor.execute(
            """
            SELECT village FROM customers
            WHERE village IS NOT NULL AND TRIM(village) <> ''
            UNION
            SELECT village FROM harvesting_records
            WHERE village IS NOT NULL AND TRIM(village) <> ''
            ORDER BY village
            """
        )
        village_options = [row["village"] for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT customer_id, customer_name, mobile, village
            FROM customers
            ORDER BY customer_name
            """
        )
        customers_list = cursor.fetchall()

        edit_record = None
        if edit_id:
            if edit_id.isdigit():
                cursor.execute(
                    "SELECT * FROM harvesting_records WHERE id=%s",
                    (int(edit_id),),
                )
                edit_record = cursor.fetchone()
                if edit_record:
                    if edit_record.get("land_unit") == "split":
                        pass
                    elif edit_record.get("land_unit") == "guntha":
                        legacy_guntha = Decimal(str(edit_record.get("guntha") or 0))
                        edit_record["acre"] = int(legacy_guntha // Decimal("40"))
                        edit_record["guntha"] = int(legacy_guntha % Decimal("40"))
                    else:
                        legacy_area = Decimal(str(edit_record.get("acre") or 0))
                        edit_record["acre"] = int(legacy_area // Decimal("1"))
                        edit_record["guntha"] = int(((legacy_area % Decimal("1")) * Decimal("40")).quantize(Decimal("1")))
                if not edit_record:
                    flash("Record for editing was not found.", "warning")
            else:
                flash("Invalid record ID.", "warning")

        return render_template(
            "harvesting_records.html",
            records=records,
            crop_options=crop_options,
            village_options=village_options,
            customers_list=customers_list,
            edit_record=edit_record,
            search=search,
            crop_filter=crop_filter,
            village_filter=village_filter,
            date_filter=date_filter,
        )

    except Error as error:
        print("Harvesting records load error:", error)
        flash(
            "Harvesting records could not load. Check the table columns and "
            "database connection. The exact error is printed in the terminal.",
            "danger",
        )
        return render_template(
            "harvesting_records.html",
            records=[],
            crop_options=["Wheat", "Soybean", "Rice", "Other"],
            village_options=[],
            customers_list=[],
            edit_record=None,
            search=search,
            crop_filter=crop_filter,
            village_filter=village_filter,
            date_filter=date_filter,
        )
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# =========================================================
# SAVE / UPDATE HARVESTING RECORD
# =========================================================
@app.route("/save-harvesting-record", methods=["POST"])
def save_harvesting_record():
    if "username" not in session:
        return redirect(url_for("login"))

    record_id = request.form.get("id", "").strip()
    customer_name = request.form.get("customer_name", "").strip()
    crop = request.form.get("crop", "").strip()
    village = request.form.get("village", "").strip()
    record_date = request.form.get("date", "").strip()
    payment_type = request.form.get("payment_type", "Cash").strip() or "Cash"
    remarks = request.form.get("remarks", "").strip()

    if not customer_name or not crop or not village or not record_date:
        flash("Please fill Customer, Crop, Village, and Date.", "danger")
        return redirect(url_for("harvesting_records"))

    try:
        datetime.strptime(record_date, "%Y-%m-%d")
        acre = get_decimal(request.form.get("acre"), "Acre")
        guntha_decimal = get_decimal(request.form.get("guntha"), "Guntha")
        goni_quantity = get_decimal(request.form.get("goni_quantity"), "Number of Goni")
        goni_rate = get_decimal(request.form.get("goni_rate"), "Rate per Goni")
        rate_per_acre = get_decimal(request.form.get("rate_per_acre"), "Rate per acre")
        payment_received = get_decimal(request.form.get("payment_received"), "Payment received")
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("harvesting_records"))

    if acre != acre.to_integral_value():
        flash("Acre must be a whole number. Enter remaining land in Guntha.", "danger")
        return redirect(url_for("harvesting_records"))
    if guntha_decimal != guntha_decimal.to_integral_value() or guntha_decimal < 0 or guntha_decimal > 39:
        flash("Guntha must be a whole number from 0 to 39.", "danger")
        return redirect(url_for("harvesting_records"))
    if goni_quantity != goni_quantity.to_integral_value():
        flash("Number of Goni must be a whole number.", "danger")
        return redirect(url_for("harvesting_records"))
    if goni_quantity > 0 and goni_rate <= 0:
        flash("Enter the rate per goni when goni quantity is greater than zero.", "danger")
        return redirect(url_for("harvesting_records"))
    if acre == 0 and guntha_decimal == 0:
        flash("Enter an area greater than zero in Acre or Guntha.", "danger")
        return redirect(url_for("harvesting_records"))

    guntha = int(guntha_decimal)
    total_area_acres = (acre + (Decimal(guntha) / Decimal("40"))).quantize(Decimal("0.0001"))
    area_amount = (total_area_acres * rate_per_acre).quantize(Decimal("0.01"))
    goni_amount = (goni_quantity * goni_rate).quantize(Decimal("0.01"))
    # Total bill combines acreage charges and goni charges; existing payment fields remain meaningful.
    total_amount = area_amount + goni_amount
    if payment_received > total_amount:
        flash("Paid amount cannot be greater than the total bill (area amount + goni amount).", "danger")
        return redirect(url_for("harvesting_records"))

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT village FROM customers WHERE customer_name=%s ORDER BY customer_id DESC LIMIT 1",
            (customer_name,),
        )
        customer = cursor.fetchone()
        if not customer:
            flash("Please select a customer saved on the Customers page.", "danger")
            return redirect(url_for("harvesting_records"))
        village = (customer[0] or village).strip()

        # Keep legacy columns populated so older parts of the app continue to work.
        values = (
            customer_name, crop, village, acre, "split", guntha,
            "acre", total_area_acres, record_date, rate_per_acre,
            rate_per_acre, total_amount, payment_received, payment_type, remarks,
            goni_quantity, goni_rate, goni_amount,
        )
        if record_id:
            if not record_id.isdigit():
                flash("Invalid harvesting record ID.", "danger")
                return redirect(url_for("harvesting_records"))
            cursor.execute("""
                UPDATE harvesting_records
                SET customer_name=%s, crop=%s, village=%s, acre=%s, land_unit=%s,
                    guntha=%s, quantity_unit=%s, quantity=%s, date=%s,
                    rate_per_acre=%s, rate_per_unit=%s, total_amount=%s,
                    payment_received=%s, payment_type=%s, remarks=%s,
                    goni_quantity=%s, goni_rate=%s, goni_amount=%s
                WHERE id=%s
            """, values + (int(record_id),))
            flash("Harvesting record updated successfully.", "success")
        else:
            cursor.execute("""
                INSERT INTO harvesting_records
                    (customer_name, crop, village, acre, land_unit, guntha,
                     quantity_unit, quantity, date, rate_per_acre, rate_per_unit,
                     total_amount, payment_received, payment_type, remarks,
                     goni_quantity, goni_rate, goni_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, values)
            flash("Harvesting record saved successfully.", "success")
        connection.commit()
    except Error as error:
        if connection:
            connection.rollback()
        print("Save harvesting record error:", error)
        flash("Could not save the harvesting record. Check the MySQL table structure; exact error is in the terminal.", "danger")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("harvesting_records"))


@app.route("/delete-harvesting-record/<int:record_id>", methods=["POST"])
def delete_harvesting_record(record_id):
    if "username" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM harvesting_records WHERE id=%s", (record_id,))
        connection.commit()
        flash("Harvesting record deleted successfully.", "success")
    except Error as error:
        if connection:
            connection.rollback()
        print("Delete harvesting record error:", error)
        flash("Could not delete the harvesting record.", "danger")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("harvesting_records"))


# =========================================================
# SETTINGS PAGE (existing navigation target)
# =========================================================
@app.route("/settings")
def settings():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("settings.html")


# =========================================================
# PAYMENT TRACKER
# Uses existing harvesting_records; no duplicate bills are created.
# =========================================================
def _payment_status(row):
    total = Decimal(str(row.get("total_amount") or 0))
    paid = Decimal(str(row.get("payment_received") or 0))
    balance = max(Decimal("0.00"), total - paid)
    due = row.get("due_date")
    today = date.today()
    if balance <= 0 and total > 0:
        return "completed"
    if balance > 0 and due and due < today:
        return "overdue"
    if paid > 0 and balance > 0:
        return "partial"
    return "pending"

# =========================================================
# PAYMENT TRACKER HELPERS
# =========================================================

def _payment_status(row):
    """
    Return payment status in lowercase.
    Statuses: pending, partial, completed, overdue.
    """

    total = Decimal(str(row.get("total_amount") or 0))
    paid = Decimal(str(row.get("payment_received") or 0))

    balance = max(
        Decimal("0.00"),
        total - paid
    )

    due = row.get("due_date")
    today = date.today()

    if balance <= 0:
        return "completed"

    if due and due < today:
        return "overdue"

    if paid > 0:
        return "partial"

    return "pending"


def _get_payment_records(cursor):
    """
    Fetch all harvesting records for Payment Tracker.
    Keep existing MySQL records unchanged.
    """

    cursor.execute("""
        SELECT
            hr.id,
            hr.customer_name,
            hr.date,
            hr.total_amount,
            hr.payment_received,
            hr.due_date,
            hr.village,

            COALESCE(c.mobile, '') AS mobile,

            GREATEST(
                COALESCE(hr.total_amount, 0)
                - COALESCE(hr.payment_received, 0),
                0
            ) AS balance_due

        FROM harvesting_records AS hr

        LEFT JOIN customers AS c
            ON c.customer_name = hr.customer_name

        ORDER BY hr.date DESC, hr.id DESC
    """)

    rows = cursor.fetchall()

    records = []

    for row in rows:

        record = dict(row)

        # Use float consistently for template display and summaries.
        total = float(record.get("total_amount") or 0)
        paid = float(record.get("payment_received") or 0)

        balance = max(total - paid, 0.0)

        record["total_amount"] = total
        record["payment_received"] = paid
        record["balance_due"] = balance

        # Keep the original lowercase status for filtering.
        status = _payment_status(record)

        record["payment_status"] = status

        # Keep a readable label for the user interface.
        record["display_status"] = status.title()

        records.append(record)

    return records

    rows = cursor.fetchall()
    for row in rows:
        row["total_amount"] = Decimal(str(row.get("total_amount") or 0))
        row["payment_received"] = Decimal(str(row.get("payment_received") or 0))
        row["balance_due"] = max(Decimal("0.00"), row["total_amount"] - row["payment_received"])
        row["display_status"] = _payment_status(row)
        row["payment_status"] = row["display_status"].upper()
    return rows


@app.route("/payment-tracker", methods=["GET"])
def payment_tracker():
    if "username" not in session:
        return redirect(url_for("login"))

    status_filter = request.args.get("status", "pending").lower()
    allowed_statuses = {"pending", "completed", "partial", "overdue", "all"}
    if status_filter not in allowed_statuses:
        status_filter = "pending"
    search = request.args.get("search", "").strip().lower()
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        all_records = _get_payment_records(cursor)

        # Summary cards always show totals across all bills, not just the selected tab.
        summary = {
            "pending": sum((r["balance_due"] for r in all_records if r["display_status"] == "pending"), Decimal("0.00")),
            "completed": sum((r["total_amount"] for r in all_records if r["display_status"] == "completed"), Decimal("0.00")),
            "partial": sum((r["balance_due"] for r in all_records if r["display_status"] == "partial"), Decimal("0.00")),
        }

        records = all_records
        if search:
            records = [r for r in records if search in str(r.get("customer_name") or "").lower()
                       or search in str(r.get("mobile") or "").lower()
                       or search in (r["date"].strftime("%d-%m-%Y") if r.get("date") else "").lower()]
        if status_filter != "all":
            records = [r for r in records if r["display_status"] == status_filter]

        return render_template("payment_tracker.html", records=records,
                               all_records=all_records, summary=summary,
                               status_filter=status_filter, search=search)
    except Error as error:
        print("Payment Tracker load error:", error)
        flash("Payment Tracker could not load. Check MySQL and the due_date migration; details are in the terminal.", "danger")
        empty_summary = {"pending": Decimal("0.00"), "completed": Decimal("0.00"), "partial": Decimal("0.00")}
        return render_template("payment_tracker.html", records=[], all_records=[], summary=empty_summary,
                               status_filter=status_filter, search=search)
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/payment-tracker/update/<int:record_id>", methods=["POST"])
def update_payment_tracker(record_id):
    if "username" not in session:
        return redirect(url_for("login"))
    try:
        paid = get_decimal(request.form.get("payment_received"), "Paid amount")
        due_text = request.form.get("due_date", "").strip()
        due_date = None
        if due_text:
            due_date = datetime.strptime(due_text, "%Y-%m-%d").date()
    except (ValueError, TypeError) as error:
        flash(str(error) or "Please enter a valid due date.", "danger")
        return redirect(url_for("payment_tracker"))

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, total_amount FROM harvesting_records WHERE id=%s", (record_id,))
        bill = cursor.fetchone()
        if not bill:
            flash("The selected harvesting bill was not found.", "danger")
            return redirect(url_for("payment_tracker"))
        total = Decimal(str(bill.get("total_amount") or 0))
        if paid > total:
            flash("Paid amount cannot be greater than the total bill amount.", "danger")
            return redirect(url_for("payment_tracker"))
        cursor.execute("""
            UPDATE harvesting_records
            SET payment_received=%s, due_date=%s
            WHERE id=%s
        """, (paid, due_date, record_id))
        connection.commit()
        flash("Payment information updated successfully.", "success")
    except Error as error:
        if connection:
            connection.rollback()
        print("Payment update error:", error)
        flash("Payment could not be updated. Check the terminal for details.", "danger")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("payment_tracker"))


@app.route("/payment-tracker/clear/<int:record_id>", methods=["POST"])
def clear_payment_tracker(record_id):
    """Clear payment details only; preserve the harvesting bill and customer."""
    if "username" not in session:
        return redirect(url_for("login"))
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE harvesting_records SET payment_received=0, due_date=NULL WHERE id=%s", (record_id,))
        if cursor.rowcount == 0:
            flash("No matching harvesting bill was found.", "warning")
        else:
            connection.commit()
            flash("Payment amount cleared. The harvesting bill and customer were preserved.", "success")
    except Error as error:
        if connection:
            connection.rollback()
        print("Clear payment error:", error)
        flash("Payment could not be cleared. Check the terminal for details.", "danger")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return redirect(url_for("payment_tracker"))


@app.route("/payment-tracker/receipt/<int:record_id>", methods=["GET"])
def payment_receipt(record_id):
    if "username" not in session:
        return redirect(url_for("login"))
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT hr.id, hr.customer_name, hr.date, hr.total_amount,
                   hr.payment_received, hr.due_date,
                   GREATEST(COALESCE(hr.total_amount,0)-COALESCE(hr.payment_received,0),0) AS balance_due,
                   COALESCE(c.mobile, '') AS mobile
            FROM harvesting_records hr
            LEFT JOIN customers c ON c.customer_name=hr.customer_name
            WHERE hr.id=%s
        """, (record_id,))
        row = cursor.fetchone()
        if not row:
            flash("Payment receipt record was not found.", "warning")
            return redirect(url_for("payment_tracker"))
        row["total_amount"] = Decimal(str(row.get("total_amount") or 0))
        row["payment_received"] = Decimal(str(row.get("payment_received") or 0))
        row["balance_due"] = max(Decimal("0.00"), row["total_amount"] - row["payment_received"])
        row["payment_status"] = _payment_status(row).upper()
        return render_template("payment_receipt.html", row=row)
    except Error as error:
        print("Payment receipt error:", error)
        flash("Could not create receipt. Check the terminal for details.", "danger")
        return redirect(url_for("payment_tracker"))
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# =========================================================
# REPORTS - daily / weekly / monthly / yearly summaries
# =========================================================
@app.route("/reports")
def reports():
    if "username" not in session:
        return redirect(url_for("login"))

    period = request.args.get("period", "monthly").lower()
    if period not in ("daily", "weekly", "monthly", "yearly", "all"):
        period = "monthly"
    selected_date = request.args.get("date", date.today().isoformat())
    try:
        base_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
    except ValueError:
        base_date = date.today()
        selected_date = base_date.isoformat()

    where = ""
    params = []
    if period == "daily":
        where = "WHERE date = %s"
        params = [base_date]
    elif period == "weekly":
        week_start = base_date.fromordinal(base_date.toordinal() - base_date.weekday())
        week_end = week_start.fromordinal(week_start.toordinal() + 7)
        where = "WHERE date >= %s AND date < %s"
        params = [week_start, week_end]
    elif period == "monthly":
        month_start = base_date.replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)
        where = "WHERE date >= %s AND date < %s"
        params = [month_start, month_end]
    elif period == "yearly":
        where = "WHERE date >= %s AND date < %s"
        params = [date(base_date.year, 1, 1), date(base_date.year + 1, 1, 1)]

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f"""
            SELECT COUNT(*) AS record_count,
                   COALESCE(SUM(CASE WHEN land_unit='split' THEN COALESCE(acre,0)+COALESCE(guntha,0)/40 WHEN land_unit='guntha' THEN COALESCE(guntha,0)/40 ELSE COALESCE(acre,0) END),0) AS total_acre,
                   COALESCE(SUM(CASE WHEN land_unit='split' THEN COALESCE(acre,0)*40+COALESCE(guntha,0) WHEN land_unit='guntha' THEN COALESCE(guntha,0) ELSE COALESCE(acre,0)*40 END),0) AS total_guntha,
                   COALESCE(SUM(COALESCE(goni_quantity,0)),0) AS total_goni,
                   COALESCE(SUM(COALESCE(goni_amount,0)),0) AS total_goni_amount,
                   COALESCE(SUM(COALESCE(total_amount,0)),0) AS total_amount,
                   COALESCE(SUM(COALESCE(payment_received,0)),0) AS total_paid,
                   COALESCE(SUM(COALESCE(total_amount,0)-COALESCE(payment_received,0)),0) AS total_pending
            FROM harvesting_records {where}
        """, tuple(params))
        totals = cursor.fetchone()
        cursor.execute(f"""
            SELECT id, customer_name, crop, village,
                   CASE WHEN land_unit='split' THEN acre WHEN land_unit='guntha' THEN FLOOR(guntha/40) ELSE FLOOR(acre) END AS display_acre,
                   CASE WHEN land_unit='split' THEN guntha WHEN land_unit='guntha' THEN MOD(guntha,40) ELSE ROUND((acre-FLOOR(acre))*40) END AS display_guntha,
                   acre, guntha, goni_quantity,
                   goni_rate, goni_amount, date, total_amount, payment_received,
                   (total_amount-payment_received) AS pending_amount
            FROM harvesting_records {where}
            ORDER BY date DESC, id DESC
        """, tuple(params))
        records = cursor.fetchall()
        cursor.execute(f"""
            SELECT date, COUNT(*) AS records,
                   COALESCE(SUM(CASE WHEN land_unit='split' THEN COALESCE(acre,0)+COALESCE(guntha,0)/40 WHEN land_unit='guntha' THEN COALESCE(guntha,0)/40 ELSE COALESCE(acre,0) END),0) AS total_acre,
                   COALESCE(SUM(COALESCE(goni_quantity,0)),0) AS total_goni,
                   COALESCE(SUM(COALESCE(goni_amount,0)),0) AS goni_amount,
                   COALESCE(SUM(COALESCE(total_amount,0)),0) AS amount
            FROM harvesting_records {where}
            GROUP BY date ORDER BY date DESC
        """, tuple(params))
        date_groups = cursor.fetchall()
        cursor.execute(f"""
            SELECT village, COUNT(*) AS records,
                   COALESCE(SUM(CASE WHEN land_unit='split' THEN COALESCE(acre,0)+COALESCE(guntha,0)/40 WHEN land_unit='guntha' THEN COALESCE(guntha,0)/40 ELSE COALESCE(acre,0) END),0) AS total_acre,
                   COALESCE(SUM(COALESCE(goni_quantity,0)),0) AS total_goni,
                   COALESCE(SUM(COALESCE(goni_amount,0)),0) AS goni_amount,
                   COALESCE(SUM(COALESCE(total_amount,0)),0) AS amount
            FROM harvesting_records {where}
            GROUP BY village ORDER BY village
        """, tuple(params))
        village_groups = cursor.fetchall()
        cursor.execute(f"""
            SELECT crop, COUNT(*) AS records,
                   COALESCE(SUM(CASE WHEN land_unit='split' THEN COALESCE(acre,0)+COALESCE(guntha,0)/40 WHEN land_unit='guntha' THEN COALESCE(guntha,0)/40 ELSE COALESCE(acre,0) END),0) AS total_acre,
                   COALESCE(SUM(COALESCE(goni_quantity,0)),0) AS total_goni,
                   COALESCE(SUM(COALESCE(goni_amount,0)),0) AS goni_amount,
                   COALESCE(SUM(COALESCE(total_amount,0)),0) AS amount
            FROM harvesting_records {where}
            GROUP BY crop ORDER BY crop
        """, tuple(params))
        crop_groups = cursor.fetchall()
        return render_template("reports.html", period=period, selected_date=selected_date,
            totals=totals, records=records, date_groups=date_groups,
            village_groups=village_groups, crop_groups=crop_groups)
    except Error as error:
        print("Reports load error:", error)
        flash("Could not load reports. See the terminal for the database error.", "danger")
        return render_template("reports.html", period=period, selected_date=selected_date,
            totals={}, records=[], date_groups=[], village_groups=[], crop_groups=[])
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# =========================================================
# LOGOUT
# =========================================================
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

from datetime import datetime
from decimal import Decimal, InvalidOperation

from models.maintenance_model import (
    add_maintenance,
    get_all_maintenance,
    get_maintenance_by_id,
    update_maintenance,
    delete_maintenance,
    get_maintenance_summary,
    get_upcoming_services
)

# CREATE BLUEPRINT
maintenance_bp = Blueprint(
    "maintenance",
    __name__
)

# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_connection():

    # Existing Flask application DB function वापरा.
    from app import get_db_connection

    return get_db_connection()


# ==========================================
# FORM VALIDATION
# ==========================================

def get_form_data():

    data = request.form.to_dict()

    required_date = data.get("maintenance_date", "").strip()

    if not required_date:
        raise ValueError("Maintenance date is required.")

    try:
        datetime.strptime(required_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Invalid maintenance date.")

    for field in ("parts_cost", "labour_charges", "other_charges"):
        try:
            amount = Decimal(data.get(field) or "0")
        except InvalidOperation:
            raise ValueError("Enter valid expense amounts.")

        if not amount.is_finite() or amount < 0:
            raise ValueError("Expense amounts cannot be negative.")

        data[field] = amount

    for field in ("parts_cost", "labour_charges", "other_charges"):
        if data[field] > Decimal("9999999999.99"):
            raise ValueError("Expense amount is too large.")

    for field in ("maintenance_date", "next_service_date"):
        value = data.get(field, "").strip()

        if value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Invalid service date.")

    if data.get("next_service_date"):
        if data["next_service_date"] < required_date:
            raise ValueError(
                "Next service date cannot be before maintenance date."
            )

    data["machine_name"] = data.get("machine_name", "").strip()
    data["maintenance_type"] = data.get("maintenance_type", "").strip()

    if not data["machine_name"] or not data["maintenance_type"]:
        raise ValueError("Machine name and maintenance type are required.")

    return data


# ==========================================
# MAINTENANCE HOME PAGE
# ==========================================

@maintenance_bp.route("/maintenance", methods=["GET"])
def maintenance_page():

    connection = get_connection()

    if not connection:
        flash("Database connection failed.", "danger")
        return redirect(url_for("dashboard"))

    try:
        records = get_all_maintenance(connection)
        summary = get_maintenance_summary(connection)
        upcoming = get_upcoming_services(connection)

        return render_template(
            "maintenance.html",
            records=records,
            summary=summary,
            upcoming=upcoming
        )

    except Exception as e:
        current_app.logger.exception("Maintenance page error")
        flash("Unable to load maintenance records.", "danger")
        return redirect(url_for("dashboard"))

    finally:
        connection.close()


# ==========================================
# ADD MAINTENANCE
# ==========================================

@maintenance_bp.route("/add-maintenance", methods=["POST"])
def add_maintenance_record():

    connection = get_connection()

    if not connection:
        flash("Database connection failed.", "danger")
        return redirect(url_for("maintenance.maintenance_page"))

    try:
        data = get_form_data()

        add_maintenance(connection, data)

        flash("Maintenance record added successfully!", "success")

    except ValueError as e:
        flash(str(e), "danger")

    except Exception:
        current_app.logger.exception("Add maintenance error")
        flash("Unable to save maintenance record.", "danger")

    finally:
        connection.close()

    return redirect(url_for("maintenance.maintenance_page"))


# ==========================================
# EDIT MAINTENANCE
# ==========================================

@maintenance_bp.route("/edit-maintenance/<int:record_id>", methods=["GET", "POST"])
def edit_maintenance_record(record_id):

    connection = get_connection()

    if not connection:
        flash("Database connection failed.", "danger")
        return redirect(url_for("maintenance.maintenance_page"))

    try:
        record = get_maintenance_by_id(connection, record_id)

        if not record:
            flash("Maintenance record not found.", "danger")
            return redirect(url_for("maintenance.maintenance_page"))

        if request.method == "POST":

            data = get_form_data()

            updated = update_maintenance(
                connection,
                record_id,
                data
            )

            if updated:
                flash("Maintenance updated successfully!", "success")
            else:
                flash("No changes were made.", "info")

            return redirect(url_for("maintenance.maintenance_page"))

        return render_template(
            "maintenance.html",
            records=get_all_maintenance(connection),
            summary=get_maintenance_summary(connection),
            upcoming=get_upcoming_services(connection),
            edit_record=record
        )

    except ValueError as e:
        flash(str(e), "danger")

    except Exception:
        current_app.logger.exception("Edit maintenance error")
        flash("Unable to update maintenance record.", "danger")

    finally:
        connection.close()

    return redirect(url_for("maintenance.maintenance_page"))


# ==========================================
# DELETE MAINTENANCE
# ==========================================

@maintenance_bp.route("/delete-maintenance/<int:record_id>", methods=["POST"])
def delete_maintenance_record(record_id):

    connection = get_connection()

    if not connection:
        flash("Database connection failed.", "danger")
        return redirect(url_for("maintenance.maintenance_page"))

    try:
        deleted = delete_maintenance(connection, record_id)

        if deleted:
            flash("Maintenance record deleted successfully!", "success")
        else:
            flash("Record not found.", "warning")

    except Exception:
        current_app.logger.exception("Delete maintenance error")
        flash("Unable to delete maintenance record.", "danger")

    finally:
        connection.close()

    return redirect(url_for("maintenance.maintenance_page"))


# =========================================================
# START APPLICATION
# =========================================================
if __name__ == "__main__":
    ensure_harvesting_table()
    migrate_harvesting_table()
    app.run(debug=True)
