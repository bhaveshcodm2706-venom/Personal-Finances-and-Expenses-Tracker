
import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATABASE = os.environ.get("DATABASE_PATH", "finance.db")

INCOME_CATEGORIES = {
    "Salary", "Business", "Investment", "Gift", "Other"
}

EXPENSE_CATEGORIES = {
    "Food", "Transport", "Shopping", "Bills", "Education",
    "Health", "Entertainment", "Other"
}


def get_db():
    connection = sqlite3.connect(DATABASE, timeout=20)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    folder = os.path.dirname(DATABASE)
    if folder:
        os.makedirs(folder, exist_ok=True)

    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
                category TEXT NOT NULL,
                date TEXT NOT NULL
            )
        """)


def transaction_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "amount": row["amount"],
        "type": row["type"],
        "category": row["category"],
        "date": row["date"]
    }


def get_transactions():
    with get_db() as db:
        rows = db.execute("""
            SELECT id, title, amount, type, category, date
            FROM transactions
            ORDER BY date DESC, id DESC
        """).fetchall()

    return [transaction_dict(row) for row in rows]


@app.route("/")
def home():
    return jsonify({
        "message": "FinTrack Python API is running!",
        "status": "online"
    })


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/transactions", methods=["GET"])
def list_transactions():
    return jsonify({"transactions": get_transactions()})


@app.route("/api/transactions", methods=["POST"])
def add_transaction():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A valid JSON object is required."}), 400

    title = data.get("title")
    category = data.get("category")
    tx_type = data.get("type")
    tx_date = data.get("date")

    if not isinstance(title, str) or not title.strip():
        return jsonify({"error": "Transaction title is required."}), 400

    title = title.strip()
    if len(title) > 100:
        return jsonify({"error": "Title must be 100 characters or fewer."}), 400

    if tx_type not in ("income", "expense"):
        return jsonify({"error": "Type must be income or expense."}), 400

    allowed_categories = (
        INCOME_CATEGORIES if tx_type == "income"
        else EXPENSE_CATEGORIES
    )

    if not isinstance(category, str) or category not in allowed_categories:
        return jsonify({"error": "Invalid category for this transaction type."}), 400

    try:
        amount = Decimal(str(data.get("amount", "")))
        if not amount.is_finite() or amount <= 0 or amount > Decimal("1000000000"):
            raise ValueError
        amount = float(amount)
    except (InvalidOperation, ValueError, TypeError):
        return jsonify({"error": "Enter a valid positive amount."}), 400

    try:
        parsed_date = date.fromisoformat(tx_date)
        if parsed_date.isoformat() != tx_date:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Use a valid date in YYYY-MM-DD format."}), 400

    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO transactions (title, amount, type, category, date)
            VALUES (?, ?, ?, ?, ?)
        """, (title, amount, tx_type, category, tx_date))

        new_id = cursor.lastrowid

        row = db.execute("""
            SELECT id, title, amount, type, category, date
            FROM transactions WHERE id = ?
        """, (new_id,)).fetchone()

    return jsonify({
        "message": "Transaction added successfully.",
        "transaction": transaction_dict(row)
    }), 201


@app.route("/api/transactions/<int:transaction_id>", methods=["DELETE"])
def delete_transaction(transaction_id):
    with get_db() as db:
        cursor = db.execute(
            "DELETE FROM transactions WHERE id = ?",
            (transaction_id,)
        )

    if cursor.rowcount == 0:
        return jsonify({"error": "Transaction not found."}), 404

    return jsonify({"message": "Transaction deleted successfully."})


@app.route("/api/summary")
def summary():
    with get_db() as db:
        row = db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN type = 'income'
                    THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN type = 'expense'
                    THEN amount ELSE 0 END), 0) AS expense
            FROM transactions
        """).fetchone()

    income = round(row["income"], 2)
    expense = round(row["expense"], 2)
    balance = round(income - expense, 2)

    savings_rate = (
        round((balance / income) * 100, 1) if income > 0 else 0
    )

    return jsonify({
        "total_income": income,
        "total_expense": expense,
        "balance": balance,
        "savings_rate": savings_rate
    })


@app.route("/api/analytics/monthly")
def monthly_analytics():
    # Show the current month and the five previous months.
    today = date.today()
    months = []

    year = today.year
    month = today.month

    for _ in range(5):
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    start_year, start_month = year, month

    for _ in range(6):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1

    start_date = f"{start_year:04d}-{start_month:02d}-01"

    with get_db() as db:
        rows = db.execute("""
            SELECT substr(date, 1, 7) AS month,
                SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
            FROM transactions
            WHERE date >= ?
            GROUP BY substr(date, 1, 7)
        """, (start_date,)).fetchall()

    totals = {
        row["month"]: {
            "income": round(row["income"], 2),
            "expense": round(row["expense"], 2)
        }
        for row in rows
    }

    return jsonify({
        "months": [
            {
                "month": datetime.strptime(m, "%Y-%m").strftime("%b %y"),
                "income": totals.get(m, {}).get("income", 0),
                "expense": totals.get(m, {}).get("expense", 0)
            }
            for m in months
        ]
    })


@app.route("/api/analytics/categories")
def category_analytics():
    with get_db() as db:
        rows = db.execute("""
            SELECT category, ROUND(SUM(amount), 2) AS total
            FROM transactions
            WHERE type = 'expense'
            GROUP BY category
            ORDER BY total DESC
        """).fetchall()

    return jsonify({
        "categories": [
            {"category": row["category"], "total": row["total"]}
            for row in rows
        ]
    })


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
