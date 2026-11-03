from flask import Flask, render_template, request, session, redirect, url_for
from database import get_db_connection
from werkzeug.utils import secure_filename
import os
import uuid
import os
from dotenv import load_dotenv
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask import jsonify
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# Post images
POST_UPLOAD_FOLDER = os.path.join(
    app.static_folder, "uploads"
)

# Profile photos
PROFILE_UPLOAD_FOLDER = os.path.join(
    app.static_folder, "uploads", "profiles"
)

# Certificates
CERTIFICATE_FOLDER = os.path.join(
    app.static_folder, "uploads", "certificates"
)

os.makedirs(POST_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROFILE_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CERTIFICATE_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "jfif"}

def allowed_photo(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

load_dotenv()
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME")

mail = Mail(app)

app.secret_key = "mini-linkedin-secret"
serializer = URLSafeTimedSerializer(app.secret_key)

# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_template("home.html")
   

# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["username"]
        email = request.form["email"]
        role = request.form["role"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Check password
        if password != confirm_password:
            return "Passwords do not match"

        connection = get_db_connection()
        cursor = connection.cursor()

        password = generate_password_hash(password)
        query = """
            INSERT INTO users (name, email, password, role)
            VALUES (%s, %s, %s, %s)
        """

        cursor.execute(query, (
            name,
            email,
            password,
            role
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("login"))

    return render_template("register.html")
  
#recruiter
@app.route("/recruiter-dashboard")
def recruiter_dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    user_id = session["user_id"]
  
    cursor.execute("""
        SELECT id, title, company, location,
            description, job_type, created_at
        FROM jobs
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))

    jobs = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "recruiter_dashboard.html",
        jobs=jobs
    )

#login
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip()
        password = request.form["password"]

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT id, name, password, role
            FROM users
            WHERE email = %s
        """, (email,))

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if not user:
            return "Email not registered", 401

        if not check_password_hash(user[2], password):
            return "Incorrect password", 401

        role = user[3].strip().lower()

        session.clear()
        session["user_id"] = user[0]
        session["user_name"] = user[1]
        session["role"] = role

        
        return redirect(url_for("recruiter_dashboard"))

        

    return render_template("login.html")



@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":
        email = request.form["email"].strip()

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE email = %s",
            (email,)
        )
        user = cursor.fetchone()

        cursor.close()
        connection.close()

        # Same response whether the email exists or not
        message = "If the email is registered, a reset link will be sent."

        if user:
            token = serializer.dumps(email, salt="password-reset")
            reset_url = url_for(
                "reset_password",
                token=token,
                _external=True
            )

            try:
                msg = Message(
                    subject="Reset Your LinkedIn Password",
                    recipients=[email],
                    body=f"Click this link to reset your password:\n\n"
                         f"{reset_url}\n\n"
                         "This link expires in 30 minutes."
                )
                mail.send(msg)
            except Exception:
                app.logger.exception("Password reset email failed")

        if user:
            return (
                f"{message}<br><br>"
                f"Reset Password Link: <a href='{reset_url}'>"
                f"Click here to reset password</a>"
            )

        return message

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):

    try:
        email = serializer.loads(
            token,
            salt="password-reset",
            max_age=1800
        )
    except SignatureExpired:
        return "Reset link has expired. Please request a new one."
    except BadSignature:
        return "Invalid reset link."

    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            return "Passwords do not match."

        if len(password) < 8:
            return "Password must be at least 8 characters."

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            "UPDATE users SET password = %s WHERE email = %s",
            (hashed_password, email)
        )

        connection.commit()
        cursor.close()
        connection.close()

        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)

#  DASHBOARD 
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    # Get posts
    query = """
        SELECT
            posts.post_id,
            users.name,
            posts.content,
            posts.image,
            posts.created_at,
            COUNT(likes.like_id) AS like_count
        FROM posts
        JOIN users
            ON posts.user_id = users.id
        LEFT JOIN likes
            ON posts.post_id = likes.post_id
        GROUP BY
            posts.post_id,
            users.name,
            posts.content,
            posts.image,
            posts.created_at
        ORDER BY posts.created_at DESC
    """

    cursor.execute(query)
    posts = cursor.fetchall()

    # Get comments
    comment_query = """
        SELECT
            comments.post_id,
            users.name,
            comments.comment,
            comments.created_at
        FROM comments
        JOIN users
            ON comments.user_id = users.id
        ORDER BY comments.created_at ASC
    """

    cursor.execute(comment_query)
    comments = cursor.fetchall()

    # Get notifications
    notification_query = """
        SELECT
            id,
            message,
            is_read,
            created_at
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC
    """

    cursor.execute(
        notification_query,
        (session["user_id"],)
    )

    notifications = cursor.fetchall()

    # Get unread notification count
    count_query = """
        SELECT COUNT(*)
        FROM notifications
        WHERE user_id = %s
        AND is_read = 0
    """

    cursor.execute(
        count_query,
        (session["user_id"],)
    )

    unread_count = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    return render_template(
        "dashboard.html",
        posts=posts,
        comments=comments,
        notifications=notifications,
        unread_count=unread_count
    )

#read notification
@app.route("/read-notification/<int:notification_id>")
def read_notification(notification_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        UPDATE notifications
        SET is_read = 1
        WHERE id = %s
        AND user_id = %s
    """

    cursor.execute(
        query,
        (notification_id, session["user_id"])
    )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("dashboard"))

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT u.id, u.name,
               p.about, p.education,
               p.skills, p.experience,
               p.profile_photo
        FROM users u
        LEFT JOIN profiles p ON u.id = p.user_id
        WHERE u.id = %s
        ORDER BY p.profile_id DESC
        LIMIT 1
    """, (session["user_id"],))


    user_profile = cursor.fetchone()

    cursor.execute("""
        SELECT certification_id,
               certificate_name,
               issuing_organization,
               issue_date,
               certificate_file
        FROM certifications
        WHERE user_id = %s
        ORDER BY certification_id DESC
    """, (session["user_id"],))

    certifications = cursor.fetchall()

    cursor.close()
    connection.close()

    if user_profile is None:
        return "User not found.", 404

    return render_template(
        "profile.html",
        user_profile=user_profile,
        certifications=certifications
    )

@app.route("/add-certification", methods=["GET", "POST"])
def add_certification():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        certificate = request.files.get("certificate_image")

        if not certificate or not certificate.filename:
            return "Please select a certificate image.", 400

        if not allowed_photo(certificate.filename):
            return "Only JPG, PNG or WEBP images allowed.", 400

        # Validate actual image content
        from PIL import Image, UnidentifiedImageError

        try:
            certificate.stream.seek(0)

            with Image.open(certificate.stream) as img:
                if img.format not in ("JPEG", "PNG", "WEBP"):
                    return "Invalid image format.", 400
                img.verify()

            certificate.stream.seek(0)

        except (UnidentifiedImageError, OSError):
            return "Invalid certificate image.", 400

        extension = certificate.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{extension}"

        certificate.save(
            os.path.join(CERTIFICATE_FOLDER, filename)
        )

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO certifications
            (user_id, certificate_file)
            VALUES (%s, %s)
        """, (session["user_id"], filename))

        connection.commit()
        cursor.close()
        connection.close()

        return redirect(url_for("profile"))

    return render_template("add_certification.html")

# DELETE CERTIFICATION
@app.route("/delete-certification/<int:cert_id>", methods=["POST"])
def delete_certification(cert_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Validate ownership and retrieve filename
        cursor.execute("""
            SELECT certificate_file
            FROM certifications
            WHERE certification_id = %s AND user_id = %s
        """, (cert_id, user_id))

        cert = cursor.fetchone()

        if cert:
            file_name = cert[0]

            cursor.execute("""
                DELETE FROM certifications
                WHERE certification_id = %s AND user_id = %s
            """, (cert_id, user_id))

            connection.commit()

            if file_name:
                file_path = os.path.join(CERTIFICATE_FOLDER, file_name)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        app.logger.exception("Failed to delete certificate file")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("profile"))

#delete post
@app.route('/delete-post/<int:post_id>')
def delete_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "delete from posts where post_id = %s and user_id = %s ",
        (post_id,session['user_id'])
    )

    connection.commit()
    cursor.close()
    connection.close()
    return redirect(url_for('dashboard'))



#  LIKE / UNLIKE 
@app.route("/like-post", methods=["POST"])
def like_post():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    post_id = request.form["post_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    # Check whether already liked
    query = """
        SELECT like_id
        FROM likes
        WHERE user_id = %s
        AND post_id = %s
    """

    cursor.execute(query, (user_id, post_id))

    like = cursor.fetchone()

    if like:

        # Unlike
        query = """
            DELETE FROM likes
            WHERE user_id = %s
            AND post_id = %s
        """

        cursor.execute(query, (user_id, post_id))

    else:

        # Like
        query = """
            INSERT INTO likes
            (user_id, post_id)
            VALUES (%s, %s)
        """

        cursor.execute(query, (user_id, post_id))

        # Get post owner's user_id
        query = """
            SELECT user_id
            FROM posts
            WHERE post_id = %s
        """

        cursor.execute(query, (post_id,))
        post = cursor.fetchone()

        if post:

            post_owner_id = post[0]

            # Don't notify yourself
            if post_owner_id != user_id:

                # Get liker name
                query = """
                    SELECT name
                    FROM users
                    WHERE id = %s
                """

                cursor.execute(query, (user_id,))
                user = cursor.fetchone()

                liker_name = user[0]

                # Notification message
                message = f"{liker_name} liked your post."

                query = """
                    INSERT INTO notifications
                    (user_id, sender_id, message)
                    VALUES (%s, %s, %s)
                """

                cursor.execute(
                    query,
                    (post_owner_id, user_id, message)
                )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("dashboard"))

# add comment
@app.route("/add-comment", methods=["POST"])
def add_comment():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    post_id = request.form["post_id"]
    comment = request.form["comment"]

    connection = get_db_connection()
    cursor = connection.cursor()

    # Add comment
    query = """
        INSERT INTO comments (user_id, post_id, comment)
        VALUES (%s, %s, %s)
    """

    cursor.execute(
        query,
        (user_id, post_id, comment)
    )

    # Get post owner
    query = """
        SELECT user_id
        FROM posts
        WHERE post_id = %s
    """

    cursor.execute(query, (post_id,))
    post = cursor.fetchone()

    if post:

        post_owner_id = post[0]

        # Don't notify yourself
        if post_owner_id != user_id:

            # Get commenter name
            query = """
                SELECT name
                FROM users
                WHERE id = %s
            """

            cursor.execute(query, (user_id,))
            user = cursor.fetchone()

            commenter_name = user[0]

            # Notification message
            message = f"{commenter_name} commented on your post."

            query = """
                INSERT INTO notifications
                (user_id, sender_id, message)
                VALUES (%s, %s, %s)
            """

            cursor.execute(
                query,
                (post_owner_id, user_id, message)
            )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("dashboard"))


# CREATE POST
@app.route("/create-post", methods=["POST"])
def create_post():

    if "user_id" not in session:
        return redirect(url_for("login"))

    content = request.form.get("content", "").strip()
    image = request.files.get("image")

    if not content:
        return redirect(url_for("dashboard"))

    image_filename = None

    if image and image.filename:
        safe_name = secure_filename(image.filename)
        extension = os.path.splitext(safe_name)[1]
        image_filename = str(uuid.uuid4()) + extension

        image.save(
            os.path.join(POST_UPLOAD_FOLDER, image_filename)
        )

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO posts (user_id, content, image)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            content,
            image_filename
        ))

        connection.commit()

    except Exception:
        connection.rollback()
        app.logger.exception("Create post failed")
        return "Post could not be created. Check the Flask terminal."

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("dashboard"))

#  EDIT PROFILE 
@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == "POST":

        about = request.form.get("about", "")
        education = request.form.get("education", "")
        skills = request.form.get("skills", "")
        experience = request.form.get("experience", "")

        photo = request.files.get("profile_photo")
        filename = None

        if photo and photo.filename:

            if not allowed_photo(photo.filename):
                cursor.close()
                connection.close()
                return "Only JPG, PNG and WEBP images are allowed.", 400

            extension = photo.filename.rsplit(".", 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{extension}"

            # Create correct file path
            saved_path = os.path.join(
                PROFILE_UPLOAD_FOLDER,
                filename
            )

            # Save image
            photo.save(saved_path)

        # Check if profile already exists for this user
        cursor.execute("""
            SELECT profile_id, profile_photo
            FROM profiles
            WHERE user_id = %s
            ORDER BY profile_id DESC
            LIMIT 1
        """, (user_id,))

        existing_profile = cursor.fetchone()

        if existing_profile:
            profile_id = existing_profile[0]
            current_photo = existing_profile[1]
            photo_to_save = filename if filename else current_photo

            cursor.execute("""
                UPDATE profiles
                SET about = %s, education = %s, skills = %s, experience = %s, profile_photo = %s
                WHERE profile_id = %s
            """, (about, education, skills, experience, photo_to_save, profile_id))

            # Clean up any duplicate legacy profile rows for this user
            cursor.execute("""
                DELETE FROM profiles
                WHERE user_id = %s AND profile_id != %s
            """, (user_id, profile_id))
        else:
            cursor.execute("""
                INSERT INTO profiles
                    (user_id, about, education, skills,
                     experience, profile_photo)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, about, education, skills, experience, filename))

        connection.commit()
        cursor.close()
        connection.close()

        return redirect(url_for("profile"))

    cursor.execute("""
        SELECT about, education, skills, experience
        FROM profiles
        WHERE user_id = %s
        ORDER BY profile_id DESC
        LIMIT 1
    """, (user_id,))

    profile = cursor.fetchone()

    cursor.close()
    connection.close()

    return render_template(
        "edit_profile.html",
        profile=profile
    )
# NOTIFICATIONS

@app.route("/notifications")
def notifications():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    # Normal notifications
    cursor.execute("""
        SELECT id, message, is_read, created_at
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))

    notifications = cursor.fetchall()

    # Connection requests
    cursor.execute("""
        SELECT
            c.id,
            u.name,
            c.created_at
        FROM connections c
        JOIN users u
        ON c.sender_id = u.id
        WHERE c.receiver_id = %s
        AND c.status = 'pending'
        ORDER BY c.created_at DESC
    """, (user_id,))

    connection_requests = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "notifications.html",
        notifications=notifications,
        connection_requests=connection_requests
    )

#search
@app.route("/search")
def search():

    if "user_id" not in session:
        return redirect(url_for("login"))

    search_text = request.args.get("q", "")

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        SELECT id, name, email
        FROM users
        WHERE name LIKE %s
        OR email LIKE %s
    """

    search_value = "%" + search_text + "%"

    cursor.execute(query, (search_value, search_value))
    users = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "search.html",
        users=users,
        search_text=search_text
    )

# VIEW OTHER USER PROFILE
@app.route("/user-profile/<int:user_id>")
def user_profile(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        SELECT
            u.id,
            u.name,
            p.about,
            p.education,
            p.skills,
            p.experience
        FROM users u
        LEFT JOIN profiles p
        ON u.id = p.user_id
        WHERE u.id = %s
    """

    cursor.execute(query, (user_id,))

    user_profile_data = cursor.fetchone()

    cursor.close()
    connection.close()

    if not user_profile_data:
        return "User not found"

    return render_template(
        "user_profile.html",
        user_profile=user_profile_data
    )

# CONNECT USER
@app.route("/connect/<int:user_id>", methods=["POST"])
def connect_user(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    sender_id = session["user_id"]

    # Cannot connect with yourself
    if sender_id == user_id:
        return redirect(url_for("user_profile", user_id=user_id))

    connection = get_db_connection()
    cursor = connection.cursor()

    # Check if request already exists
    cursor.execute("""
        SELECT id
        FROM connections
        WHERE sender_id = %s
        AND receiver_id = %s
    """, (sender_id, user_id))

    existing = cursor.fetchone()

    if not existing:

        # Create connection request
        cursor.execute("""
            INSERT INTO connections
            (sender_id, receiver_id, status)
            VALUES (%s, %s, 'pending')
        """, (sender_id, user_id))

        connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("user_profile", user_id=user_id))

# ACCEPT CONNECTION
@app.route("/accept-connection/<int:connection_id>", methods=["POST"])
def accept_connection(connection_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE connections
        SET status = 'accepted'
        WHERE id = %s
        AND receiver_id = %s
        AND status = 'pending'
    """, (connection_id, session["user_id"]))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("notifications"))

# REJECT CONNECTION
@app.route("/reject-connection/<int:connection_id>", methods=["POST"])
def reject_connection(connection_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE connections
        SET status = 'rejected'
        WHERE id = %s
        AND receiver_id = %s
        AND status = 'pending'
    """, (connection_id, session["user_id"]))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("notifications"))


@app.route("/add-job", methods=["GET", "POST"])
def add_job():

    if "user_id" not in session:
        return redirect(url_for("login"))
    role = session.get("role", "").strip().lower()

    if role not in ("recruiter", "company", "recruiter/company"):
        return "Access denied! Only recruiters can post jobs.", 403
    if request.method == "POST":

        title = request.form["title"]
        company = request.form["company"]
        location = request.form["location"]
        description = request.form["description"]
        job_type = request.form["job_type"]

        user_id = session["user_id"]

        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
            INSERT INTO jobs
            (title, company, location, description, job_type, user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """

        cursor.execute(query, (
            title,
            company,
            location,
            description,
            job_type,
            user_id
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("recruiter_dashboard"))

    return render_template("add_jobs.html")


@app.route("/job/<int:job_id>")
def job_details(job_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        SELECT *
        FROM jobs
        WHERE id = %s
    """

    cursor.execute(query, (job_id,))
    job = cursor.fetchone()

    cursor.close()
    connection.close()

    if not job:
        return "Job not found"

    return render_template("jobs_details.html", job=job)


@app.route("/jobs")
def jobs():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, title, company, location,
               description, job_type, created_at
        FROM jobs
        ORDER BY created_at DESC
    """)

    jobs = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "jobs.html",
        jobs=jobs,
        user_role=session.get("role")
    )


@app.route("/my-applications")
def my_applications():

    # Step 1: Login check
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Step 2: Only students allowed
    role = session.get("role", "").strip().lower()

    if role not in ("student", "job seeker", "student/job seeker"):
        return "Only students can view applications!", 403

    # Step 3: Get logged-in student
    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Step 4: Get student's applications
        cursor.execute("""
            SELECT jobs.title,
                   jobs.company,
                   jobs.location
            FROM applications
            JOIN jobs ON applications.job_id = jobs.id
            WHERE applications.user_id = %s
        """, (user_id,))

        applications = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "my_applications.html",
        applications=applications
    )


# Apply Job - Only Students
@app.route("/apply-job/<int:job_id>", methods=["POST"])
def apply_job(job_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please login first!"
        }), 401

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Step 1: Check user role from database
        cursor.execute("""
            SELECT role FROM users WHERE id = %s
        """, (user_id,))

        user = cursor.fetchone()

        if not user:
            return jsonify({
                "success": False,
                "message": "User not found!"
            }), 404

        role = (user[0] or "").strip().lower()

        # Only students can apply
        if role not in ("student", "job seeker", "student/job seeker"):
            return jsonify({
                "success": False,
                "message": "Only students can apply for jobs!"
            }), 403

        # Step 2: Check job exists
        cursor.execute("""
            SELECT user_id FROM jobs WHERE id = %s
        """, (job_id,))

        job = cursor.fetchone()

        if not job:
            return jsonify({
                "success": False,
                "message": "Job not found!"
            }), 404

        # Step 3: Prevent applying to own job
        if job[0] == user_id:
            return jsonify({
                "success": False,
                "message": "You cannot apply for your own job!"
            }), 403

        # Step 4: Check duplicate application
        cursor.execute("""
            SELECT id FROM applications
            WHERE job_id = %s AND user_id = %s
        """, (job_id, user_id))

        if cursor.fetchone():
            return jsonify({
                "success": False,
                "message": "You have already applied for this job!"
            })

        # Step 5: Submit application
        cursor.execute("""
            INSERT INTO applications (job_id, user_id)
            VALUES (%s, %s)
        """, (job_id, user_id))

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Application submitted successfully!"
        })

    finally:
        cursor.close()
        connection.close()


@app.route("/job-applicants/<int:job_id>")
def job_applicants(job_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    # Check that this job belongs to the logged-in recruiter
    cursor.execute("""
        SELECT id, title
        FROM jobs
        WHERE id = %s AND user_id = %s
    """, (job_id, user_id))

    job = cursor.fetchone()

    if not job:
        cursor.close()
        connection.close()
        return "Job not found or access denied."

    # Get students who applied   
    cursor.execute("""
    SELECT users.name,
           users.email,
           applications.status,
           applications.applied_at,
           applications.id,
           users.id
    FROM applications
    JOIN users ON applications.user_id = users.id
    WHERE applications.job_id = %s
    ORDER BY applications.applied_at DESC
    """, (job_id,))

    applicants = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "job_applicants.html",
        job=job,
        applicants=applicants
    )


# Update Application Status
@app.route("/update-application/<int:job_id>/<int:application_id>", methods=["POST"])
def update_application(job_id, application_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    status = request.form.get("status")

    if status not in ["Accepted", "Rejected"]:
        return "Invalid application status!"

    connection = get_db_connection()
    cursor = connection.cursor()

    # Check job ownership and update only its application
    cursor.execute("""
        UPDATE applications
        SET status = %s
        WHERE id = %s
        AND job_id = %s
        AND EXISTS (
            SELECT 1 FROM jobs
            WHERE jobs.id = applications.job_id
            AND jobs.user_id = %s
        )
    """, (status, application_id, job_id, session["user_id"]))

    updated = cursor.rowcount
    connection.commit()

    cursor.close()
    connection.close()

    if updated == 0:
        return "Application not found or access denied."

    return redirect(url_for("job_applicants", job_id=job_id))


# VIEW APPLICANT FULL PROFILE
@app.route("/applicant-profile/<int:job_id>/<int:student_id>")
def view_applicant_profile(job_id, student_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    # Only recruiters can view applicant profiles
    role = session.get("role", "").strip().lower()

    if role not in ("recruiter", "company", "recruiter/company"):
        return "Access denied! Only recruiters allowed.", 403

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Check job ownership and student application
        cursor.execute("""
            SELECT users.name, users.email
            FROM applications
            JOIN jobs
                ON applications.job_id = jobs.id
            JOIN users
                ON applications.user_id = users.id
            WHERE applications.job_id = %s
              AND applications.user_id = %s
              AND jobs.user_id = %s
        """, (job_id, student_id, session["user_id"]))

        applicant = cursor.fetchone()

        if not applicant:
            return "Applicant not found or access denied!", 403

        # Fetch student's complete profile
        cursor.execute("""
            SELECT about,
                   education,
                   skills,
                   experience,
                   profile_photo
            FROM profiles
            WHERE user_id = %s
            ORDER BY profile_id DESC
            LIMIT 1
        """, (student_id,))

        profile = cursor.fetchone()

        return render_template(
            "applicant_profile.html",
            applicant=applicant,
            profile=profile,
            job_id=job_id
        )

    finally:
        cursor.close()
        connection.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# RUN APP

if __name__ == "__main__":
    app.run(debug=True)