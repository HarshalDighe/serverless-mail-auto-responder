/* =========================================
   CONFIG
========================================= */

const API_URL = "https://3h0zcreeg1.execute-api.us-east-1.amazonaws.com/prod/report";

let lineChart = null;
let pieChart = null;
let barChart = null;

let autoRefreshInterval = null;
let isAutoRefreshOn = false;

const currentPage =
  window.location.pathname.split("/").pop() || "index.html";

/* =========================================
   AUTH
========================================= */

if (currentPage === "index.html") {
  if (sessionStorage.getItem("isLoggedIn") !== "true") {
    window.location.replace("login.html");
  }
}

if (currentPage === "login.html") {
  if (sessionStorage.getItem("isLoggedIn") === "true") {
    window.location.replace("index.html");
  }
}

function login() {
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();
  const errorMsg = document.getElementById("errorMsg");

  if (!username || !password) {
    errorMsg.innerText = "Enter username and password.";
    return;
  }

  if (username === "admin" && password === "123") {
    sessionStorage.setItem("isLoggedIn", "true");
    window.location.replace("index.html");
  } else {
    errorMsg.innerText = "Invalid credentials.";
  }
}

function logout() {
  sessionStorage.clear();
  window.location.replace("login.html");
}

/* =========================================
   LOAD DATA
========================================= */

async function loadData() {
  try {
    const response = await fetch(API_URL);

    if (!response.ok) throw new Error("API Error");

    const result = await response.json();
    const data = result.body ? JSON.parse(result.body) : result;

    console.log("API DATA:", data);

    updateKPIs(data);
    updateTable(data.records || []);
    renderCharts(data);

    setApiStatus(true);

  } catch (error) {
    console.error("API Error:", error);
    setApiStatus(false);
  }
}

function setApiStatus(isOnline) {
  const status = document.getElementById("apiStatus");
  if (!status) return;

  if (isOnline) {
    status.innerText = "API: Online";
    status.className = "status-badge online";
  } else {
    status.innerText = "API: Offline";
    status.className = "status-badge offline";
  }
}

/* =========================================
   KPI
========================================= */

function updateKPIs(data) {

  const today = data.today || 0;
  const processed = data.processed || 0;
  const autoReplies = data.auto_replies || 0;

  const notAutoReplied = processed - autoReplies;

  const successRate =
    processed > 0 ? ((autoReplies / processed) * 100).toFixed(1) : 0;

  const todayEl = document.getElementById("today");
  const processedEl = document.getElementById("processed");
  const notReplyEl = document.getElementById("notAutoReplied");
  const successEl = document.getElementById("successRate");
  const autoReplyEl = document.getElementById("autoReplied");

  if (todayEl) todayEl.innerText = today;
  if (processedEl) processedEl.innerText = processed;
  if (autoReplyEl) autoReplyEl.innerText = autoReplies;
  if (notReplyEl) notReplyEl.innerText = notAutoReplied;
  if (successEl) successEl.innerText = successRate + "%";
}

/* =========================================
   TABLE (FULL DYNAMODB RECORDS)
========================================= */

function updateTable(records) {
  const table = document.getElementById("activityTable");
  if (!table) return;

  table.innerHTML = "";

  if (!records.length) {
    table.innerHTML =
      "<tr><td colspan='7'>No Records Found</td></tr>";
    return;
  }

  records.forEach((item) => {
    table.innerHTML += `
      <tr>
        <td>${item.transaction_id || "-"}</td>
        <td>${item.email_id || "-"}</td>
        <td>${item.sender_email || "-"}</td>
        <td>${item.keyword || "-"}</td>
        <td>${item.status || "-"}</td>
        <td>${item.auto_reply ? "Yes" : "No"}</td>
        <td>${item.timestamp || "-"}</td>
      </tr>
    `;
  });
}

/* =========================================
   CHARTS
========================================= */

function renderCharts(data) {

  if (!document.getElementById("lineChart")) return;

  if (lineChart) lineChart.destroy();
  if (pieChart) pieChart.destroy();
  if (barChart) barChart.destroy();

  const weeklyData = data.weekly_data || [0,0,0,0,0,0,0];

  lineChart = new Chart(document.getElementById("lineChart"), {
    type: "line",
    data: {
      labels: ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
      datasets: [{
        label: "Emails",
        data: weeklyData
      }]
    }
  });

  const keywords = data.keyword_distribution || {};

  pieChart = new Chart(document.getElementById("pieChart"), {
    type: "pie",
    data: {
      labels: Object.keys(keywords),
      datasets: [{
        data: Object.values(keywords)
      }]
    }
  });

  barChart = new Chart(document.getElementById("barChart"), {
    type: "bar",
    data: {
      labels: ["Processed","Failed"],
      datasets: [{
        data: [data.processed || 0, data.failed || 0]
      }]
    }
  });
}

/* =========================================
   AUTO REFRESH
========================================= */

function toggleAutoRefresh() {
  const btn = document.querySelector(".refresh-btn");

  if (!isAutoRefreshOn) {
    autoRefreshInterval = setInterval(loadData, 30000);
    if (btn) btn.innerText = "Auto Refresh: ON";
    isAutoRefreshOn = true;
  } else {
    clearInterval(autoRefreshInterval);
    if (btn) btn.innerText = "Auto Refresh: OFF";
    isAutoRefreshOn = false;
  }
}

/* =========================================
   THEME
========================================= */

function toggleTheme() {
  document.body.classList.toggle("light-mode");
}

/* =========================================
   AUTO LOAD
========================================= */

document.addEventListener("DOMContentLoaded", loadData);