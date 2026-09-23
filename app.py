from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session
import os
import random
from datetime import date, datetime
import smtplib
from email.message import EmailMessage
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print("Supabase connected successfully!")

SENDER_EMAIL = os.getenv("NEARU_EMAIL")
SENDER_PASSWORD = os.getenv("NEARU_APP_PASSWORD")


app = Flask(__name__)
app.secret_key = "your_secret_key"  # Replace

CATEGORIES = ["Tutor", "Part-time Job", "PG-Hostel", "Other"]


    
def days_ago(date_str):
    d = date.fromisoformat(date_str)
    today = date.today()
    diff = (today - d).days
    if diff <= 0:
        return "Today"
    if diff == 1:
        return "Yesterday"
    return f"{diff} days ago"

#----------------------------------
def send_verification_email(to_email, verification_code):
    print("SENDER EMAIL:", SENDER_EMAIL)
    print("APP PASSWORD EXISTS:", bool(SENDER_PASSWORD))

    msg = EmailMessage()

    msg["Subject"] = "NearU - Email Verification Code"
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email

    msg.set_content(
        f"""Hello,

Your NearU verification code is:

{verification_code}

Please enter this code on the NearU verification page.

Thank you,
NearU Team
"""
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
        smtp.send_message(msg)
        
@app.route("/")
def intro():

    # Agar user already logged in hai
    if "user_id" in session:
        return redirect(url_for("index"))

    # New / logged-out user
    return render_template("intro.html")

@app.route("/home")
def index():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    search = request.args.get("search", "").strip().lower()
    category = request.args.get("category", "All")
    sort = request.args.get("sort", "newest")

    # Logged-in user's profile
    profile_result = (
        supabase
        .table("profiles")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )

    profile = (
        profile_result.data[0]
        if profile_result.data
        else None
    )

    # Get all listings
    listings_result = (
        supabase
        .table("listings")
        .select("*")
        .execute()
    )

    listings = listings_result.data or []

    # Get all profiles
    profiles_result = (
        supabase
        .table("profiles")
        .select("user_id, name, profile_photo")
        .execute()
    )

    profiles = profiles_result.data or []

    # Make profile lookup
    profile_map = {
        p["user_id"]: p
        for p in profiles
    }

    # Add poster information to listings
    for listing in listings:

        poster = profile_map.get(listing.get("user_id"), {})

        listing["poster_name"] = poster.get("name", "Unknown User")
        listing["poster_photo"] = poster.get("profile_photo")

    # Category filter
    if category != "All":
        listings = [
            l for l in listings
            if l.get("category") == category
        ]

    # Search filter
    if search:
        listings = [
            l for l in listings
            if search in l.get("title", "").lower()
            or search in l.get("location", "").lower()
            or search in l.get("description", "").lower()
        ]

    # Sorting
    if sort == "price":
        listings.sort(
            key=lambda x: float(x.get("price") or 0)
        )
    else:
        listings.sort(
            key=lambda x: x.get("posted_date", ""),
            reverse=True
        )

    # Add "posted ago"
    for listing in listings:
        listing["posted_ago"] = days_ago(
            listing.get("posted_date")
        )

    # Statistics
    stats = {
        "tutors": len([
            l for l in listings
            if l.get("category") == "Tutor"
        ]),

        "jobs": len([
            l for l in listings
            if l.get("category") == "Part-time Job"
        ]),

        "rooms": len([
            l for l in listings
            if l.get("category") == "PG-Hostel"
        ])
    }

    return render_template(
        "index.html",
        listings=listings,
        categories=CATEGORIES,
        stats=stats,
        search=search,
        active_category=category,
        active_sort=sort,
        profile=profile
    )
    
    
@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            return "Passwords do not match!"

        # Check existing user in Supabase
        existing_user = (
            supabase
            .table("users")
            .select("*")
            .eq("email", email)
            .execute()
        )

        if existing_user.data:
            return "Email already registered!"

        # Generate 6-digit verification code
        verification_code = str(random.randint(100000, 999999))

        # Hash password
        password_hash = generate_password_hash(password)

        # Create user in Supabase
        new_user = (
            supabase
            .table("users")
            .insert({
                "name": name,
                "email": email,
                "password_hash": password_hash,
                "email_verified": False,
                "verification_code": verification_code
            })
            .execute()
        )

        if not new_user.data:
            return "Something went wrong while creating account!"

        # Get new user's ID
        user_id = new_user.data[0]["id"]

        # Create profile
        supabase.table("profiles").insert({
            "user_id": user_id,
            "name": name
        }).execute()

        # Send verification email
        send_verification_email(email, verification_code)

        return redirect(url_for("verify_email", email=email))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        # Find user in Supabase
        result = (
            supabase
            .table("users")
            .select("*")
            .eq("email", email)
            .execute()
        )

        if not result.data:
            return "Invalid email or password!"

        user = result.data[0]

        # Check password
        if not check_password_hash(user["password_hash"], password):
            return "Invalid email or password!"

        # Check email verification
        if not user["email_verified"]:
            return "Please verify your email first!"

        # Save logged-in user's ID
        session["user_id"] = user["id"]

        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        code = request.form["code"].strip()

        # Find user in Supabase
        result = (
            supabase
            .table("users")
            .select("*")
            .eq("email", email)
            .execute()
        )

        if not result.data:
            return "User not found!"

        user = result.data[0]

        # Check verification code
        if user["verification_code"] != code:
            return "Invalid verification code!"

        # Verify email in Supabase
        supabase.table("users").update({
            "email_verified": True,
            "verification_code": None
        }).eq("email", email).execute()

        return redirect(url_for("dashboard"))

    return render_template("verify_email.html")

@app.route("/add", methods=["POST"])
def add_listing():
    if "user_id" not in session:
        return redirect(url_for("login"))

    supabase.table("listings").insert({
        "user_id": session["user_id"],
        "title": request.form["title"],
        "category": request.form["category"],
        "description": request.form.get("description", ""),
        "location": request.form["location"],
        "price": int(request.form.get("price") or 0),
        "price_unit": request.form.get("price_unit", ""),
        "contact": request.form["contact"],
        "posted_date": date.today().isoformat()
    }).execute()

    return redirect(url_for("index"))

@app.route("/edit/<int:listing_id>", methods=["GET", "POST"])
def edit_listing(listing_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    result = (
        supabase
        .table("listings")
        .select("*")
        .eq("id", listing_id)
        .execute()
    )

    if not result.data:
        return redirect(url_for("index"))

    listing = result.data[0]

    if listing["user_id"] != user_id:
        return "You are not allowed to edit this listing!", 403

    if request.method == "POST":
        title = request.form["title"].strip()
        category = request.form["category"].strip()
        description = request.form.get("description", "").strip()
        location = request.form["location"].strip()
        contact = request.form["contact"].strip()
        price = int(request.form.get("price") or 0)
        price_unit = request.form.get("price_unit", "")

        supabase.table("listings").update({
            "title": title,
            "category": category,
            "description": description,
            "location": location,
            "price": price,
            "price_unit": price_unit,
            "contact": contact
        }).eq("id", listing_id).eq("user_id", user_id).execute()

        return redirect(url_for("index"))

    return render_template("edit_listing.html", listing=listing)


@app.route("/delete/<int:listing_id>", methods=["POST"])
def delete_listing(listing_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    result = (
        supabase
        .table("listings")
        .select("id, user_id")
        .eq("id", listing_id)
        .execute()
    )

    if not result.data:
        return redirect(url_for("index"))

    listing = result.data[0]

    if listing["user_id"] != user_id:
        return "You are not allowed to delete this listing!", 403

    supabase.table("listings") \
        .delete() \
        .eq("id", listing_id) \
        .eq("user_id", user_id) \
        .execute()

    return redirect(url_for("index"))


@app.route("/chat/<int:user_id>")
def chat(user_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    # Other user's basic information
    user_result = (
        supabase
        .table("users")
        .select("id, name")
        .eq("id", user_id)
        .execute()
    )

    if not user_result.data:
        return redirect(url_for("index"))

    other_user = user_result.data[0]

    # Other user's profile
    profile_result = (
        supabase
        .table("profiles")
        .select("name, profile_photo")
        .eq("user_id", user_id)
        .execute()
    )

    if profile_result.data:
        profile = profile_result.data[0]

        other_user["name"] = profile.get(
            "name",
            other_user.get("name")
        )

        other_user["profile_photo"] = profile.get(
            "profile_photo"
        )
    else:
        other_user["profile_photo"] = None

    # Messages sent by current user
    sent_result = (
        supabase
        .table("messages")
        .select("*")
        .eq("sender_id", current_user)
        .eq("receiver_id", user_id)
        .execute()
    )

    # Messages received from other user
    received_result = (
        supabase
        .table("messages")
        .select("*")
        .eq("sender_id", user_id)
        .eq("receiver_id", current_user)
        .execute()
    )

    messages = (
        (sent_result.data or [])
        + (received_result.data or [])
    )

    # Oldest → newest
    messages.sort(
        key=lambda x: x.get("sent_at", "")
    )

    return render_template(
        "chat.html",
        other_user=other_user,
        messages=messages
    )
    
@app.route("/messages",endpoint="messages")
def messages_inbox():
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    # Messages sent by current user
    sent_result = (
        supabase
        .table("messages")
        .select("*")
        .eq("sender_id", current_user)
        .execute()
    )

    # Messages received by current user
    received_result = (
        supabase
        .table("messages")
        .select("*")
        .eq("receiver_id", current_user)
        .execute()
    )

    all_messages = (
        (sent_result.data or [])
        + (received_result.data or [])
    )

    # Latest messages first
    all_messages.sort(
        key=lambda x: x.get("id", 0),
        reverse=True
    )

    # Keep only the latest message with each person
    latest_by_user = {}

    for message in all_messages:
        if message["sender_id"] == current_user:
            other_id = message["receiver_id"]
        else:
            other_id = message["sender_id"]

        if other_id not in latest_by_user:
            latest_by_user[other_id] = message

    user_ids = list(latest_by_user.keys())

    chats = []

    if user_ids:
        users_result = (
            supabase
            .table("users")
            .select("id, name")
            .in_("id", user_ids)
            .execute()
        )

        profiles_result = (
            supabase
            .table("profiles")
            .select("user_id, name, profile_photo")
            .in_("user_id", user_ids)
            .execute()
        )

        users_map = {
            user["id"]: user
            for user in (users_result.data or [])
        }

        profiles_map = {
            profile["user_id"]: profile
            for profile in (profiles_result.data or [])
        }

        for other_id, message in latest_by_user.items():

            user = users_map.get(other_id, {})
            profile = profiles_map.get(other_id, {})

            chats.append({
                "id": other_id,
                "name": profile.get(
                    "name",
                    user.get("name", "Unknown User")
                ),
                "profile_photo": profile.get("profile_photo"),
                "message": (
                    "🎤 Voice message"
                    if message.get("message_type") == "audio"
                    else message.get("message", "")
                ),
                "sent_at": message.get("sent_at")
            })

    return render_template(
        "messages.html",
        chats=chats
    )
    
@app.route("/send_message/<int:user_id>", methods=["POST"])
def send_message(user_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    message = request.form.get("message", "").strip()

    if not message:
        return redirect(url_for("chat", user_id=user_id))

    supabase.table("messages").insert({
        "sender_id": current_user,
        "receiver_id": user_id,
        "message": message,
        "message_type": "text",
        "audio_file": None,
        "sent_at": datetime.now().isoformat()
    }).execute()

    return redirect(url_for("chat", user_id=user_id))

@app.route("/send_voice/<int:user_id>", methods=["POST"])
def send_voice(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    audio = request.files.get("audio")

    if not audio or not audio.filename:
        return {
            "success": False,
            "message": "Audio not received"
        }, 400


    # Unique filename
    extension = os.path.splitext(audio.filename)[1] or ".webm"

    filename = (
        f"voice_{current_user}_{user_id}_"
        f"{int(datetime.now().timestamp() * 1000)}"
        f"{extension}"
    )


    # Upload folder
    upload_folder = os.path.join(
        app.root_path,
        "static",
        "uploads",
        "voice"
    )

    os.makedirs(
        upload_folder,
        exist_ok=True
    )


    # Save audio
    audio_path = os.path.join(
        upload_folder,
        filename
    )

    audio.save(audio_path)


    # Database path
    audio_file = (
        "uploads/voice/" + filename
    )


    # Save in Supabase
    supabase.table("messages").insert({

        "sender_id": current_user,
        "receiver_id": user_id,
        "message": "",
        "message_type": "audio",
        "audio_file": audio_file,
        "sent_at": datetime.now().isoformat()

    }).execute()


    # Return JSON instead of redirect
    return {
        "success": True,
        "audio_file": audio_file
    }

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html")
@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # =========================
    # SAVE / UPDATE PROFILE
    # =========================

    if request.method == "POST":

        print("\n========== PROFILE POST ==========")

        name = request.form.get("name", "").strip()
        about = request.form.get("about", "").strip()
        location = request.form.get("location", "").strip()
        skills = request.form.get("skills", "").strip()
        experience = request.form.get("experience", "").strip()

        # =========================
        # GPS COORDINATES
        # =========================

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        print("RAW LATITUDE:", latitude)
        print("RAW LONGITUDE:", longitude)

        try:
            latitude = float(latitude) if latitude else None
            longitude = float(longitude) if longitude else None
        except (ValueError, TypeError):
            latitude = None
            longitude = None

        print("GPS LATITUDE:", latitude)
        print("GPS LONGITUDE:", longitude)

        # =========================
        # EXISTING PROFILE
        # =========================

        result = (
            supabase
            .table("profiles")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )

        existing_profile = (
            result.data[0]
            if result.data
            else None
        )

        profile_photo = (
            existing_profile.get("profile_photo")
            if existing_profile
            else None
        )

        # =========================
        # PROFILE PHOTO
        # =========================

        photo = request.files.get("profile_photo")

        if photo and photo.filename:

            filename = secure_filename(photo.filename)

            upload_folder = os.path.join(
                app.root_path,
                "static",
                "uploads"
            )

            os.makedirs(
                upload_folder,
                exist_ok=True
            )

            photo_path = os.path.join(
                upload_folder,
                filename
            )

            photo.save(photo_path)

            profile_photo = "uploads/" + filename

        # =========================
        # PROFILE DATA
        # =========================

        profile_data = {
            "name": name,
            "about": about,
            "location": location,
            "latitude": latitude,
            "longitude": longitude,
            "skills": skills,
            "experience": experience,
            "profile_photo": profile_photo
        }

        # =========================
        # UPDATE EXISTING PROFILE
        # =========================

        if existing_profile:

            response = (
                supabase
                .table("profiles")
                .update(profile_data)
                .eq("user_id", user_id)
                .execute()
            )

            print("PROFILE UPDATED")

        # =========================
        # CREATE NEW PROFILE
        # =========================

        else:

            profile_data["user_id"] = user_id

            response = (
                supabase
                .table("profiles")
                .insert(profile_data)
                .execute()
            )

            print("PROFILE CREATED")

        # =========================
        # UPDATE USER NAME
        # =========================

        supabase.table("users").update({
            "name": name
        }).eq("id", user_id).execute()

        print("SAVED LATITUDE:", latitude)
        print("SAVED LONGITUDE:", longitude)
        print("================================\n")

        # =========================
        # GO HOME
        # =========================

        return redirect(url_for("index"))

    # =========================
    # LOAD PROFILE
    # =========================

    profile_result = (
        supabase
        .table("profiles")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )

    profile_data = (
        profile_result.data[0]
        if profile_result.data
        else None
    )

    # =========================
    # LOAD USER
    # =========================

    user_result = (
        supabase
        .table("users")
        .select("name, email")
        .eq("id", user_id)
        .execute()
    )

    user = (
        user_result.data[0]
        if user_result.data
        else None
    )

    # =========================
    # EDIT MODE
    # =========================

    edit_mode = request.args.get("edit") == "1"

    return render_template(
        "profile.html",
        profile=profile_data,
        user=user,
        edit_mode=edit_mode
    )

    
    
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("intro"))
    
    
    
if __name__ == "__main__":
    app.run(debug=True)
