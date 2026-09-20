from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    session,
)

from datetime import timedelta, datetime
from zoneinfo import ZoneInfo

import sqlite3
from pathlib import Path
import os
import hmac
import hashlib
import secrets

import razorpay
from dotenv import load_dotenv
import qrcode


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

IST = ZoneInfo("Asia/Kolkata")

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
)

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is missing from .env"
    )


TICKET_PRICE = 2000

BASE_DIR = Path(__file__).resolve().parent

DATABASE = BASE_DIR / "farewell.db"

QR_FOLDER = BASE_DIR / "static" / "qr"

QR_FOLDER.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# TIMESTAMP HELPER
# ============================================================

def current_ist_time():

    return datetime.now(IST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# ============================================================
# ADMIN / HOST CONFIGURATION
# ============================================================

ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME"
)

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD"
)

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    raise RuntimeError(
        "ADMIN_USERNAME or ADMIN_PASSWORD is missing from .env"
    )


# ============================================================
# RAZORPAY
# ============================================================

RAZORPAY_KEY_ID = os.getenv(
    "RAZORPAY_KEY_ID"
)

RAZORPAY_KEY_SECRET = os.getenv(
    "RAZORPAY_KEY_SECRET"
)

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise RuntimeError(
        "Razorpay test credentials are missing from .env"
    )


razorpay_client = razorpay.Client(
    auth=(
        RAZORPAY_KEY_ID,
        RAZORPAY_KEY_SECRET
    )
)


# ============================================================
# DATABASE
# ============================================================

def get_db_connection():

    connection = sqlite3.connect(
        DATABASE
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():

    connection = get_db_connection()


    # ========================================================
    # REGISTRATIONS TABLE
    # ========================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS registrations (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            class_name TEXT NOT NULL,

            amount INTEGER NOT NULL,

            payment_status TEXT NOT NULL
                DEFAULT 'PENDING',

            ticket_status TEXT NOT NULL
                DEFAULT 'PENDING',

            razorpay_order_id TEXT,

            razorpay_payment_id TEXT,

            created_at TIMESTAMP
        )
    """)

    connection.commit()


    # ========================================================
    # COMPATIBILITY WITH OLDER DATABASE
    # ========================================================

    columns = connection.execute(
        "PRAGMA table_info(registrations)"
    ).fetchall()

    existing_columns = {
        column["name"]
        for column in columns
    }


    if "ticket_number" not in existing_columns:

        connection.execute("""
            ALTER TABLE registrations
            ADD COLUMN ticket_number TEXT
        """)


    if "ticket_token" not in existing_columns:

        connection.execute("""
            ALTER TABLE registrations
            ADD COLUMN ticket_token TEXT
        """)


    if "ticket_generated_at" not in existing_columns:

        connection.execute("""
            ALTER TABLE registrations
            ADD COLUMN ticket_generated_at TEXT
        """)


    if "checked_in_at" not in existing_columns:

        connection.execute("""
            ALTER TABLE registrations
            ADD COLUMN checked_in_at TEXT
        """)


    connection.commit()

    connection.close()


# ============================================================
# PUBLIC HOME
# ============================================================

@app.route("/")
def home():

    return render_template(
        "index.html",
        ticket_price=TICKET_PRICE
    )


# ============================================================
# REGISTER + CREATE RAZORPAY ORDER
# ============================================================

@app.route(
    "/register",
    methods=["POST"]
)
def register():

    # --------------------------------------------------------
    # GET FORM DATA
    # --------------------------------------------------------

    name = request.form.get(
        "name",
        ""
    ).strip()

    section = request.form.get(
        "section",
        ""
    ).strip().upper()


    # --------------------------------------------------------
    # VALIDATE NAME
    # --------------------------------------------------------

    if not name:

        return (
            "Full name is required.",
            400
        )


    if len(name) > 100:

        return (
            "Name is too long.",
            400
        )


    # --------------------------------------------------------
    # VALIDATE SECTION
    # --------------------------------------------------------

    if section not in {
        "A",
        "B",
        "C",
        "D"
    }:

        return (
            "Please select a valid section.",
            400
        )


    class_name = f"10-{section}"


    # --------------------------------------------------------
    # CREATE DATABASE CONNECTION
    # --------------------------------------------------------

    connection = get_db_connection()


    # --------------------------------------------------------
    # CREATE REGISTRATION
    # --------------------------------------------------------

    cursor = connection.execute(
        """
        INSERT INTO registrations
        (
            name,
            class_name,
            amount,
            payment_status,
            ticket_status,
            created_at
        )
        VALUES (?, ?, ?, 'PENDING', 'PENDING', ?)
        """,
        (
            name,
            class_name,
            TICKET_PRICE,
            current_ist_time()
        )
    )


    registration_id = cursor.lastrowid


    # --------------------------------------------------------
    # CREATE RAZORPAY ORDER
    # --------------------------------------------------------

    order_data = {

        "amount":
            TICKET_PRICE * 100,

        "currency":
            "INR",

        "receipt":
            f"obsidia_{registration_id}",

        "notes": {

            "registration_id":
                str(registration_id),

            "name":
                name,

            "class":
                class_name

        }

    }


    try:

        razorpay_order = (
            razorpay_client
            .order
            .create(
                data=order_data
            )
        )

    except Exception as error:

        print(
            "Razorpay order creation failed:",
            error
        )


        connection.execute(
            """
            DELETE FROM registrations
            WHERE id = ?
            """,
            (
                registration_id,
            )
        )


        connection.commit()

        connection.close()


        return (
            "Unable to create payment order.",
            500
        )


    # --------------------------------------------------------
    # SAVE RAZORPAY ORDER ID
    # --------------------------------------------------------

    connection.execute(
        """
        UPDATE registrations

        SET razorpay_order_id = ?

        WHERE id = ?
        """,
        (
            razorpay_order["id"],
            registration_id
        )
    )


    connection.commit()

    connection.close()


    # --------------------------------------------------------
    # PAYMENT PAGE
    # --------------------------------------------------------

    return render_template(

        "payment.html",

        key_id=
            RAZORPAY_KEY_ID,

        order_id=
            razorpay_order["id"],

        amount=
            TICKET_PRICE * 100,

        name=
            name,

        registration_id=
            registration_id

    )


# ============================================================
# PAYMENT SUCCESS + SIGNATURE VERIFICATION
# ============================================================

@app.route(
    "/payment-success",
    methods=["POST"]
)
def payment_success():

    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({

            "success":
                False,

            "error":
                "No payment data received."

        }), 400


    payment_id = data.get(
        "razorpay_payment_id"
    )

    returned_order_id = data.get(
        "razorpay_order_id"
    )

    received_signature = data.get(
        "razorpay_signature"
    )


    if (
        not payment_id
        or not returned_order_id
        or not received_signature
    ):

        return jsonify({

            "success":
                False,

            "error":
                "Incomplete payment response."

        }), 400


    connection = get_db_connection()


    # ========================================================
    # FIND REGISTRATION
    # ========================================================

    registration = connection.execute(
        """
        SELECT *

        FROM registrations

        WHERE razorpay_order_id = ?
        """,
        (
            returned_order_id,
        )
    ).fetchone()


    if registration is None:

        connection.close()


        return jsonify({

            "success":
                False,

            "error":
                "Payment order not found."

        }), 404


    # ========================================================
    # CRYPTOGRAPHIC SIGNATURE VERIFICATION
    # ========================================================

    message = (
        f"{registration['razorpay_order_id']}|{payment_id}"
    )


    expected_signature = hmac.new(

        RAZORPAY_KEY_SECRET.encode(
            "utf-8"
        ),

        message.encode(
            "utf-8"
        ),

        hashlib.sha256

    ).hexdigest()


    signature_valid = hmac.compare_digest(

        expected_signature,

        received_signature

    )


    if not signature_valid:

        connection.close()


        print(
            "Rejected invalid payment signature "
            f"for registration "
            f"{registration['id']}"
        )


        return jsonify({

            "success":
                False,

            "error":
                "Payment verification failed."

        }), 400


    # ========================================================
    # ALREADY PAID
    # ========================================================

    if registration["payment_status"] == "PAID":

        registration_id = (
            registration["id"]
        )


        connection.close()


        session[
            "payment_verified_registration_id"
        ] = registration_id


        return jsonify({

            "success":
                True,

            "message":
                "Payment already verified.",

            "registration_id":
                registration_id

        })


    # ========================================================
    # FETCH PAYMENT DIRECTLY FROM RAZORPAY
    # ========================================================

    try:

        payment_details = (
            razorpay_client
            .payment
            .fetch(
                payment_id
            )
        )

    except Exception as error:

        connection.close()


        print(
            "Unable to fetch Razorpay payment:",
            error
        )


        return jsonify({

            "success":
                False,

            "error":
                "Unable to verify payment status."

        }), 500


    # ========================================================
    # VERIFY PAYMENT BELONGS TO OUR ORDER
    # ========================================================

    if payment_details.get(
        "order_id"
    ) != registration["razorpay_order_id"]:

        connection.close()


        print(
            "Payment/order mismatch for registration "
            f"{registration['id']}"
        )


        return jsonify({

            "success":
                False,

            "error":
                "Payment order mismatch."

        }), 400


    # ========================================================
    # VERIFY PAYMENT AMOUNT
    # ========================================================

    try:

        payment_amount = int(
            payment_details.get(
                "amount",
                0
            )
        )

    except (
        TypeError,
        ValueError
    ):

        payment_amount = 0


    if payment_amount != (
        TICKET_PRICE * 100
    ):

        connection.close()


        print(
            "Incorrect payment amount for registration "
            f"{registration['id']}"
        )


        return jsonify({

            "success":
                False,

            "error":
                "Incorrect payment amount."

        }), 400


    # ========================================================
    # PAYMENT MUST BE CAPTURED
    # ========================================================

    payment_status = payment_details.get(
        "status"
    )


    if payment_status != "captured":

        connection.close()


        print(
            "Payment not captured for registration "
            f"{registration['id']}: "
            f"{payment_status}"
        )


        return jsonify({

            "success":
                False,

            "error":
                "Payment has not been captured yet."

        }), 400


    # ========================================================
    # MARK PAYMENT AS PAID
    # ========================================================

    connection.execute(
        """
        UPDATE registrations

        SET

            payment_status = 'PAID',

            razorpay_payment_id = ?

        WHERE

            id = ?

            AND razorpay_order_id = ?

            AND payment_status != 'PAID'
        """,
        (

            payment_id,

            registration["id"],

            registration["razorpay_order_id"]

        )
    )


    connection.commit()

    connection.close()


    # ========================================================
    # BIND VERIFIED PAYMENT TO SESSION
    # ========================================================

    session[
        "payment_verified_registration_id"
    ] = registration["id"]


    print(
        "Payment verified successfully "
        f"for registration "
        f"{registration['id']}"
    )


    return jsonify({

        "success":
            True,

        "message":
            "Payment verified successfully.",

        "registration_id":
            registration["id"]

    })


# ============================================================
# GENERATE TICKET
# ============================================================

def generate_ticket(registration):

    connection = get_db_connection()


    # ========================================================
    # EXISTING TICKET
    # ========================================================

    if registration["ticket_token"]:

        ticket_number = (
            registration["ticket_number"]
        )

        ticket_token = (
            registration["ticket_token"]
        )


        connection.close()


        # ----------------------------------------------------
        # RECREATE QR IF MISSING
        # ----------------------------------------------------

        qr_path = (
            QR_FOLDER
            /
            f"{ticket_number}.png"
        )


        if not qr_path.exists():

            qr = qrcode.QRCode(

                version=None,

                error_correction=
                    qrcode.constants.ERROR_CORRECT_H,

                box_size=10,

                border=4

            )


            qr.add_data(
                ticket_token
            )


            qr.make(
                fit=True
            )


            qr_image = qr.make_image()


            qr_image.save(
                qr_path
            )


        return (

            ticket_number,

            ticket_token

        )


    # ========================================================
    # CREATE UNIQUE TICKET NUMBER
    # ========================================================

    ticket_number = (

        "OBS-27-"

        +

        secrets
        .token_hex(3)
        .upper()

    )


    # ========================================================
    # SECURE TICKET TOKEN
    # ========================================================

    ticket_token = (
        secrets.token_urlsafe(32)
    )


    # ========================================================
    # SAVE TICKET
    # ========================================================

    connection.execute(
        """
        UPDATE registrations

        SET

            ticket_number = ?,

            ticket_token = ?,

            ticket_generated_at = ?

        WHERE id = ?
        """,
        (

            ticket_number,

            ticket_token,

            current_ist_time(),

            registration["id"]

        )
    )


    connection.commit()

    connection.close()


    # ========================================================
    # GENERATE QR CODE
    # ========================================================

    qr = qrcode.QRCode(

        version=None,

        error_correction=
            qrcode.constants.ERROR_CORRECT_H,

        box_size=10,

        border=4

    )


    qr.add_data(
        ticket_token
    )


    qr.make(
        fit=True
    )


    qr_image = qr.make_image()


    qr_path = (

        QR_FOLDER

        /

        f"{ticket_number}.png"

    )


    qr_image.save(
        qr_path
    )


    return (

        ticket_number,

        ticket_token

    )


# ============================================================
# PAYMENT COMPLETE → TICKET
# ============================================================

@app.route(
    "/payment-complete/<int:registration_id>"
)
def payment_complete(
    registration_id
):

    # ========================================================
    # SESSION SECURITY CHECK
    # ========================================================

    verified_registration_id = session.get(
        "payment_verified_registration_id"
    )


    if verified_registration_id != registration_id:

        return (
            "Ticket access is not authorised.",
            403
        )


    # ========================================================
    # GET REGISTRATION
    # ========================================================

    connection = get_db_connection()


    registration = connection.execute(
        """
        SELECT *

        FROM registrations

        WHERE id = ?
        """,
        (
            registration_id,
        )
    ).fetchone()


    connection.close()


    if registration is None:

        return (
            "Registration not found.",
            404
        )


    # ========================================================
    # PAYMENT MUST BE PAID
    # ========================================================

    if (
        registration["payment_status"]
        !=
        "PAID"
    ):

        return (
            "Payment has not been verified.",
            403
        )


    # ========================================================
    # GENERATE / REUSE TICKET
    # ========================================================

    ticket_number, ticket_token = (
        generate_ticket(
            registration
        )
    )


    # ========================================================
    # FRESH DATABASE INFORMATION
    # ========================================================

    connection = get_db_connection()


    registration = connection.execute(
        """
        SELECT *

        FROM registrations

        WHERE id = ?
        """,
        (
            registration_id,
        )
    ).fetchone()


    connection.close()


    # ========================================================
    # QR FILE
    # ========================================================

    qr_filename = (
        f"{ticket_number}.png"
    )


    # ========================================================
    # RENDER TICKET
    # ========================================================

    return render_template(

        "ticket.html",

        registration=
            registration,

        ticket_number=
            ticket_number,

        qr_filename=
            qr_filename

    )


# ============================================================
# ============================================================
# HOST / ADMIN SYSTEM
# ============================================================
# ============================================================


# ============================================================
# HOST LOGIN
# ============================================================

@app.route(
    "/host",
    methods=["GET", "POST"]
)
def host_login():

    if session.get(
        "host_authenticated"
    ):

        return redirect(
            url_for("host_dashboard")
        )


    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()


        password = request.form.get(
            "password",
            ""
        )


        username_correct = hmac.compare_digest(

            username,

            ADMIN_USERNAME

        )


        password_correct = hmac.compare_digest(

            password,

            ADMIN_PASSWORD

        )


        if (
            username_correct
            and
            password_correct
        ):

            session.clear()

            session[
                "host_authenticated"
            ] = True

            session.permanent = True

            session[
                "host_username"
            ] = ADMIN_USERNAME


            return redirect(
                url_for("host_dashboard")
            )


        return render_template(

            "host_login.html",

            error=
                "Invalid username or password."

        ), 401


    return render_template(
        "host_login.html"
    )


# ============================================================
# HOST AUTHENTICATION HELPER
# ============================================================

def host_required():

    return session.get(
        "host_authenticated"
    ) is True


# ============================================================
# HOST DASHBOARD
# ============================================================

@app.route(
    "/host/dashboard"
)
def host_dashboard():

    if not host_required():

        return redirect(
            url_for("host_login")
        )


    # ========================================================
    # FILTERS
    # ========================================================

    search = request.args.get(
        "search",
        ""
    ).strip()


    payment_filter = request.args.get(
        "payment",
        "ALL"
    ).upper()


    entry_filter = request.args.get(
        "entry",
        "ALL"
    ).upper()


    class_filter = request.args.get(
        "class",
        "ALL"
    ).upper()


    # ========================================================
    # ALLOWED FILTERS
    # ========================================================

    allowed_payment_filters = {

        "ALL",

        "PAID",

        "PENDING"

    }


    allowed_entry_filters = {

        "ALL",

        "CHECKED_IN",

        "NOT_CHECKED_IN"

    }


    allowed_class_filters = {

        "ALL",

        "10-A",

        "10-B",

        "10-C",

        "10-D"

    }


    if payment_filter not in allowed_payment_filters:

        payment_filter = "ALL"


    if entry_filter not in allowed_entry_filters:

        entry_filter = "ALL"


    if class_filter not in allowed_class_filters:

        class_filter = "ALL"


    connection = get_db_connection()


    # ========================================================
    # STATISTICS
    # ========================================================

    total_registrations = connection.execute(
        """
        SELECT COUNT(*)

        FROM registrations
        """
    ).fetchone()[0]


    total_paid = connection.execute(
        """
        SELECT COUNT(*)

        FROM registrations

        WHERE payment_status = 'PAID'
        """
    ).fetchone()[0]


    total_pending = connection.execute(
        """
        SELECT COUNT(*)

        FROM registrations

        WHERE payment_status != 'PAID'
        """
    ).fetchone()[0]


    total_checked_in = connection.execute(
        """
        SELECT COUNT(*)

        FROM registrations

        WHERE ticket_status = 'CHECKED_IN'
        """
    ).fetchone()[0]


    total_not_checked_in = connection.execute(
        """
        SELECT COUNT(*)

        FROM registrations

        WHERE ticket_status != 'CHECKED_IN'

        AND payment_status = 'PAID'
        """
    ).fetchone()[0]


    total_collected = connection.execute(
        """
        SELECT COALESCE(
            SUM(amount),
            0
        )

        FROM registrations

        WHERE payment_status = 'PAID'
        """
    ).fetchone()[0]


    # ========================================================
    # BUILD FILTERED QUERY
    # ========================================================

    query = """
        SELECT

            id,

            name,

            class_name,

            amount,

            payment_status,

            ticket_status,

            ticket_number,

            created_at,

            checked_in_at

        FROM registrations

        WHERE 1 = 1
    """


    parameters = []


    # ========================================================
    # SEARCH
    # ========================================================

    if search:

        query += """
            AND (

                name LIKE ?

                OR class_name LIKE ?

                OR ticket_number LIKE ?

                OR CAST(id AS TEXT) LIKE ?

            )
        """


        search_value = (
            f"%{search}%"
        )


        parameters.extend([

            search_value,

            search_value,

            search_value,

            search_value

        ])


    # ========================================================
    # PAYMENT FILTER
    # ========================================================

    if payment_filter == "PAID":

        query += """
            AND payment_status = 'PAID'
        """


    elif payment_filter == "PENDING":

        query += """
            AND payment_status != 'PAID'
        """


    # ========================================================
    # ENTRY FILTER
    # ========================================================

    if entry_filter == "CHECKED_IN":

        query += """
            AND ticket_status = 'CHECKED_IN'
        """


    elif entry_filter == "NOT_CHECKED_IN":

        query += """
            AND ticket_status != 'CHECKED_IN'

            AND payment_status = 'PAID'
        """


    # ========================================================
    # CLASS FILTER
    # ========================================================

    if class_filter != "ALL":

        query += """
            AND class_name = ?
        """


        parameters.append(
            class_filter
        )


    # ========================================================
    # ORDER
    # ========================================================

    query += """
        ORDER BY id DESC
    """


    registrations = connection.execute(
        query,
        parameters
    ).fetchall()


    connection.close()


    # ========================================================
    # RENDER DASHBOARD
    # ========================================================

    return render_template(

        "host_dashboard.html",

        total_registrations=
            total_registrations,

        total_paid=
            total_paid,

        total_pending=
            total_pending,

        total_checked_in=
            total_checked_in,

        total_not_checked_in=
            total_not_checked_in,

        total_collected=
            total_collected,

        registrations=
            registrations,

        search=
            search,

        payment_filter=
            payment_filter,

        entry_filter=
            entry_filter,

        class_filter=
            class_filter

    )


# ============================================================
# HOST QR SCANNER
# ============================================================

@app.route(
    "/host/scanner"
)
def host_scanner():

    if not host_required():

        return redirect(
            url_for("host_login")
        )


    return render_template(
        "host_scanner.html"
    )


# ============================================================
# VALIDATE QR TICKET
# ============================================================

@app.route(
    "/host/validate-ticket",
    methods=["POST"]
)
def validate_ticket():

    if not host_required():

        return jsonify({

            "success":
                False,

            "error":
                "Unauthorized."

        }), 401


    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({

            "success":
                False,

            "error":
                "No ticket data received."

        }), 400


    ticket_token = data.get(
        "ticket_token"
    )


    if not ticket_token:

        return jsonify({

            "success":
                False,

            "error":
                "No ticket token provided."

        }), 400


    connection = get_db_connection()


    registration = connection.execute(
        """
        SELECT

            id,

            name,

            class_name,

            amount,

            payment_status,

            ticket_status,

            ticket_number,

            checked_in_at

        FROM registrations

        WHERE ticket_token = ?
        """,
        (
            ticket_token,
        )
    ).fetchone()


    connection.close()


    # ========================================================
    # TICKET DOESN'T EXIST
    # ========================================================

    if registration is None:

        return jsonify({

            "success":
                False,

            "status":
                "INVALID",

            "message":
                "This ticket is not recognised."

        })


    # ========================================================
    # PAYMENT ISN'T VERIFIED
    # ========================================================

    if registration["payment_status"] != "PAID":

        return jsonify({

            "success":
                False,

            "status":
                "UNPAID",

            "message":
                "Payment has not been verified.",

            "name":
                registration["name"],

            "class_name":
                registration["class_name"],

            "ticket_number":
                registration["ticket_number"]

        })


    # ========================================================
    # ALREADY CHECKED IN
    # ========================================================

    if registration["ticket_status"] == "CHECKED_IN":

        return jsonify({

            "success":
                False,

            "status":
                "ALREADY_CHECKED_IN",

            "message":
                "This ticket has already been checked in.",

            "name":
                registration["name"],

            "class_name":
                registration["class_name"],

            "amount":
                registration["amount"],

            "ticket_number":
                registration["ticket_number"],

            "checked_in_at":
                registration["checked_in_at"]

        })


    # ========================================================
    # VALID
    # ========================================================

    return jsonify({

        "success":
            True,

        "status":
            "VALID",

        "message":
            "Valid entry pass.",

        "registration_id":
            registration["id"],

        "name":
            registration["name"],

        "class_name":
            registration["class_name"],

        "amount":
            registration["amount"],

        "ticket_number":
            registration["ticket_number"]

    })


# ============================================================
# CHECK IN TICKET
# ============================================================

@app.route(
    "/host/check-in",
    methods=["POST"]
)
def check_in_ticket():

    if not host_required():

        return jsonify({

            "success":
                False,

            "error":
                "Unauthorized."

        }), 401


    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({

            "success":
                False,

            "error":
                "No ticket data received."

        }), 400


    ticket_token = data.get(
        "ticket_token"
    )


    if not ticket_token:

        return jsonify({

            "success":
                False,

            "error":
                "No ticket token provided."

        }), 400


    connection = get_db_connection()


    registration = connection.execute(
        """
        SELECT *

        FROM registrations

        WHERE ticket_token = ?
        """,
        (
            ticket_token,
        )
    ).fetchone()


    if registration is None:

        connection.close()


        return jsonify({

            "success":
                False,

            "status":
                "INVALID",

            "message":
                "Invalid ticket."

        }), 404


    # ========================================================
    # PAYMENT VERIFICATION CHECK
    # ========================================================

    if registration["payment_status"] != "PAID":

        connection.close()


        return jsonify({

            "success":
                False,

            "status":
                "UNPAID",

            "message":
                "Payment has not been verified."

        })


    # ========================================================
    # ALREADY CHECKED IN
    # ========================================================

    if registration["ticket_status"] == "CHECKED_IN":

        connection.close()


        return jsonify({

            "success":
                False,

            "status":
                "ALREADY_CHECKED_IN",

            "message":
                "This ticket has already been checked in.",

            "name":
                registration["name"],

            "class_name":
                registration["class_name"],

            "ticket_number":
                registration["ticket_number"],

            "checked_in_at":
                registration["checked_in_at"]

        })


    # ========================================================
    # ATOMIC CHECK-IN
    # ========================================================

    checked_in_at = current_ist_time()


    cursor = connection.execute(
        """
        UPDATE registrations

        SET

            ticket_status = 'CHECKED_IN',

            checked_in_at = ?

        WHERE

            ticket_token = ?

            AND payment_status = 'PAID'

            AND ticket_status != 'CHECKED_IN'
        """,
        (

            checked_in_at,

            ticket_token

        )
    )


    connection.commit()


    # ========================================================
    # CHECK WHETHER UPDATE ACTUALLY HAPPENED
    # ========================================================

    if cursor.rowcount != 1:

        connection.close()


        return jsonify({

            "success":
                False,

            "status":
                "ALREADY_CHECKED_IN",

            "message":
                "This ticket was already checked in."

        })


    connection.close()


    return jsonify({

        "success":
            True,

        "status":
            "CHECKED_IN",

        "message":
            "Entry confirmed.",

        "name":
            registration["name"],

        "class_name":
            registration["class_name"],

        "ticket_number":
            registration["ticket_number"],

        "checked_in_at":
            checked_in_at

    })


# ============================================================
# HOST CHECK-IN ACTIVITY
# ============================================================

@app.route(
    "/host/check-in-activity"
)
def host_check_in_activity():

    if not host_required():

        return jsonify({

            "success":
                False,

            "error":
                "Unauthorized."

        }), 401


    connection = get_db_connection()


    check_ins = connection.execute(
        """
        SELECT

            id,

            name,

            class_name,

            ticket_number,

            checked_in_at

        FROM registrations

        WHERE ticket_status = 'CHECKED_IN'

        ORDER BY checked_in_at DESC

        
        """
    ).fetchall()


    total_checked_in = connection.execute(
        """
        SELECT COUNT(*)

        FROM registrations

        WHERE ticket_status = 'CHECKED_IN'
        """
    ).fetchone()[0]


    connection.close()


    activity = []


    for registration in check_ins:

        activity.append({

            "id":
                registration["id"],

            "name":
                registration["name"],

            "class_name":
                registration["class_name"],

            "ticket_number":
                registration["ticket_number"],

            "checked_in_at":
                registration["checked_in_at"]

        })


    return jsonify({

        "success":
            True,

        "total_checked_in":
            total_checked_in,

        "activity":
            activity

    })


# ============================================================
# HOST LOGOUT
# ============================================================

@app.route(
    "/host/logout"
)
def host_logout():

    session.clear()


    return redirect(
        url_for("host_login")
    )


# ============================================================
# START SERVER
# ============================================================


if __name__ == "__main__":

    initialize_database()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        ssl_context=(
            "192.168.29.218.pem",
            "192.168.29.218-key.pem"
        )
    )