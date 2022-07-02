import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
uri = os.getenv("postgres://uiqriapemjrvop:c74dd67063fd2c937a0b7898f6d2eb9575bba312b2bf7a2195bd5c52c4aa3c0b@ec2-23-23-151-191.compute-1.amazonaws.com:5432/d670afivjtqfrf")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://")
db = SQL(uri)

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# HOMEPAGE


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]

    # Getting stock info from the db
    stocks_info = db.execute("SELECT symbol, shares FROM stock_owners WHERE owner_id = ?", user_id)

    # List of final stocks
    stocks = []
    Tvalue = 0

    for i in range(len(stocks_info)):
        stocks_results = {}

        symbol = stocks_info[i]["symbol"]
        shares = int(stocks_info[i]["shares"])

        results = lookup(symbol)
        price = results["price"]
        name = results["name"]
        total = price * shares
        Tvalue += total

        stocks_results["symbol"] = symbol
        stocks_results["shares"] = shares
        stocks_results["price"] = price
        stocks_results["name"] = name
        stocks_results["total"] = total

        stocks.append(stocks_results)

    # Calculating the summaries
    TOTALS = []
    Totals = {}

    Tshares = db.execute("SELECT SUM(shares) AS shares FROM stock_owners WHERE owner_id = ?", user_id)
    Tshares = Tshares[0]["shares"]
    balance = db.execute("SELECT cash FROM  users WHERE id = ?", user_id)
    balance = balance[0]["cash"]

    Totals["balance"] = balance
    Totals["Tshares"] = Tshares
    Totals["Tvalue"] = Tvalue

    TOTALS.append(Totals)

    return render_template("index.html", stocks=stocks, TOTALS=TOTALS)

# BUY


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        user_id = session["user_id"]
        buy = "buy"

        # Check if the symbol field is blank
        if not symbol:
            return apology("Missing symbol")

        # Check if the shares field is blank
        if not shares:
            return apology("Missing shares")

        # If the input contains non-letters
        if not symbol.isalpha():
            return apology("Invalid Symbol")
        else:
            symbol = symbol.upper()

        # Check if number is a digit
        if not shares.isdigit():
            return apology("You did not print an integer")
        else:
            shares = int(shares)

        # If user inputs a negative integer
        if shares <= 0:
            return apology("Invalid shares")

        # Lookup stocks with that symbol
        results = lookup(symbol)

        # Ensuring the symbol is in the stock market
        if results == None:
            return apology("Invalid symbol")
        else:
            price = results["price"]

            # Total amount of cash to be used
            total = price * shares

            # Getting cash from user
            cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
            cash = cash[0]["cash"]
            # Ensure they have the cash to buy shares
            if cash < total:
                return apology("Insufficient amount to purchase this stock")

            # Making the purchase
            bal = cash - total

            # Updating the cash balance of the user
            db.execute("UPDATE users SET cash = ? WHERE id = ?", bal, user_id)

            # Record the transaction
            db.execute("INSERT INTO transactions (user_id, symbol, transaction_amt, transaction_type, shares, date) VALUES(?, ?, ?, ?, ?, datetime('now', 'localtime'))",
                       user_id, symbol, total, buy, shares)

            # Check if the buyer has made any prior purchases
            buyer = db.execute("SELECT owner_id FROM stock_owners WHERE owner_id = ?", user_id)

            # If the user hasn't bought before add them, the stock info and purchase amount to the list
            if not buyer:
                db.execute("INSERT INTO stock_owners (owner_id, symbol, shares) VALUES(?, ?, ?)", user_id, symbol, shares)
            else:
                # If the user has that specific stock, update it's shares, otherwise add the shares and the stock
                value = db.execute("SELECT shares FROM stock_owners WHERE owner_id = ? and symbol = ?", user_id, symbol)
                if not value:
                    db.execute("INSERT INTO stock_owners (owner_id, symbol, shares) VALUES(?, ?, ?)", user_id, symbol, shares)
                else:
                    value = value[0]["shares"]
                    value += shares
                    db.execute("UPDATE stock_owners SET shares = ? WHERE symbol = ? AND owner_id = ?",  value, symbol, user_id)

            return redirect("/")

    else:
        return render_template("buy.html")

# HISTORY


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]

    # TRANSACTION HISTORY
    Ts_info = db.execute(
        "SELECT symbol, transaction_amt, transaction_type, shares, date FROM transactions WHERE user_id = ?", user_id)
    sales = []

    for i in range(len(Ts_info)):
        sell_results = {}

        symbol = Ts_info[i]["symbol"]
        amt = float(Ts_info[i]["transaction_amt"])
        shares = int(Ts_info[i]["shares"])
        transaction_type = Ts_info[i]["transaction_type"]
        date = Ts_info[i]["date"]
        results = lookup(symbol)
        name = results["name"]

        sell_results["symbol"] = symbol
        sell_results["name"] = name
        sell_results["amt"] = amt
        sell_results["shares"] = shares
        sell_results["Ts_type"] = transaction_type
        sell_results["date"] = date

        sales.append(sell_results)

    return render_template("history.html", sales=sales)

# LOGIN


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

# LOG OUT


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

# QUOTE


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Getting the symbol from the user
        symbol = request.form.get("symbol").upper()

        # Looking up the symbol for stocks
        results = lookup(symbol)

        if results != None:
            name = results.get("name")
            price = usd(results.get("price"))
            symbol = results["symbol"].upper()

            return render_template("quote.html", name=name, price=price, symbol=symbol, quote="none", quoted="block")
        else:
            return apology("Invalid symbol")
    else:
        return render_template("quote.html", quote="block", quoted="none")

# REGISTER


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensuring the fields are not blank
        if not username:
            return apology("Missing username")

        # Ensuring there is a password
        if not password or not confirmation:
            return apology("Missing password")

        # If password and apology don't match return error
        if password != confirmation:
            return apology("Passwords do not match")

        # Ensure password is atleast 6 characters
        if len(password) < 6:
            return apology("Password Length must be at least 6 characters long")

        # If username is already taken, return error
        name_check = db.execute("SELECT username FROM users WHERE username = ?", username)

        if not name_check:
            # Encrypt the password
            wordpass = generate_password_hash(password)
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, wordpass)

            # Query database for username
            rows = db.execute("SELECT * FROM users WHERE username = ?", username)

            # Remember which user has logged in
            session["user_id"] = rows[0]["id"]

            # Redirect user to home page
            return redirect("/")
        else:
            return apology("Username already taken, please try another one")
    else:
        return render_template("register.html")


# SELL


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # Check if the symbol field is blank
        if not symbol:
            return apology("Missing symbol")

        # Check if the shares field is blank
        if not shares:
            return apology("Missing shares")

        # Check if number is a digit
        if not shares.isdigit():
            return apology("You did not print an integer")
        else:
            shares = int(shares)

        # If user inputs a negative integer or zero
        if shares <= 0:
            return apology("Invalid shares")

        # If the shares input is greater than the shares in ownership, return an apology
        dbShares = db.execute("SELECT shares FROM stock_owners WHERE owner_id = ? AND symbol = ?", user_id, symbol)
        dbShares = dbShares[0]["shares"]

        if shares > dbShares:
            return apology("Too many shares")

        # Lookup stocks with that symbol
        results = lookup(symbol)

        price = results["price"]
        sell = "sell"

        # Total amount of cash to be gained
        total = price * shares

        # Getting cash from user
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = cash[0]["cash"]

        # Making the purchase
        summation = cash + total
        # Updating the cash balance of the user
        db.execute("UPDATE users SET cash = ? WHERE id = ?", summation, user_id)

        # Record the transaction
        db.execute("INSERT INTO transactions (user_id, symbol, transaction_amt, transaction_type, shares, date) VALUES(?, ?, ?, ?, ?, datetime('now', 'localtime'))",
                   user_id, symbol, total, sell, shares)

        # Update the stock owned
        original_shares = db.execute("SELECT shares FROM stock_owners WHERE owner_id = ? AND symbol = ?", user_id, symbol)
        original_shares = original_shares[0]["shares"]

        original_shares -= shares

        db.execute("UPDATE stock_owners SET shares = ? WHERE symbol = ? AND owner_id = ?",  original_shares, symbol, user_id)

        # Delete stocks that the user has 0 shares
        db.execute("DELETE FROM stock_owners WHERE shares = ?", 0)
        return redirect("/")
    else:
        symbols = db.execute("SELECT symbol FROM stock_owners WHERE owner_id = ?", user_id)
        return render_template("sell.html", user_id=user_id, symbols=symbols)

# Add cash


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    user_id = session["user_id"]
    if request.method == "POST":
        new_cash = float(request.form.get("cash"))

        # If number is not a positive integer
        if new_cash <= 0:
            return apology("Invalid input")

        # If cash exceeds limit, return apology
        if new_cash > 5000:
            return apology("Value has passed the max allowed")

        db_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        db_cash = db_cash[0]["cash"]
        db_cash += new_cash

        db.execute("UPDATE users SET cash = ? WHERE id = ?", db_cash, user_id)
        db.execute("INSERT INTO deposits (person_id, dep_amt, date) VALUES(?, ?, datetime('now', 'localtime'))", user_id, new_cash)
        return redirect("/")
    else:
        bal = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        bal = bal[0]["cash"]

        return render_template("add.html", bal=bal)

if __name__ == "__main__":
    app.run(debug=True)