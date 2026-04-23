from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from collections import defaultdict
from functools import wraps
from security import (
    record_failed_login, is_ip_blocked, clear_failed_logins,
    record_unauthorized_access, check_suspicious_payment
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "spiltwise_secret_2024")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///spiltwise.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# ── Models ────────────────────────────────────────────────────────────────────

expense_members = db.Table(
    "expense_members",
    db.Column("expense_id", db.Integer, db.ForeignKey("expense.id"), primary_key=True),
    db.Column("user_id",    db.Integer, db.ForeignKey("user.id"),    primary_key=True),
)

expense_settled = db.Table(
    "expense_settled",
    db.Column("expense_id", db.Integer, db.ForeignKey("expense.id"), primary_key=True),
    db.Column("user_id",    db.Integer, db.ForeignKey("user.id"),    primary_key=True),
)


class User(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(120), nullable=False)
    email        = db.Column(db.String(120), unique=True, nullable=False)
    password     = db.Column(db.String(256), nullable=False)
    avatar_color = db.Column(db.String(20), default="#4ECDC4")
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    wallet       = db.relationship("Wallet", back_populates="user", uselist=False)


class Expense(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(256), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    category    = db.Column(db.String(80), default="General")
    split_type  = db.Column(db.String(20), default="equal")
    paid_by     = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    payer       = db.relationship("User", foreign_keys=[paid_by])
    members     = db.relationship("User", secondary=expense_members, backref="expenses")
    settled     = db.relationship("User", secondary=expense_settled)
    splits      = db.relationship("ExpenseSplit", back_populates="expense", cascade="all, delete-orphan")


class ExpenseSplit(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("expense.id"), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"),    nullable=False)
    amount     = db.Column(db.Float, nullable=False)

    expense    = db.relationship("Expense", back_populates="splits")
    user       = db.relationship("User")


class Payment(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    from_user  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    to_user    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    note       = db.Column(db.String(256), default="Payment")
    status     = db.Column(db.String(20), default="completed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender     = db.relationship("User", foreign_keys=[from_user])
    receiver   = db.relationship("User", foreign_keys=[to_user])


class Wallet(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    balance = db.Column(db.Float, default=0.0)

    user    = db.relationship("User", back_populates="wallet")


# ── Helpers ───────────────────────────────────────────────────────────────────

app.jinja_env.globals["enumerate"] = enumerate
app.jinja_env.globals["get_current_user"] = lambda: get_current_user()
app.jinja_env.globals["session"] = session


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            ip = request.remote_addr
            record_unauthorized_access(ip, request.path, request.method)
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None


def _pick_color(email):
    colors = ["#FF6B6B","#4ECDC4","#45B7D1","#96CEB4","#FFEAA7","#DDA0DD","#98D8C8","#F7DC6F","#BB8FCE","#85C1E9"]
    return colors[sum(ord(c) for c in email) % len(colors)]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or not password:
            flash("All fields are required.", "error")
            return render_template("signup.html")
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return render_template("signup.html")
        hashed = bcrypt.generate_password_hash(password).decode("utf-8")
        user = User(name=name, email=email, password=hashed, avatar_color=_pick_color(email))
        db.session.add(user)
        db.session.flush()
        wallet = Wallet(user_id=user.id, balance=0.0)
        db.session.add(wallet)
        db.session.commit()
        session["user_id"]   = user.id
        session["user_name"] = user.name
        flash("Welcome to Spiltwise!", "success")
        return redirect(url_for("dashboard"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip       = request.remote_addr
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if is_ip_blocked(ip):
            flash("Too many failed attempts. Please try again later.", "error")
            return render_template("login.html")

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            clear_failed_logins(ip)
            session["user_id"]   = user.id
            session["user_name"] = user.name
            return redirect(url_for("dashboard"))

        record_failed_login(ip, email)
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    user       = get_current_user()
    uid        = session["user_id"]
    balances   = _compute_balances(uid)
    total_owed = sum(v for v in balances.values() if v > 0)
    total_owe  = sum(-v for v in balances.values() if v < 0)
    recent_expenses = (Expense.query
                       .filter(Expense.members.any(id=uid))
                       .order_by(Expense.created_at.desc())
                       .limit(5).all())
    wallet     = Wallet.query.filter_by(user_id=uid).first() or Wallet(balance=0)
    monthly    = _monthly_spending(uid)
    categories = _category_breakdown(uid)
    partners   = _top_partners(uid)
    all_users  = {u.id: u for u in User.query.all()}
    return render_template("dashboard.html",
        user=user, balances=balances, total_owed=total_owed,
        total_owe=total_owe, recent_expenses=recent_expenses,
        wallet=wallet, monthly=monthly, categories=categories,
        partners=partners, all_users=all_users)


@app.route("/expenses")
@login_required
def expenses():
    uid           = session["user_id"]
    user_expenses = (Expense.query
                     .filter(Expense.members.any(id=uid))
                     .order_by(Expense.created_at.desc()).all())
    all_users     = User.query.all()
    return render_template("expenses.html", expenses=user_expenses,
                           all_users=all_users, uid=uid)


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        uid        = session["user_id"]
        desc       = request.form.get("description", "").strip()
        amount     = float(request.form.get("amount", 0))
        category   = request.form.get("category", "General")
        split_type = request.form.get("split_type", "equal")
        member_ids = list(set(int(m) for m in request.form.getlist("members")))
        paid_by    = int(request.form.get("paid_by", uid))
        if uid not in member_ids:
            member_ids.append(uid)
        members = User.query.filter(User.id.in_(member_ids)).all()
        expense = Expense(
            description=desc, amount=amount, category=category,
            split_type=split_type, paid_by=paid_by,
            members=members
        )
        db.session.add(expense)
        db.session.flush()
        if split_type == "equal":
            per_person = round(amount / len(member_ids), 2)
            for mid in member_ids:
                db.session.add(ExpenseSplit(expense_id=expense.id, user_id=mid, amount=per_person))
        else:
            for mid in member_ids:
                val = float(request.form.get(f"custom_{mid}", 0))
                db.session.add(ExpenseSplit(expense_id=expense.id, user_id=mid, amount=val))
        db.session.commit()
        flash("Expense added!", "success")
        return redirect(url_for("expenses"))
    all_users = User.query.all()
    return render_template("add_expense.html", all_users=all_users, uid=session["user_id"])


@app.route("/expenses/<int:expense_id>/settle", methods=["POST"])
@login_required
def settle_expense(expense_id):
    uid     = session["user_id"]
    expense = Expense.query.get_or_404(expense_id)
    user    = User.query.get(uid)
    if user not in expense.settled:
        expense.settled.append(user)
        db.session.commit()
    return jsonify({"success": True})


@app.route("/balances")
@login_required
def balances():
    uid        = session["user_id"]
    bal        = _compute_balances(uid)
    simplified = _simplify_debts(uid)
    all_users  = {u.id: u for u in User.query.all()}
    return render_template("balances.html", balances=bal, simplified=simplified, all_users=all_users)


@app.route("/payments")
@login_required
def payments():
    uid         = session["user_id"]
    my_payments = (Payment.query
                   .filter((Payment.from_user == uid) | (Payment.to_user == uid))
                   .order_by(Payment.created_at.desc()).all())
    all_users   = {u.id: u for u in User.query.all()}
    return render_template("payments.html", payments=my_payments, all_users=all_users)


@app.route("/payments/send", methods=["POST"])
@login_required
def send_payment():
    uid     = session["user_id"]
    to_user = int(request.form.get("to_user"))
    amount  = float(request.form.get("amount", 0))
    note    = request.form.get("note", "Payment")
    if amount <= 0:
        flash("Invalid amount.", "error")
        return redirect(url_for("balances"))
    if check_suspicious_payment(uid, amount, to_user):
        flash("Transaction blocked: amount exceeds allowed limit.", "error")
        return redirect(url_for("balances"))
    db.session.add(Payment(from_user=uid, to_user=to_user, amount=amount, note=note, status="completed"))
    sender   = Wallet.query.filter_by(user_id=uid).first()
    receiver = Wallet.query.filter_by(user_id=to_user).first()
    if sender:
        sender.balance -= amount
    if receiver:
        receiver.balance += amount
    db.session.commit()
    flash(f"Payment of ${amount:.2f} sent!", "success")
    return redirect(url_for("balances"))


@app.route("/wallet")
@login_required
def wallet():
    uid       = session["user_id"]
    w         = Wallet.query.filter_by(user_id=uid).first() or Wallet(balance=0)
    history   = (Payment.query
                 .filter((Payment.from_user == uid) | (Payment.to_user == uid))
                 .order_by(Payment.created_at.desc()).limit(20).all())
    all_users = {u.id: u for u in User.query.all()}
    return render_template("wallet.html", wallet=w, history=history, all_users=all_users)


@app.route("/wallet/topup", methods=["POST"])
@login_required
def topup_wallet():
    uid    = session["user_id"]
    amount = float(request.form.get("amount", 0))
    if amount <= 0:
        flash("Enter valid amount.", "error")
        return redirect(url_for("wallet"))
    wallet = Wallet.query.filter_by(user_id=uid).first()
    if wallet:
        wallet.balance += amount
    db.session.add(Payment(from_user=None, to_user=uid, amount=amount, note="Wallet Top-up", status="completed"))
    db.session.commit()
    flash(f"${amount:.2f} added to wallet!", "success")
    return redirect(url_for("wallet"))


@app.route("/api/users/search")
@login_required
def search_users():
    q   = request.args.get("q", "").strip()
    uid = session["user_id"]
    if not q:
        return jsonify([])
    results = (User.query
               .filter(User.id != uid)
               .filter((User.name.ilike(f"%{q}%")) | (User.email.ilike(f"%{q}%")))
               .limit(5).all())
    return jsonify([{"id": u.id, "name": u.name, "email": u.email,
                     "color": u.avatar_color} for u in results])


# ── Business logic ────────────────────────────────────────────────────────────

def _compute_balances(uid):
    balances      = defaultdict(float)
    user_expenses = Expense.query.filter(Expense.members.any(id=uid)).all()
    for exp in user_expenses:
        paid_by     = exp.paid_by
        settled_ids = {u.id for u in exp.settled}
        splits_map  = {s.user_id: s.amount for s in exp.splits}
        for member_id, share in splits_map.items():
            if member_id == paid_by or member_id in settled_ids:
                continue
            if paid_by == uid:
                balances[member_id] += share
            elif member_id == uid:
                balances[paid_by] -= share
    payments = (Payment.query
                .filter(((Payment.from_user == uid) | (Payment.to_user == uid)) & (Payment.from_user != None))
                .all())
    for p in payments:
        if p.from_user == uid:
            balances[p.to_user] += p.amount
        else:
            balances[p.from_user] -= p.amount
    return {k: round(v, 2) for k, v in balances.items() if abs(v) > 0.01}


def _compute_global_balances():
    """Compute net balance for every user across all expenses and payments."""
    net = defaultdict(float)
    for exp in Expense.query.all():
        paid_by     = exp.paid_by
        settled_ids = {u.id for u in exp.settled}
        for s in exp.splits:
            if s.user_id == paid_by or s.user_id in settled_ids:
                continue
            net[paid_by]   += s.amount
            net[s.user_id] -= s.amount
    for p in Payment.query.filter(Payment.from_user != None).all():
        net[p.from_user] -= p.amount
        net[p.to_user]   += p.amount
    return {k: round(v, 2) for k, v in net.items() if abs(v) > 0.01}


def _simplify_debts(uid):
    """
    Graph-based debt simplification using a greedy min/max heap algorithm.
    Reduces the total number of transactions needed across the whole group,
    then returns only the transactions involving the current user.

    Example: A owes B $10, B owes C $10 -> simplified to A pays C $10 directly.
    """
    import heapq
    global_net = _compute_global_balances()

    debtors   = []  # most negative first
    creditors = []  # most positive first

    for user_id, balance in global_net.items():
        if balance < -0.01:
            heapq.heappush(debtors,   (balance, user_id))
        elif balance > 0.01:
            heapq.heappush(creditors, (-balance, user_id))

    transactions = []  # (from_id, to_id, amount)

    while debtors and creditors:
        debt_bal,  debtor_id   = heapq.heappop(debtors)
        cred_bal,  creditor_id = heapq.heappop(creditors)
        cred_bal = -cred_bal

        settled          = round(min(-debt_bal, cred_bal), 2)
        remaining_debt   = round(debt_bal + settled, 2)
        remaining_credit = round(cred_bal - settled, 2)

        transactions.append((debtor_id, creditor_id, settled))

        if remaining_debt < -0.01:
            heapq.heappush(debtors,   (remaining_debt, debtor_id))
        if remaining_credit > 0.01:
            heapq.heappush(creditors, (-remaining_credit, creditor_id))

    # Return only transactions involving the current user
    simplified = []
    for from_id, to_id, amount in transactions:
        if from_id == uid:
            other = User.query.get(to_id)
            if other:
                simplified.append({"direction": "i_owe", "user": other, "amount": amount, "user_id": to_id})
        elif to_id == uid:
            other = User.query.get(from_id)
            if other:
                simplified.append({"direction": "owes_me", "user": other, "amount": amount, "user_id": from_id})
    return simplified


def _monthly_spending(uid):
    months = []
    now    = datetime.utcnow()
    for i in range(5, -1, -1):
        base        = now - timedelta(days=i * 30)
        month_start = base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_m      = month_start + timedelta(days=32)
        month_end   = next_m.replace(day=1)
        exps  = (Expense.query
                 .filter(Expense.members.any(id=uid))
                 .filter(Expense.created_at >= month_start, Expense.created_at < month_end)
                 .all())
        total = sum(s.amount for e in exps for s in e.splits if s.user_id == uid)
        months.append({"month": month_start.strftime("%b"), "amount": round(total, 2)})
    return months


def _category_breakdown(uid):
    cats = defaultdict(float)
    for exp in Expense.query.filter(Expense.members.any(id=uid)).all():
        for s in exp.splits:
            if s.user_id == uid:
                cats[exp.category] += s.amount
    return [{"category": k, "total": round(v, 2)} for k, v in sorted(cats.items(), key=lambda x: -x[1]) if v > 0]


def _top_partners(uid):
    partner_amounts = defaultdict(float)
    for exp in Expense.query.filter(Expense.members.any(id=uid)).all():
        user_share = next((s.amount for s in exp.splits if s.user_id == uid), 0)
        for m in exp.members:
            if m.id != uid:
                partner_amounts[m.id] += user_share
    result = []
    for pid, amount in sorted(partner_amounts.items(), key=lambda x: x[1], reverse=True)[:3]:
        p = User.query.get(pid)
        if p:
            result.append({"user": p, "amount": round(amount, 2), "user_id": pid})
    return result


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    print("Starting Spiltwise...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
