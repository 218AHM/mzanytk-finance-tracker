import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from datetime import datetime, timedelta
from collections import defaultdict
from werkzeug.security import check_password_hash, generate_password_hash

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True  # Set to True if using HTTPS

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Use environment variable for security
app.secret_key = os.environ.get("SECRET_KEY", "default_secret_key")

app.permanent_session_lifetime = timedelta(days=7)  # Session expires in 7 days


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
def index():
    if "username" in session:
        user_id = session["user_id"]
        username = session["username"]

        transactions = db.execute("SELECT category, amount, payment_method, date FROM transactions WHERE user_id = ? ORDER BY date DESC", user_id)

        total_amount = sum(transaction["amount"] for transaction in transactions)
        total_cash = sum(transaction["amount"]
                         for transaction in transactions if transaction["payment_method"] == "Cash")
        total_online = sum(transaction["amount"] for transaction in transactions if transaction["payment_method"] == "Online")
        expense_by_category_result = db.execute("SELECT category, SUM(amount) AS total FROM transactions WHERE user_id = ? GROUP BY category", user_id)
        expense_by_category = {row["category"]: row["total"] for row in expense_by_category_result} if expense_by_category_result else {}

        expense_by_payment_method_result = db.execute("SELECT payment_method, SUM(amount) AS total FROM transactions WHERE user_id = ? GROUP BY payment_method", user_id)
        expense_by_payment_method = {row["payment_method"]: row["total"] for row in expense_by_payment_method_result} if expense_by_payment_method_result else {}

        # Debugging - Check if the data is being fetched
        print("Expense by Category:", expense_by_category)
        print("Expense by Payment Method:", expense_by_payment_method)

        return render_template(
            "index.html",
            username=username,
            transactions=transactions,
            total_amount=total_amount,
            total_cash=total_cash,
            total_online=total_online,
            expense_by_category=expense_by_category,  # ✅ Always defined
            expense_by_payment_method=expense_by_payment_method  # ✅ Always defined
            )

    return render_template("login.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = db.execute("SELECT id, username, password FROM users WHERE username = ?", username)

        if user and check_password_hash(user[0]["password"], password):
            session.permanent = True  # Keep user logged in
            session["user_id"] = user[0]["id"]
            session["username"] = user[0]["username"]
            return redirect("/")
        else:
            flash("Invalid Username or Password. Please try again.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("user_id", None)
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_password = generate_password_hash(password)

        existing_user = db.execute("SELECT * FROM users WHERE username = ?", username)

        if existing_user:
            flash("Username already exists.", "error")
        else:
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                       username, hashed_password)
            flash("Registration successful! Please Log in.", "success")
            return redirect("/login")
    return render_template("register.html")


@app.route("/transactions")
def transactions():
    if "username" in session:
        user_id = session["user_id"]
        username = session["username"]

        transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", user_id)

        return render_template("transaction.html", transactions=transactions, username=username)

    return redirect("/login")


@app.route("/add_transaction", methods=["GET", "POST"])
def add_transaction():
    if "username" in session:
        user_id = session["user_id"]
        date = request.form["date"]
        category = request.form["category"]
        try:
            amount = float(request.form["amount"])
            if amount <= 0:
                flash("Amount must be positive.", "error")
                return redirect("/transactions")
        except ValueError:
            flash("Invalid amount format.", "error")
            return redirect("/transactions")

        payment_method = request.form["payment_method"]
        if payment_method not in ["Online", "Cash"]:
            flash("Invalid payment method.", "error")
            return redirect("/transactions")

        description = request.form["notes"].strip() if request.form["notes"] else ""

        try:
            date = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            flash("Invalid date format. Use YYYY-MM-DD.", "error")
            return redirect("/transactions")

        db.execute(
            "INSERT INTO transactions (user_id, date, category, amount, payment_method, description) VALUES (?, ?, ?, ?, ?, ?)",
            user_id, date, category, amount, payment_method, description
        )

        flash("Transaction added successfully!", "success")
        return redirect("/transactions")

    return redirect("/login")


@app.route("/delete_transaction/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    if "username" in session:
        db.execute("DELETE FROM transactions WHERE id = ?", transaction_id)
        flash("Transaction deleted successfully.", "success")
    else:
        flash("You must be logged in to delete a transaction.", "error")

    return redirect("/transactions")


@app.route("/daily_spending_data")
def daily_spending_data():
    if "username" in session:
        user_id = session["user_id"]

        # Fetch daily spending data from the database
        data = db.execute(
            "SELECT date, SUM(amount) AS total FROM transactions WHERE user_id = ? GROUP BY date", user_id)

        # Format data for Chart.js
        labels = [row["date"] for row in data]
        amounts = [row["total"] for row in data]

        return jsonify({"labels": labels, "amounts": amounts})

    return redirect("/login")


@app.route("/monthly_spending_data")
def monthly_spending_data():
    if "username" in session:
        user_id = session["user_id"]

        # Fetch monthly spending data from the database
        data = db.execute(
            "SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total FROM transactions WHERE user_id = ? GROUP BY month", user_id)

        # Format data for Chart.js
        labels = [datetime.strptime(row["month"], "%Y-%m").strftime("%b %Y") for row in data]
        amounts = [row["total"] for row in data]

        return jsonify({"labels": labels, "amounts": amounts})

    return redirect("/login")


@app.route("/statistics")
def statistics():
    if "user_id" in session:
        user_id = session["user_id"]
        username = session["username"]  # Retrieve the username from session

        total_expenses_result = db.execute("SELECT SUM(amount) AS total FROM transactions WHERE user_id = ?", user_id)
        total_expenses = total_expenses_result[0]["total"] if total_expenses_result and total_expenses_result[0]["total"] else 0

        expense_by_category_result = db.execute("SELECT category, SUM(amount) AS total FROM transactions WHERE user_id = ? GROUP BY category", user_id)
        expense_by_category = {row["category"]: row["total"] for row in expense_by_category_result}

        expense_by_payment_method_result = db.execute("SELECT payment_method, SUM(amount) AS total FROM transactions WHERE user_id = ? GROUP BY payment_method", user_id)
        expense_by_payment_method = {row["payment_method"]: row["total"] for row in expense_by_payment_method_result}


        return render_template('statistics.html',
                               username=username,  # Pass the username to the template
                               total_expenses=total_expenses,
                               expense_by_category=expense_by_category,
                               expense_by_payment_method=expense_by_payment_method)

    return redirect("/login")
