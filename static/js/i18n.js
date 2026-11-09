/**
 * Minimal i18n module (issue #9).
 *
 * - dictionaries live in /static/i18n/<lang>.json (sv.json is the reference)
 * - keys are English identifiers; values are strings, or {one, other} for plurals
 * - t(key, params) interpolates {placeholder} values
 * - static HTML is translated via data-i18n / data-i18n-placeholder /
 *   data-i18n-title / data-i18n-aria-label attributes
 * - the chosen language is stored in localStorage, defaults from
 *   navigator.language, and is reflected on <html lang>
 * - dynamic views re-render on the "langchange" event
 */

const SUPPORTED = { sv: "Svenska", en: "English" };
const STORAGE_KEY = "riskmatris_lang";

let lang = "sv";
let dict = {};

export function getLang() {
  return lang;
}

export function has(key) {
  return Object.prototype.hasOwnProperty.call(dict, key);
}

export function t(key, params) {
  let entry = Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : key;
  if (params && typeof params.count === "number" && entry && typeof entry === "object" && !Array.isArray(entry)) {
    entry = params.count === 1 ? entry.one : entry.other;
  }
  if (typeof entry !== "string") return key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      entry = entry.split(`{${k}}`).join(String(v));
    }
  }
  return entry;
}

function detectLang() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && SUPPORTED[stored]) return stored;
  } catch {
    /* localStorage unavailable – fall through */
  }
  const nav = (navigator.language || "sv").toLowerCase();
  if (nav.startsWith("en")) return "en";
  return "sv";
}

async function loadDict(code) {
  try {
    const res = await fetch(`/static/i18n/${code}.json`);
    dict = res.ok ? await res.json() : {};
  } catch {
    dict = {};
  }
}

export function applyStaticTranslations() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.getAttribute("data-i18n-title"));
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
    el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria-label")));
  });
  const title = document.querySelector("title");
  if (title) title.textContent = t("app.title");
}

export async function initI18n() {
  lang = detectLang();
  document.documentElement.lang = lang;
  await loadDict(lang);
  applyStaticTranslations();
  const select = document.getElementById("langSelect");
  if (select) {
    for (const [code, label] of Object.entries(SUPPORTED)) {
      if (!select.querySelector(`option[value="${code}"]`)) {
        const opt = document.createElement("option");
        opt.value = code;
        opt.textContent = label;
        select.appendChild(opt);
      }
    }
    select.value = lang;
    select.addEventListener("change", () => setLang(select.value));
  }
}

export async function setLang(code) {
  if (!SUPPORTED[code]) return;
  const changed = code !== lang;
  lang = code;
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = code;
  await loadDict(code);
  applyStaticTranslations();
  const select = document.getElementById("langSelect");
  if (select) select.value = code;
  if (changed) {
    window.dispatchEvent(new CustomEvent("langchange", { detail: code }));
  }
}
