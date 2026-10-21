
const API_URL = "https://YOUR-RENDER-SERVICE.onrender.com";

let transactions = [];
let monthlyChart = null;
let categoryChart = null;

const $ = (id) => document.getElementById(id);

function money(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2
  }).format(Number(value) || 0);
}

function showMessage(message, type = "") {
  const el = $("formMessage");
  el.textContent = message;
  el.className = `form-message ${type}`;
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

function setConnection(online) {
  $("connection").textContent = online ? "API connected" : "API unavailable";
  const dot = document.querySelector(".live-dot");
  dot.style.background = online ? "#48dfb0" : "#ff8294";
  dot.style.boxShadow = online
    ? "0 0 10px #48dfb066"
    : "0 0 10px #ff829466";
}

function setToday() {
  const now = new Date();
  $("date").value = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0")
  ].join("-");
}

function updateCategoryOptions() {
  const type = document.querySelector('input[name="type"]:checked').value;
  const select = $("category");
  const previous = select.value;

  const categories = type === "income"
    ? ["Salary", "Business", "Investment", "Gift", "Other"]
    : ["Food", "Transport", "Shopping", "Bills", "Education",
       "Health", "Entertainment", "Other"];

  select.replaceChildren();

  categories.forEach(category => {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    select.appendChild(option);
  });

  if (categories.includes(previous)) select.value = previous;
}

function renderSummary(summary) {
  $("totalIncome").textContent = money(summary.total_income);
  $("totalExpense").textContent = money(summary.total_expense);
  $("currentBalance").textContent = money(summary.balance);
  $("savingsRate").textContent = `${summary.savings_rate}%`;
}

function renderMonthlyChart(rows) {
  const labels = rows.map(item => item.month);
  const income = rows.map(item => item.income);
  const expenses = rows.map(item => item.expense);

  if (monthlyChart) monthlyChart.destroy();

  monthlyChart = new Chart($("monthlyChart"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Income",
          data: income,
          backgroundColor: "#48dfb0",
          borderRadius: 5
        },
        {
          label: "Expenses",
          data: expenses,
          backgroundColor: "#a78bfa",
          borderRadius: 5
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 650 },
      plugins: {
        legend: {
          labels: { color: "#aeb7d0", usePointStyle: true, boxWidth: 8 }
        },
        tooltip: {
          callbacks: {
            label: context => `${context.dataset.label}: ${money(context.raw)}`
          }
        }
      },
      scales: {
        x: {
          ticks: { color: "#929bb6", maxRotation: 0 },
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          ticks: {
            color: "#929bb6",
            callback: value => "₹" + Number(value).toLocaleString("en-IN")
          },
          grid: { color: "#ffffff0b" }
        }
      }
    }
  });
}

function renderCategoryChart(rows) {
  const canvas = $("categoryChart");
  const empty = $("categoryEmpty");

  if (categoryChart) {
    categoryChart.destroy();
    categoryChart = null;
  }

  if (!rows.length) {
    canvas.style.display = "none";
    empty.style.display = "block";
    return;
  }

  canvas.style.display = "block";
  empty.style.display = "none";

  categoryChart = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: rows.map(item => item.category),
      datasets: [{
        data: rows.map(item => item.total),
        backgroundColor: [
          "#a78bfa", "#48dfb0", "#6f9dff", "#ff8294",
          "#f6c76b", "#57c7dc", "#ed91d3", "#a5b4fc"
        ],
        borderColor: "#191e32",
        borderWidth: 4,
        hoverOffset: 7
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: "#aeb7d0",
            usePointStyle: true,
            boxWidth: 8,
            padding: 14
          }
        },
        tooltip: {
          callbacks: {
            label: context => `${context.label}: ${money(context.raw)}`
          }
        }
      }
    }
  });
}

function formatDate(value) {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function renderTransactions() {
  const query = $("searchInput").value.trim().toLowerCase();

  const filtered = transactions.filter(item =>
    item.title.toLowerCase().includes(query) ||
    item.category.toLowerCase().includes(query) ||
    item.type.toLowerCase().includes(query)
  );

  const tbody = $("transactionList");
  tbody.replaceChildren();

  if (!filtered.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.className = "empty";
    td.textContent = transactions.length
      ? "No matching transactions found."
      : "No transactions yet. Add your first transaction!";
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  filtered.forEach(item => {
    const tr = document.createElement("tr");
    const titleCell = document.createElement("td");
    const title = document.createElement("span");
    const category = document.createElement("span");

    title.className = "tx-title";
    title.textContent = item.title;
    category.className = "tx-category";
    category.textContent = item.category;
    titleCell.append(title, category);

    const amountCell = document.createElement("td");
    amountCell.className = item.type === "income"
      ? "amount-income" : "amount-expense";
    amountCell.textContent =
      `${item.type === "income" ? "+" : "−"}${money(item.amount)}`;

    const dateCell = document.createElement("td");
    dateCell.textContent = formatDate(item.date);

    const actionCell = document.createElement("td");
    const deleteButton = document.createElement("button");
    deleteButton.className = "delete-btn";
    deleteButton.textContent = "Delete";
    deleteButton.setAttribute("aria-label", `Delete ${item.title}`);
    deleteButton.addEventListener("click", () => deleteTransaction(item.id));
    actionCell.appendChild(deleteButton);

    tr.append(titleCell, amountCell, dateCell, actionCell);
    tbody.appendChild(tr);
  });

  $("transactionCount").textContent =
    `${filtered.length} transaction${filtered.length === 1 ? "" : "s"}`;
}

async function loadAll() {
  const refreshButton = document.querySelector(".section-heading .btn");
  refreshButton.disabled = true;

  try {
    const [summary, transactionData, monthly, categories] = await Promise.all([
      api("/api/summary"),
      api("/api/transactions"),
      api("/api/analytics/monthly"),
      api("/api/analytics/categories")
    ]);

    transactions = transactionData.transactions;
    renderSummary(summary);
    renderTransactions();
    renderMonthlyChart(monthly.months);
    renderCategoryChart(categories.categories);
    setConnection(true);
  } catch (error) {
    setConnection(false);
    showMessage(
      `Could not load data: ${error.message}. Check your Render URL and service logs.`,
      "error"
    );
  } finally {
    refreshButton.disabled = false;
  }
}

$("transactionForm").addEventListener("submit", async event => {
  event.preventDefault();

  const saveButton = $("saveButton");
  saveButton.disabled = true;
  saveButton.textContent = "Saving...";

  const payload = {
    title: $("title").value.trim(),
    amount: Number($("amount").value),
    type: document.querySelector('input[name="type"]:checked').value,
    category: $("category").value,
    date: $("date").value
  };

  try {
    await api("/api/transactions", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    showMessage("✓ Transaction saved successfully!", "success");
    $("title").value = "";
    $("amount").value = "";
    setToday();
    await loadAll();
  } catch (error) {
    showMessage(`Could not save: ${error.message}`, "error");
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = "＋ Save transaction";
  }
});

async function deleteTransaction(id) {
  if (!confirm("Delete this transaction permanently?")) return;

  try {
    await api(`/api/transactions/${id}`, { method: "DELETE" });
    showMessage("Transaction deleted successfully.", "success");
    await loadAll();
  } catch (error) {
    showMessage(`Could not delete: ${error.message}`, "error");
  }
}

document.querySelectorAll('input[name="type"]').forEach(radio => {
  radio.addEventListener("change", updateCategoryOptions);
});

$("searchInput").addEventListener("input", renderTransactions);

setToday();
updateCategoryOptions();
loadAll();
