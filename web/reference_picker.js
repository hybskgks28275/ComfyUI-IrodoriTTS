import { t, locale } from "./i18n.js";
// ComponentWidget multiselects are not mounted by some Nodes 2.0 releases.
// This DOM-widget fallback shares the existing files value and saved workflow.
export function createReferencePicker(filesWidget, onChange) {
    const element = document.createElement("details");
    element.className = "irodori-reference-picker";
    element.style.cssText = "padding:8px;font:13px sans-serif;";
    const summary = document.createElement("summary");
    summary.textContent = t("Select reference audio (multiple files allowed)", "参照音声を選択（複数可）");
    summary.style.cursor = "pointer";
    element.appendChild(summary);
    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = t("Search by filename", "ファイル名で検索");
    search.setAttribute("aria-label", t("Search reference audio", "参照音声を検索"));
    search.style.cssText = "box-sizing:border-box;width:100%;margin:6px 0;padding:4px;";
    element.appendChild(search);
    const list = document.createElement("div");
    list.style.cssText = "max-height:180px;overflow:auto;";
    element.appendChild(list);
    const checkboxes = new Map();
    let signature;
    const refresh = () => {
        summary.textContent = t("Select reference audio (multiple files allowed)", "参照音声を選択（複数可）");
        search.placeholder = t("Search by filename", "ファイル名で検索");
        search.setAttribute("aria-label", t("Search reference audio", "参照音声を検索"));
        const selected = Array.isArray(filesWidget.value) ? filesWidget.value : [];
        const options = filesWidget.inputSpec?.options ?? filesWidget.options.values ?? [];
        const nextSignature = JSON.stringify([options, selected, search.value, locale()]);
        if (signature === nextSignature) return;
        signature = nextSignature;
        // Keep missing selections visible until explicitly removed by the user.
        const names = [...new Set([...options, ...selected])];
        list.replaceChildren();
        checkboxes.clear();
        for (const name of names.filter((name) => name.toLowerCase().includes(search.value.toLowerCase()))) {
            const label = document.createElement("label");
            label.style.cssText = "display:flex;gap:6px;align-items:center;padding:4px 0;overflow-wrap:anywhere;";
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = selected.includes(name);
            checkboxes.set(name, checkbox);
            checkbox.addEventListener("change", () => {
                const focused = document.activeElement === checkbox;
                const current = Array.isArray(filesWidget.value) ? filesWidget.value : [];
                onChange(checkbox.checked ? [...current, name] : current.filter((file) => file !== name));
                if (focused) checkboxes.get(name)?.focus();
            });
            label.append(checkbox, document.createTextNode(name));
            list.appendChild(label);
        }
        if (!list.childElementCount) list.textContent = t("No matching audio files. Refresh the file list.", "該当する音声がありません。一覧を更新してください。");
    };
    search.addEventListener("input", refresh);
    refresh();
    return { element, refresh };
}
