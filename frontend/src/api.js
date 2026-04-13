const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function runChatQuery(question) {
  const response = await fetch(`${API_BASE}/api/chat/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error || payload?.detail || "Backend request failed.");
  }
  return payload;
}

export async function generateInsightsReport(payload = {}) {
  const response = await fetch(`${API_BASE}/api/insights/report/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || body?.error || "Failed to generate insights report.");
  }
  return body;
}

export function getInsightsReportDownloadUrl() {
  return `${API_BASE}/api/insights/report/download`;
}

export async function sendInsightsReportEmail(recipientEmail) {
  const response = await fetch(`${API_BASE}/api/insights/report/email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipient_email: recipientEmail }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || body?.error || "Failed to send insights report email.");
  }
  return body;
}
