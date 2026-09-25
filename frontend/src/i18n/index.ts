import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import ta from "./ta.json";

const STORAGE_KEY = "cocreat.lang";

function savedLanguage(): "en" | "ta" {
  try {
    return localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "ta";
  } catch {
    return "ta";
  }
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ta: { translation: ta } },
  lng: savedLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React already escapes
});

i18n.on("languageChanged", (lng) => {
  document.documentElement.lang = lng;
  try {
    localStorage.setItem(STORAGE_KEY, lng);
  } catch {
    // private mode: language just won't persist
  }
});

export default i18n;
