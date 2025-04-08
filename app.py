import os
import psycopg2
import urllib.parse
import psycopg2.extras

from flask import Flask, flash, redirect, render_template, request, session, g
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, apology1

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/")
@login_required
def index():
    userid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT company, symbol, quantity FROM portfolio WHERE userid = %s", (userid,))
    rows = cur.fetchall()
    cur.execute("SELECT cash FROM users WHERE id = %s", (userid,))
    cash = cur.fetchone()["cash"]
    cur.close()
    conn.close()
    return render_template("layout.html", rows=rows, lookup=lookup, cash=cash)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        try:
            qty = float(request.form.get("shares"))
            if (qty % 1) > 0 or qty < 1:
                return apology("Not a valid quantity")
        except:
            return apology("Invalid quantity")

        buy = request.form.get("symbol")
        temp = lookup(buy)
        if temp:
            name = temp["name"]
            price = temp["price"]
            buy = temp["symbol"]
            userid = session["user_id"]

            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT cash FROM users WHERE id = %s", (userid,))
            cash = cur.fetchone()["cash"]
            total = price * qty

            if cash < total:
                cur.close()
                conn.close()
                return apology("not enough money")

            cur.execute("UPDATE portfolio SET quantity = quantity + %s WHERE userid = %s AND symbol = %s", (qty, userid, buy))
            if cur.rowcount == 0:
                cur.execute("INSERT INTO portfolio (userid, company, symbol, quantity) VALUES (%s, %s, %s, %s)", (userid, name, buy, qty))
            cur.execute("UPDATE users SET cash = cash - %s WHERE id = %s", (total, userid))
            cur.execute("INSERT INTO logs (userid, company, symbol, price, quantity, type) VALUES (%s, %s, %s, %s, %s, 'buy')", (userid, name, buy, price, qty))
            conn.commit()
            cur.close()
            conn.close()
            return redirect("/")
        else:
            return apology("Stock does not exist!")
    return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    userid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT type, symbol, price, quantity, time FROM logs WHERE userid = %s", (userid,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("history.html", rows=rows)

@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username:
            return apology("must provide username", 403)
        elif not password:
            return apology("must provide password", 403)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], password):
            return apology("invalid username and/or password", 403)

        session["user_id"] = rows[0]["id"]
        flash("Login successful!")
        return redirect("/")
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        temp = lookup(symbol)
        if temp:
            name = temp["name"]
            price = usd(temp["price"])
            symbol = temp["symbol"]
            return render_template("quoted.html", name=name, price=price, symbol=symbol)
        else:
            return apology("Stock does not exist!")
    return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if password != confirmation:
            return apology("Passwords do not match!")
        elif not username.strip() or not password.strip():
            return apology("Field cannot be blank!")

        hashed = generate_password_hash(password)

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, hash) VALUES (%s, %s)", (username, hashed))
            conn.commit()
            cur.close()
            conn.close()
            flash("You have successfully registered!")
            return redirect("/")
        except:
            return apology("Duplicate username")
    return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    userid = session["user_id"]
    if request.method == "POST":
        try:
            qty = float(request.form.get("shares"))
            if (qty % 1) > 0 or qty < 1:
                return apology("Not a valid quantity")
        except:
            return apology("Invalid quantity")

        sell = request.form.get("symbol")
        if sell == "select":
            return apology("Please select a stock")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT quantity FROM portfolio WHERE symbol = %s AND userid = %s", (sell, userid))
        curr = cur.fetchone()
        if not curr or qty > curr["quantity"]:
            cur.close()
            conn.close()
            return apology("Not a valid quantity")

        temp = lookup(sell)
        if temp:
            name = temp["name"]
            price = temp["price"]
            sell = temp["symbol"]
            total = price * qty
            cur.execute("UPDATE portfolio SET quantity = quantity - %s WHERE userid = %s AND symbol = %s", (qty, userid, sell))
            cur.execute("DELETE FROM portfolio WHERE quantity = 0")
            cur.execute("INSERT INTO logs (userid, company, symbol, price, quantity, type) VALUES (%s, %s, %s, %s, %s, 'sell')", (userid, name, sell, price, qty))
            cur.execute("UPDATE users SET cash = cash + %s WHERE id = %s", (total, userid))
            conn.commit()
            cur.close()
            conn.close()
            return redirect("/")
        else:
            return apology("Stock does not exist!")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM portfolio WHERE userid = %s", (userid,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("sell.html", rows=rows)

@app.route("/meme", methods=["GET", "POST"])
def meme():
    if request.method == "POST":
        top = request.form.get("top")
        bottom = request.form.get("bottom")
        return apology1(top, bottom)
    return render_template("meme.html")

@app.route("/topup", methods=["GET", "POST"])
def topup():
    if request.method == "POST":
        userid = session["user_id"]
        cash = request.form.get("cash")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET cash = cash + %s WHERE id = %s", (cash, userid))
        conn.commit()
        cur.close()
        conn.close()
        return redirect("/")
    return render_template("topup.html")

if __name__ == "__main__":
    # Make sure the app runs on all network interfaces and on the specified port
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))