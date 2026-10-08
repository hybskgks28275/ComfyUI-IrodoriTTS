import { app } from "../../scripts/app.js";

export function locale() {
    const value = app.ui?.settings?.getSettingValue("Comfy.Locale");
    return /^ja(?:[-_]|$)/i.test(String(value ?? "")) ? "ja" : "en";
}

export function t(english, japanese) {
    return locale() === "ja" ? japanese : english;
}

// Repaint existing DOM widgets when the user changes ComfyUI's language.
export function watchLocale(node, refresh) {
    const settings = app.ui?.settings;
    settings?.addEventListener("Comfy.Locale.change", refresh);
    const removed = node.onRemoved;
    node.onRemoved = function () {
        settings?.removeEventListener("Comfy.Locale.change", refresh);
        return removed?.apply(this, arguments);
    };
    refresh();
}
