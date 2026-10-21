
import os
import sqlite3
import math
from datetime import date, datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATABASE_PATH = os.environ.get("DATABASE_PATH", "finance.db")

INCOME_CATEGORIES = {
    "Salary", "Business", "Investment", "Gift"
}

EXPENSE_CATEGORIES = {
    "Food", "Transport", "Shopping", "Bills",
    "Education", "Health", "Entertainment", "Other"
}


def connect_db():
    db = sqlite3.connect(DATABASE_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'essential'
            )
        """)

        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(transactions)")
        }

        if "priority" not in columns:
            db.execute("""
                ALTER TABLE transactions
                ADD COLUMN priority TEXT NOT NULL DEFAULT 'essential'
            """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                month TEXT PRIMARY KEY,
                amount REAL NOT NULL
            )
        """)


def valid_month(value):
    try:
        datetime.strptime(value, "%Y-%m")
        return True
    except (ValueError, TypeError):
        return False


def get_month_totals(month):
    with connect_db() as db:
        row = db.execute("""
            SELECT
                COALESCE(SUM(CASE
                    WHEN type = 'income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE
                    WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS expenses,
                COALESCE(SUM(CASE
                    WHEN type = 'expense' AND priority = 'essential'
                    THEN amount ELSE 0 END), 0) AS essential,
                COALESCE(SUM(CASE
                    WHEN type = 'expense' AND priority = 'optional'
                    THEN amount ELSE 0 END), 0) AS optional
            FROM transactions
            WHERE substr(date, 1, 7) = ?
        """, (month,)).fetchone()

    income = float(row["income"])
    expenses = float(row["expenses"])

    return {
        "income": income,
        "expenses": expenses,
        "essential": float(row["essential"]),
        "optional": float(row["optional"]),
        "balance": income - expenses
    }


def get_budget(month):
    with connect_db() as db:
        row = db.execute(
            "SELECT amount FROM budgets WHERE month = ?", (month,)
        ).fetchone()

    return float(row["amount"]) if row else 0.0


@app.get("/")
def home():
    return jsonify({
        "message": "FinTrack Smart Money Advisor API",
        "status": "running"
    })


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/transactions", methods=["GET", "POST"])
def transactions_api():
    if request.method == "GET":
        with connect_db() as db:
            rows = db.execute("""
                SELECT * FROM transactions
                ORDER BY date DESC, id DESC
            """).fetchall()

        return jsonify({"transactions": [dict(row) for row in rows]})

    data = request.get_json(silent=True) or {}

    title = str(data.get("title", "")).strip()
    category = str(data.get("category", "")).strip()
    transaction_type = str(data.get("type", "")).strip().lower()
    priority = str(data.get("priority", "essential")).strip().lower()
    raw_amount = data.get("amount")
    transaction_date = str(data.get("date", "")).strip()

    if not title or len(title) > 100:
        return jsonify({"error": "Enter a title up to 100 characters."}), 400

    if transaction_type not in {"income", "expense"}:
        return jsonify({"error": "Type must be income or expense."}), 400

    allowed_categories = (
        INCOME_CATEGORIES | EXPENSE_CATEGORIES
    )

    if category not in allowed_categories:
        return jsonify({"error": "Choose a valid category."}), 400

    if transaction_type == "income" and category not in INCOME_CATEGORIES:
        return jsonify({"error": "Choose an income category."}), 400

    if transaction_type == "expense" and category not in EXPENSE_CATEGORIES:
        return jsonify({"error": "Choose an expense category."}), 400

    if priority not in {"essential", "optional"}:
        return jsonify({"error": "Invalid expense priority."}), 400

    if transaction_type == "income":
        priority = "essential"

    try:
        amount = float(raw_amount)
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid amount."}), 400

    if not math.isfinite(amount) or not 0 < amount <= 1_000_000_000:
        return jsonify({"error": "Amount must be greater than zero and within the limit."}), 400

    try:
        parsed_date = date.fromisoformat(transaction_date)
        if parsed_date.isoformat() != transaction_date:
            raise ValueError()
    except ValueError:
        return jsonify({"error": "Enter a valid date in YYYY-MM-DD format."}), 400

    with connect_db() as db:
        cursor = db.execute("""
            INSERT INTO transactions
                (title, amount, type, category, date, priority)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title, amount, transaction_type,
            category, transaction_date, priority
        ))

        row = db.execute(
            "SELECT * FROM transactions WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()

    return jsonify(dict(row)), 201


@app.route("/api/transactions/<int:transaction_id>", methods=["DELETE"])
def delete_transaction(transaction_id):
    with connect_db() as db:
        cursor = db.execute(
            "DELETE FROM transactions WHERE id = ?",
            (transaction_id,)
        )

    if cursor.rowcount == 0:
        return jsonify({"error": "Transaction not found."}), 404

    return jsonify({"message": "Transaction deleted successfully."})


@app.get("/api/summary")
def summary():
    with connect_db() as db:
        row = db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expenses
            FROM transactions
        """).fetchone()

    income = float(row["income"])
    expenses = float(row["expenses"])
    balance = income - expenses
    savings_rate = ((balance / income) * 100) if income > 0 else 0

    return jsonify({
        "total_income": income,
        "total_expense": expenses,
        "balance": balance,
        "savings_rate": round(savings_rate, 2)
    })


@app.get("/api/analytics/monthly")
def monthly_analytics():
    with connect_db() as db:
        rows = db.execute("""
            SELECT
                substr(date, 1, 7) AS month,
                SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense
            FROM transactions
            GROUP BY substr(date, 1, 7)
            ORDER BY month DESC
            LIMIT 6
        """).fetchall()

    return jsonify([
        {
            "month": row["month"],
            "income": float(row["income"] or 0),
            "expense": float(row["expense"] or 0)
        }
        for row in reversed(rows)
    ])


@app.get("/api/analytics/categories")
def category_analytics():
    with connect_db() as db:
        rows = db.execute("""
            SELECT category, SUM(amount) AS total
            FROM transactions
            WHERE type = 'expense'
            GROUP BY category
            ORDER BY total DESC
        """).fetchall()

    return jsonify([
        {"category": row["category"], "total": float(row["total"])}
        for row in rows
    ])


@app.route("/api/budget", methods=["GET", "POST"])
def budget_api():
    month = request.args.get("month", date.today().strftime("%Y-%m"))

    if not valid_month(month):
        return jsonify({"error": "Month must use YYYY-MM format."}), 400

    if request.method == "GET":
        return jsonify({"month": month, "amount": get_budget(month)})

    data = request.get_json(silent=True) or {}

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid budget amount."}), 400

    if not math.isfinite(amount) or not 0 < amount <= 1_000_000_000:
        return jsonify({"error": "Budget must be greater than zero and within the limit."}), 400

    with connect_db() as db:
        db.execute("""
            INSERT INTO budgets (month, amount)
            VALUES (?, ?)
            ON CONFLICT(month) DO UPDATE SET amount = excluded.amount
        """, (month, amount))

    return jsonify({"month": month, "amount": amount})


@app.get("/api/advisor")
def advisor():
    month = request.args.get("month", date.today().strftime("%Y-%m"))

    if not valid_month(month):
        return jsonify({"error": "Month must use YYYY-MM format."}), 400

    try:
        emergency = float(request.args.get("emergency", "0"))
        reserve = float(request.args.get("reserve", "0"))
    except (TypeError, ValueError):
        return jsonify({"error": "Emergency and reserve amounts must be numbers."}), 400

    if (
        not math.isfinite(emergency) or not math.isfinite(reserve)
        or emergency < 0 or reserve < 0
        or emergency > 1_000_000_000 or reserve > 1_000_000_000
    ):
        return jsonify({"error": "Enter valid non-negative amounts within the limit."}), 400

    totals = get_month_totals(month)
    budget = get_budget(month)
    income = totals["income"]
    expenses = totals["expenses"]
    balance = totals["balance"]
    optional = totals["optional"]

    after_emergency = balance - emergency
    after_reserve = after_emergency - reserve

    alerts = []
    tips = []

    if income == 0:
        alerts.append({
            "level": "warning",
            "message": "No income is recorded for this month. Add your income for a more accurate report."
        })
        tips.append("Record all income before making a spending plan.")

    if balance < 0:
        alerts.append({
            "level": "danger",
            "message": "Your recorded expenses exceed your recorded income."
        })
        tips.append("Pause non-essential purchases and review your recent expenses.")

    if budget > 0:
        percentage = expenses / budget * 100

        if percentage >= 100:
            alerts.append({
                "level": "danger",
                "message": f"You have exceeded your monthly budget by ₹{expenses - budget:,.2f}."
            })
            tips.append("Avoid optional spending until you have reviewed your remaining needs.")
        elif percentage >= 80:
            alerts.append({
                "level": "warning",
                "message": f"You have used {percentage:.1f}% of your monthly budget."
            })
            tips.append("You are approaching your budget limit. Prioritize essential purchases.")
        else:
            tips.append(f"You have ₹{budget - expenses:,.2f} remaining in your monthly budget.")
    else:
        tips.append("Set a monthly budget to receive more useful overspending alerts.")

    if optional > 0:
        tips.append(f"Review your optional expenses, currently ₹{optional:,.2f}, to find possible savings.")

    if emergency > 0:
        if after_emergency < 0:
            alerts.append({
                "level": "danger",
                "message": "Your recorded monthly balance would not cover the unexpected expense."
            })
        else:
            alerts.append({
                "level": "success",
                "message": f"After this unexpected expense, the estimated amount left is ₹{after_emergency:,.2f}, before reserved bills."
            })

    if reserve > 0 and after_reserve < 0:
        alerts.append({
            "level": "danger",
            "message": "The emergency expense and reserved bills together exceed your recorded monthly balance."
        })
        tips.append("Check whether the expense can be delayed or paid in installments, if appropriate.")
    elif reserve > 0:
        tips.append(f"After the emergency expense and reserved bills, the estimate is ₹{after_reserve:,.2f}.")

    if balance > 0 and income > 0:
        tips.append("Consider setting aside part of your remaining income for savings and emergencies.")

    if not alerts:
        alerts.append({
            "level": "success",
            "message": "No immediate budget warning based on the information recorded."
        })

    return jsonify({
        "month": month,
        "income": income,
        "expenses": expenses,
        "essential_expenses": totals["essential"],
        "optional_expenses": optional,
        "balance": balance,
        "budget": budget,
        "remaining_budget": budget - expenses if budget else None,
        "emergency_expense": emergency,
        "reserved_bills": reserve,
        "after_emergency": after_emergency,
        "after_reserve": after_reserve,
        "alerts": alerts,
        "tips": tips
    })


init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
