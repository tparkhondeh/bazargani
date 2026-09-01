"use strict";

const API_ENDPOINT = "/api/v1/requests/parse";
const EXAMPLE_REQUEST =
  "برای واردات ۳۰۰ دستگاه اسپرسوساز نیمه‌اتوماتیک، مبدأ: ایتالیا، مقصد: تهران، اینکوترمز: FOB";

const form = document.getElementById("request-form");
const apiKeyInput = document.getElementById("api-key");
const requestInput = document.getElementById("request-text");
const parseButton = document.getElementById("parse-button");
const exampleButton = document.getElementById("example-button");
const characterCount = document.getElementById("character-count");
const resultBadge = document.getElementById("result-badge");
const resultStatus = document.getElementById("result-status");
const parsedResult = document.getElementById("parsed-result");
const parsedFields = document.getElementById("parsed-fields");

const persianNumber = new Intl.NumberFormat("fa-IR");

const fieldDefinitions = [
  { key: "product_name", label: "کالا" },
  { key: "quantity", label: "تعداد" },
  { key: "quantity_unit", label: "واحد تعداد" },
  { key: "origin_market", label: "بازار مبدأ" },
  { key: "destination", label: "مقصد" },
  { key: "requested_incoterm_code", label: "Incoterm درخواستی" },
];

const fieldLabels = Object.fromEntries(
  fieldDefinitions.map((definition) => [definition.key, definition.label]),
);

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function setBadge(text, state) {
  resultBadge.textContent = text;
  resultBadge.className = `result-badge ${state}`;
}

function setLoading(isLoading) {
  parseButton.disabled = isLoading;
  parseButton.textContent = isLoading
    ? "در حال بررسی…"
    : "بررسی و ساختاربندی درخواست";
}

function updateCharacterCount() {
  characterCount.textContent = `${persianNumber.format(requestInput.value.length)} از ۵۰۰۰`;
}

function setStatus(title, detail, isError = false) {
  clearNode(resultStatus);
  resultStatus.className = isError ? "result-status is-error" : "result-status";

  const heading = document.createElement("h3");
  heading.textContent = title;
  const paragraph = document.createElement("p");
  paragraph.textContent = detail;
  resultStatus.append(heading, paragraph);
  resultStatus.hidden = false;
  parsedResult.hidden = true;
}

function displayValue(key, value, data) {
  if (key === "quantity" && Number.isInteger(value)) {
    return persianNumber.format(value);
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (key === "quantity_unit" && Number.isInteger(data.quantity)) {
    return "اعلام نشده";
  }
  return "تشخیص داده نشد";
}

function confidenceLabel(value) {
  const labels = {
    HIGH: "اطمینان بالا",
    MEDIUM: "اطمینان متوسط",
    LOW: "اطمینان پایین",
    UNKNOWN: "نامشخص",
  };
  return labels[value] || "نامشخص";
}

function renderFields(data) {
  clearNode(parsedFields);
  const confidence = data.field_confidence;
  const safeConfidence = confidence && typeof confidence === "object" ? confidence : {};

  fieldDefinitions.forEach((definition) => {
    const card = document.createElement("div");
    card.className = "field-card";

    const name = document.createElement("span");
    name.className = "field-name";
    name.textContent = definition.label;

    const value = document.createElement("span");
    value.className = "field-value";
    value.textContent = displayValue(definition.key, data[definition.key], data);

    const confidenceValue = safeConfidence[definition.key];
    const confidenceChip = document.createElement("span");
    confidenceChip.className = confidenceValue === "HIGH" ? "confidence high" : "confidence";
    confidenceChip.textContent = confidenceLabel(confidenceValue);

    card.append(name, value, confidenceChip);
    parsedFields.append(card);
  });
}

function safeStringArray(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item) => typeof item === "string" && item.trim());
}

function renderList(sectionId, listId, items) {
  const section = document.getElementById(sectionId);
  const list = document.getElementById(listId);
  clearNode(list);
  items.forEach((item) => {
    const entry = document.createElement("li");
    entry.textContent = item;
    list.append(entry);
  });
  section.hidden = items.length === 0;
}

function renderConflicts(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value).flatMap(([key, candidates]) => {
    const safeCandidates = safeStringArray(candidates);
    if (!safeCandidates.length) {
      return [];
    }
    const label = fieldLabels[key] || "فیلد ناشناخته";
    return [`${label}: ${safeCandidates.join("، ")}`];
  });
}

function renderResult(data) {
  renderFields(data);
  renderList(
    "questions-section",
    "questions-list",
    safeStringArray(data.critical_questions),
  );
  renderList(
    "conflicts-section",
    "conflicts-list",
    renderConflicts(data.field_conflicts),
  );
  renderList(
    "assumptions-section",
    "assumptions-list",
    safeStringArray(data.assumptions),
  );

  resultStatus.hidden = true;
  parsedResult.hidden = false;
  if (data.can_start_research === true) {
    setBadge("آماده برای مرحله شروع", "ready");
  } else {
    setBadge("نیازمند تکمیل", "attention");
  }
}

function errorPresentation(status) {
  const presentations = {
    401: ["کلید دسترسی پذیرفته نشد", "کلید API معتبر را وارد کنید و دوباره تلاش کنید."],
    403: ["دسترسی کافی نیست", "این کلید اجازه انجام این عملیات را ندارد."],
    413: ["متن بیش از حد بزرگ است", "درخواست را کوتاه‌تر از سقف مجاز ارسال کنید."],
    422: ["متن قابل بررسی نیست", "یک متن غیرخالی و حداکثر ۵۰۰۰ نویسه وارد کنید."],
    429: ["تعداد درخواست‌ها زیاد است", "کمی بعد دوباره تلاش کنید."],
  };
  return presentations[status] || [
    "بررسی انجام نشد",
    "پاسخ قابل استفاده‌ای از سرویس دریافت نشد. دوباره تلاش کنید.",
  ];
}

async function parseRequest(event) {
  event.preventDefault();
  const text = requestInput.value.trim();
  if (!text) {
    setBadge("ورودی لازم است", "attention");
    setStatus("متن درخواست خالی است", "شرح نیاز بازرگانی را وارد کنید.", true);
    requestInput.focus();
    return;
  }

  setLoading(true);
  setBadge("در حال بررسی", "neutral");
  setStatus("در حال ساختاربندی درخواست…", "سامانه فقط قواعد قطعی ورودی را اجرا می‌کند.");

  const headers = { "Content-Type": "application/json" };
  const apiKey = apiKeyInput.value.trim();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

  try {
    const response = await fetch(API_ENDPOINT, {
      method: "POST",
      headers,
      body: JSON.stringify({ text }),
      cache: "no-store",
      credentials: "same-origin",
      referrerPolicy: "no-referrer",
    });

    if (!response.ok) {
      const [title, detail] = errorPresentation(response.status);
      setBadge("خطا در بررسی", "error");
      setStatus(title, detail, true);
      return;
    }

    const data = await response.json();
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new TypeError("unexpected parser response");
    }
    renderResult(data);
  } catch (_error) {
    setBadge("سرویس در دسترس نیست", "error");
    setStatus(
      "ارتباط با سرویس برقرار نشد",
      "مطمئن شوید API محلی فعال است و سپس دوباره تلاش کنید.",
      true,
    );
  } finally {
    setLoading(false);
  }
}

requestInput.addEventListener("input", updateCharacterCount);
exampleButton.addEventListener("click", () => {
  requestInput.value = EXAMPLE_REQUEST;
  updateCharacterCount();
  requestInput.focus();
});
form.addEventListener("submit", parseRequest);
window.addEventListener("pagehide", () => {
  apiKeyInput.value = "";
});
updateCharacterCount();
