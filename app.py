
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
    db = sqlite3.connect(DATABASE, timeout=20)
    db.row_factory = sqlite3.Row
    return db


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

        # Add priority to an existing database without deleting records.
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
                amount REAL NOT NULL CHECK(amount >= 0)
            )
        """)


def transaction_dict(row):
    result = dict(row)
    if "priority" not in result:
        result["priority"] = "essential"
    return result


def get_transactions():
    with get_db() as db:
        rows = db.execute("""
            SELECT id, title, amount, type, category, date, priority
            FROM transactions
            ORDER BY date DESC, id DESC
        """).fetchall()

    return [transaction_dict(row) for row in rows]


def get_month_totals(month):
    with get_db() as db:
        row = db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN type = 'income'
                    THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN type = 'expense'
                    THEN amount ELSE 0 END), 0) AS expense,
                COALESCE(SUM(CASE WHEN type = 'expense'
                    AND priority = 'essential'
                    THEN amount ELSE 0 END), 0) AS essential,
                COALESCE(SUM(CASE WHEN type = 'expense'
                    AND priority = 'optional'
                    THEN amount ELSE 0 END), 0) AS optional
            FROM transactions
            WHERE substr(date, 1, 7) = ?
        """, (month,)).fetchone()

    return {
        "income": round(row["income"], 2),
        "expense": round(row["expense"], 2),
        "essential": round(row["essential"], 2),
        "optional": round(row["optional"], 2)
    }


@app.route("/")
def home():
    return jsonify({
        "message": "FinTrack Smart Money Advisor API is running!",
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
    priority = data.get("priority", "essential")

    if not isinstance(title, str) or not title.strip():
        return jsonify({"error": "Transaction title is required."}), 400

    title = title.strip()
    if len(title) > 100:
        return jsonify({"error": "Title must be 100 characters or fewer."}), 400

    if tx_type not in ("income", "expense"):
        return jsonify({"error": "Choose income or expense."}), 400

    allowed = INCOME_CATEGORIES if tx_type == "income" else EXPENSE_CATEGORIES
    if not isinstance(category, str) or category not in allowed:
        return jsonify({"error": "Invalid category for this transaction type."}), 400

    if priority not in ("essential", "optional"):
        return jsonify({"error": "Priority must be essential or optional."}), 400

    if tx_type == "income":
        priority = "essential"

    try:
        amount = Decimal(str(data.get("amount", "")))
        if (
            not amount.is_finite()
            or amount <= 0
            or amount > Decimal("1000000000")
        ):
            raise ValueError
        amount = float(amount)
    except (InvalidOperation, ValueError, TypeError):
        return jsonify({"error": "Enter a valid positive amount."}), 400

    try:
        parsed_date = date.fromisoformat(tx_date)
        if parsed_date.isoformat() != tx_date:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Use a valid YYYY-MM-DD date."}), 400

    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO transactions
                (title, amount, type, category, date, priority)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, amount, tx_type, category, tx_date, priority))

        row = db.execute("""
            SELECT id, title, amount, type, category, date, priority
            FROM transactions WHERE id = ?
        """, (cursor.lastrowid,)).fetchone()

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

    return jsonify({
        "total_income": income,
        "total_expense": expense,
        "balance": balance,
        "savings_rate": round(balance / income * 100, 1) if income else 0
    })


@app.route("/api/analytics/monthly")
def monthly_analytics():
    today = date.today()
    months = []

    year, month = today.year, today.month
    for _ in range(5):
        month -= 1
        if month == 0:
            month, year = 12, year - 1

    start = f"{year:04d}-{month:02d}-01"

    for _ in range(6):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month, year = 1, year + 1

    with get_db() as db:
        rows = db.execute("""
            SELECT substr(date, 1, 7) AS month,
                SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
            FROM transactions
            WHERE date >= ?
            GROUP BY substr(date, 1, 7)
        """, (start,)).fetchall()

    totals = {
        row["month"]: {
            "income": round(row["income"], 2),
            "expense": round(row["expense"], 2)
        }
        for row in rows
    }

    return jsonify({
        "months": [{
            "month": datetime.strptime(m, "%Y-%m").strftime("%b %y"),
            "income": totals.get(m, {}).get("income", 0),
            "expense": totals.get(m, {}).get("expense", 0)
        } for m in months]
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


@app.route("/api/budget", methods=["GET", "POST"])
def monthly_budget():
    month = request.args.get("month", date.today().strftime("%Y-%m"))

    try:
        if datetime.strptime(month, "%Y-%m").strftime("%Y-%m") != month:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Month must use YYYY-MM format."}), 400

    if request.method == "POST":
        data = request.get_json(silent=True) or {}

        try:
            amount = Decimal(str(data.get("amount", "")))
            if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
                raise ValueError
            amount = float(amount)
        except (InvalidOperation, ValueError, TypeError):
            return jsonify({"error": "Enter a valid non-negative budget."}), 400

        with get_db() as db:
            db.execute("""
                INSERT INTO budgets (month, amount) VALUES (?, ?)
                ON CONFLICT(month) DO UPDATE SET amount = excluded.amount
            """, (month, amount))

    with get_db() as db:
        row = db.execute(
            "SELECT amount FROM budgets WHERE month = ?", (month,)
        ).fetchone()

    return jsonify({
        "month": month,
        "budget": row["amount"] if row else 0
    })


@app.route("/api/advisor")
def smart_advisor():
    month = request.args.get("month", date.today().strftime("%Y-%m"))

    try:
        if datetime.strptime(month, "%Y-%m").strftime("%Y-%m") != month:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Month must use YYYY-MM format."}), 400

    try:
        emergency = Decimal(request.args.get("emergency", "0"))
        reserve = Decimal(request.args.get("reserve", "0"))

        if (
            not emergency.is_finite()
            or not reserve.is_finite()
            or emergency < 0
            or reserve < 0
            or emergency > Decimal("1000000000")
            or reserve > Decimal("1000000000")
        ):
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        return jsonify({"error": "Enter valid emergency and reserve amounts."}), 400

    totals = get_month_totals(month)
    current_balance = round(totals["income"] - totals["expense"], 2)
    after_emergency = round(current_balance - float(emergency), 2)
    after_reserve = round(after_emergency - float(reserve), 2)

    with get_db() as db:
        row = db.execute(
            "SELECT amount FROM budgets WHERE month = ?", (month,)
        ).fetchone()

        categories = db.execute("""
            SELECT category, SUM(amount) AS total
            FROM transactions
            WHERE type = 'expense' AND priority = 'optional'
                AND substr(date, 1, 7) = ?
            GROUP BY category
            ORDER BY total DESC
        """, (month,)).fetchall()

    budget = row["amount"] if row else 0
    remaining_budget = round(budget - totals["expense"], 2)
    alerts = []
    tips = []

    if totals["income"] == 0 and totals["expense"] > 0:
        alerts.append({
            "level": "warning",
            "title": "No income recorded",
            "message": "Expenses are recorded, but no income is recorded for this month. Add your income to improve the analysis."
        })

    if current_balance < 0:
        alerts.append({
            "level": "danger",
            "title": "Spending exceeds income",
            "message": f"Your recorded expenses exceed your recorded income by ₹{abs(current_balance):,.2f}."
        })
        tips.append(
            "Review optional purchases and upcoming bills. Avoid taking on new debt without checking repayment costs."
        )

    if budget > 0:
        used_percent = round(totals["expense"] / budget * 100, 1)

        if totals["expense"] > budget:
            alerts.append({
                "level": "danger",
                "title": "Monthly budget exceeded",
                "message": f"You have exceeded your ₹{budget:,.2f} budget by ₹{abs(remaining_budget):,.2f} ({used_percent}% used)."
            })
            tips.append(
                "Pause optional spending and review the largest expense categories before making new purchases."
            )
        elif used_percent >= 80:
            alerts.append({
                "level": "warning",
                "title": "Budget running low",
                "message": f"You have used {used_percent}% of your monthly budget. ₹{remaining_budget:,.2f} remains."
            })
            tips.append(
                "Keep the remaining budget for essential needs and delay non-urgent purchases."
            )
        else:
            tips.append(
                f"You have used {used_percent}% of your monthly budget. Your recorded spending is currently within the limit."
            )
    else:
        tips.append(
            "Set a monthly expense budget to receive budget-use percentages and overspending alerts."
        )

    if categories:
        top = categories[0]
        tips.append(
            f"Your largest optional-spending category is {top['category']} at ₹{top['total']:,.2f}. Review it for possible reductions."
        )

    if after_emergency < 0:
        alerts.append({
            "level": "danger",
            "title": "Emergency expense exceeds your balance",
            "message": f"This expense would leave a shortfall of ₹{abs(after_emergency):,.2f}, before reserved bills."
        })
        tips.append(
            "Check available emergency savings, whether the payment can be reduced or delayed, and what safe support options are available."
        )
    elif after_emergency < float(reserve):
        alerts.append({
            "level": "warning",
            "title": "Essential bills may be at risk",
            "message": f"After the emergency expense, ₹{after_emergency:,.2f} remains, below the ₹{float(reserve):,.2f} reserve you entered."
        })
        tips.append(
            "Protect essential bills first and review optional expenses before committing to further purchases."
        )
    else:
        tips.append(
            f"After the emergency expense and your stated reserve, ₹{after_reserve:,.2f} remains unreserved."
        )

    if not alerts:
        alerts.append({
            "level": "success",
            "title": "No immediate warning detected",
            "message": "Your recorded figures do not currently trigger the rules above. Keep recording transactions and review upcoming bills."
        })

    return jsonify({
        "month": month,
        "income": totals["income"],
        "expenses": totals["expense"],
        "essential_expenses": totals["essential"],
        "optional_expenses": totals["optional"],
        "balance": current_balance,
        "budget": budget,
        "remaining_budget": remaining_budget,
        "emergency_expense": float(emergency),
        "reserved_bills": float(reserve),
        "after_emergency": after_emergency,
        "after_reserve": after_reserve,
        "alerts": alerts,
        "tips": tips
    })


init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
