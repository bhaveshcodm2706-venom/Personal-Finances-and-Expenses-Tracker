
const API_URL = "https://personal-finances-and-expenses-tracker-1.onrender.com";

const $ = (id) => document.getElementById(id);

let monthlyChart = null;
let categoryChart = null;
let transactions = [];
let budgetAmount = 0;

function money(value) {
  return Number(value || 0).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2
  });
}

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function today() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }

  return data;
}

function showMessage(id, message, success = false) {
  $(id).textContent = message;
  $(id).style.color = success ? "#35e0b0" : "#ff9aaa";
}

function renderSummary(data) {
  $("totalIncome").textContent = money(data.total_income);
  $("totalExpense").textContent = money(data.total_expense);
  $("currentBalance").textContent = money(data.balance);
  $("savingsRate").textContent = `${Number(data.savings_rate || 0).toFixed(1)}%`;
}

function renderTransactions() {
  const search = $("searchInput").value.trim().toLowerCase();

  const filtered = transactions.filter((t) =>
    `${t.title} ${t.category} ${t.date} ${t.type}`
      .toLowerCase()
      .includes(search)
  );

  const tbody = $("transactionList");
  tbody.replaceChildren();

  if (!filtered.length) {
    const row = tbody.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 4;
    cell.textContent = "No transactions found.";
  }

  filtered.forEach((t) => {
    const row = tbody.insertRow();

    const titleCell = row.insertCell();
    const title = document.createElement("strong");
    title.textContent = t.title;
    titleCell.appendChild(title);

    const category = document.createElement("div");
    category.className = "muted";
    category.textContent = `${t.category} · ${t.priority || "essential"}`;
    titleCell.appendChild(category);

    const amountCell = row.insertCell();
    amountCell.textContent =
      `${t.type === "income" ? "+" : "−"}${money(t.amount)}`;
    amountCell.style.color = t.type === "income" ? "#35e0b0" : "#ff7185";

    row.insertCell().textContent = t.date;

    const actionCell = row.insertCell();
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Delete";
    button.addEventListener("click", () => deleteTransaction(t.id));
    actionCell.appendChild(button);
  });

  $("transactionCount").textContent =
    `${filtered.length} transaction${filtered.length === 1 ? "" : "s"}`;
}

function renderMonthlyChart(data) {
  const context = $("monthlyChart").getContext("2d");

  if (monthlyChart) monthlyChart.destroy();

  monthlyChart = new Chart(context, {
    type: "bar",
    data: {
      labels: data.map((item) => item.month),
      datasets: [
        {
          label: "Income",
          data: data.map((item) => item.income),
          backgroundColor: "#35e0b0"
        },
        {
          label: "Expenses",
          data: data.map((item) => item.expense),
          backgroundColor: "#ff7185"
        }
      ]
    },
    options: {
      responsive: true,
      scales: {
        y: {
          beginAtZero: true,
          ticks: { color: "#9caed1" },
          grid: { color: "#303952" }
        },
        x: {
          ticks: { color: "#9caed1" },
          grid: { display: false }
        }
      },
      plugins: {
        legend: { labels: { color: "#f4f6ff" } }
      }
    }
  });
}

function renderCategoryChart(data) {
  if (categoryChart) categoryChart.destroy();

  categoryChart = new Chart($("categoryChart"), {
    type: "doughnut",
    data: {
      labels: data.map((item) => item.category),
      datasets: [{
        data: data.map((item) => item.total),
        backgroundColor: [
          "#a18aff", "#71a0ff", "#35e0b0", "#ff7185",
          "#ffcc66", "#f18aff", "#63d5e8", "#a6d96a"
        ]
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "#f4f6ff" }
        }
      }
    }
  });
}

async function loadAdvisor() {
  const month = currentMonth();
  const emergency = Number($("emergencyAmount").value || 0);
  const reserve = Number($("reservedBills").value || 0);

  const [budgetData, advisorData] = await Promise.all([
    api(`/api/budget?month=${month}`),
    api(`/api/advisor?month=${month}&emergency=${emergency}&reserve=${reserve}`)
  ]);

  budgetAmount = budgetData.amount || 0;

  if (document.activeElement !== $("monthlyBudget")) {
    $("monthlyBudget").value = budgetAmount || "";
  }

  renderAdvisor(advisorData);
}

function renderAdvisor(data) {
  const expenses = Number(data.expenses || 0);
  const budget = Number(data.budget || 0);
  const percentage = budget > 0 ? Math.round(expenses / budget * 100) : 0;

  $("budgetPercent").textContent = `${percentage}% used`;
  $("budgetBar").style.width = `${Math.min(percentage, 100)}%`;
  $("budgetBar").style.background =
    percentage >= 100 ? "#ff7185" :
    percentage >= 80 ? "#ffcc66" :
    "linear-gradient(90deg, #a18aff, #71a0ff)";

  if (!budget) {
    $("budgetStatus").textContent = "Set a monthly budget to track spending.";
  } else if (percentage >= 100) {
    $("budgetStatus").textContent =
      `Budget exceeded by ${money(expenses - budget)}.`;
  } else if (percentage >= 80) {
    $("budgetStatus").textContent =
      `${money(budget - expenses)} remains. Spending is getting close to your limit.`;
  } else {
    $("budgetStatus").textContent =
      `${money(budget - expenses)} remains in your budget.`;
  }

  $("advisorSummary").textContent =
    `This month: income ${money(data.income)}, expenses ${money(expenses)}, ` +
    `essential expenses ${money(data.essential_expenses)}, and optional expenses ` +
    `${money(data.optional_expenses)}. Current-month recorded balance: ${money(data.balance)}.`;

  const alerts = $("advisorAlerts");
  alerts.replaceChildren();

  (data.alerts || []).forEach((item) => {
    const box = document.createElement("div");
    box.className = `advisor-alert ${item.level || "warning"}`;
    box.textContent = item.message;
    alerts.appendChild(box);
  });

  if (!(data.alerts || []).length) {
    const box = document.createElement("div");
    box.className = "advisor-alert success";
    box.textContent = "No alerts right now. Continue tracking your money.";
    alerts.appendChild(box);
  }

  const tips = $("advisorTips");
  tips.replaceChildren();

  (data.tips || []).forEach((tip) => {
    const li = document.createElement("li");
    li.textContent = tip;
    tips.appendChild(li);
  });

  if (!(data.tips || []).length) {
    const li = document.createElement("li");
    li.textContent = "Keep recording transactions and review your budget regularly.";
    tips.appendChild(li);
  }
}

async function loadAll() {
  $("connection").textContent = "Connecting...";

  try {
    const [summary, transactionData, monthly, categories] = await Promise.all([
      api("/api/summary"),
      api("/api/transactions"),
      api("/api/analytics/monthly"),
      api("/api/analytics/categories")
    ]);

    renderSummary(summary);
    transactions = transactionData.transactions || [];
    renderTransactions();
    renderMonthlyChart(monthly);
    renderCategoryChart(categories);

    $("connection").textContent = "● Connected";
    $("connection").style.color = "#35e0b0";

    try {
      await loadAdvisor();
    } catch (error) {
      $("advisorSummary").textContent =
        `Smart Advisor could not load: ${error.message}. Check the backend deployment.`;
    }
  } catch (error) {
    $("connection").textContent = "● Connection error";
    $("connection").style.color = "#ff7185";
    showMessage("formMessage", error.message);
    $("advisorSummary").textContent =
      `Cannot load financial data: ${error.message}`;
  }
}

async function deleteTransaction(id) {
  if (!confirm("Delete this transaction?")) return;

  try {
    await api(`/api/transactions/${id}`, { method: "DELETE" });
    await loadAll();
  } catch (error) {
    alert(`Could not delete transaction: ${error.message}`);
  }
}

$("transactionForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const button = $("saveButton");
  button.disabled = true;
  showMessage("formMessage", "Saving transaction...", true);

  const type = $("type").value;
  const payload = {
    title: $("title").value.trim(),
    amount: Number($("amount").value),
    type,
    category: $("category").value,
    priority: type === "income" ? "essential" : $("priority").value,
    date: $("date").value
  };

  try {
    await api("/api/transactions", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    $("transactionForm").reset();
    $("date").value = today();
    showMessage("formMessage", "Transaction saved successfully!", true);
    await loadAll();
  } catch (error) {
    showMessage("formMessage", error.message);
  } finally {
    button.disabled = false;
  }
});

$("searchInput").addEventListener("input", renderTransactions);

$("saveBudget").addEventListener("click", async () => {
  const amount = Number($("monthlyBudget").value);

  if (!Number.isFinite(amount) || amount <= 0) {
    showMessage("budgetMessage", "Enter a budget greater than zero.");
    return;
  }

  try {
    await api(`/api/budget?month=${currentMonth()}`, {
      method: "POST",
      body: JSON.stringify({ amount })
    });

    showMessage("budgetMessage", "Monthly budget saved!", true);
    await loadAdvisor();
  } catch (error) {
    showMessage("budgetMessage", error.message);
  }
});

$("checkEmergency").addEventListener("click", async () => {
  const emergency = Number($("emergencyAmount").value);
  const reserve = Number($("reservedBills").value);

  if (
    !Number.isFinite(emergency) || emergency < 0 ||
    !Number.isFinite(reserve) || reserve < 0
  ) {
    alert("Enter valid non-negative amounts.");
    return;
  }

  try {
    await loadAdvisor();
  } catch (error) {
    $("advisorSummary").textContent =
      `Could not calculate your position: ${error.message}`;
  }
});

$("emergencyAmount").addEventListener("change", () => {
  loadAdvisor().catch(() => {});
});

$("reservedBills").addEventListener("change", () => {
  loadAdvisor().catch(() => {});
});


const incomeCategories = ["Salary", "Business", "Investment", "Gift"];
const expenseCategories = [
  "Food", "Transport", "Shopping", "Bills",
  "Education", "Health", "Entertainment", "Other"
];

function updateCategories() {
  const type = $("type").value;
  const categories = type === "income"
    ? incomeCategories
    : expenseCategories;

  $("category").replaceChildren();

  categories.forEach((category) => {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    $("category").appendChild(option);
  });

  $("priority").disabled = type === "income";
}

$("type").addEventListener("change", updateCategories);
updateCategories();

$("date").value = today();
loadAll();
