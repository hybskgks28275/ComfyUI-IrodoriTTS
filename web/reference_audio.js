import { t, locale, watchLocale } from "./i18n.js";
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { createReferencePicker } from "./reference_picker.js";

app.registerExtension({
    name: "IrodoriTTS.ReferenceAudioSelection",
    setup() {
        const style = document.createElement("style");
        style.textContent = ".irodori-reference-picker{display:none}[data-node-id] .irodori-reference-picker{display:block}";
        document.head.appendChild(style);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "IrodoriTTSLoadReferenceAudios") return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            const filesWidget = this.widgets.find((widget) => widget.name === "files");
            const referencePanel = document.createElement("div");
            referencePanel.style.cssText = "box-sizing:border-box;overflow:auto;";
            const orderPanel = document.createElement("div");
            orderPanel.style.cssText = "box-sizing:border-box;padding:8px;overflow:auto;color:var(--input-text,#ddd);background:var(--comfy-input-bg,#222);font:13px sans-serif;";
            referencePanel.addEventListener("pointerdown", (event) => event.stopPropagation());
            referencePanel.addEventListener("wheel", (event) => event.stopPropagation());
            let lastOrder;
            const selectedFiles = () => Array.isArray(filesWidget.value) ? [...filesWidget.value] : [];
            const setFiles = (files) => {
                this.graph?.beforeChange();
                filesWidget.value = files;
                filesWidget.callback?.(files);
                this.graph?.afterChange();
                renderOrder();
                this.setDirtyCanvas(true, true);
            };
            const picker = createReferencePicker(filesWidget, setFiles);
            referencePanel.append(picker.element, orderPanel);
            const changeOrder = (index, offset) => {
                const files = selectedFiles();
                const target = index + offset;
                if (target < 0 || target >= files.length) return;
                [files[index], files[target]] = [files[target], files[index]];
                // The existing files value is the sole saved/executed source of order.
                setFiles(files);
                orderPanel.querySelector(`[data-position="${target}"] button:not(:disabled)`)?.focus();
            };
            const renderOrder = () => {
                picker.refresh();
                const files = selectedFiles();
                const signature = JSON.stringify([files, locale()]);
                if (signature === lastOrder) return;
                lastOrder = signature;
                orderPanel.replaceChildren();
                const heading = document.createElement("div");
                heading.textContent = t("Reference order (top to bottom)", "参照順序（上から使用）");
                heading.style.cssText = "font-weight:bold;margin-bottom:8px;";
                orderPanel.appendChild(heading);
                if (!files.length) {
                    const empty = document.createElement("div");
                    empty.textContent = t("Select audio files to arrange their order here.", "filesで音声を選択すると、ここで順序を変更できます。");
                    orderPanel.appendChild(empty);
                }
                files.forEach((file, index) => {
                    const row = document.createElement("div");
                    row.dataset.position = String(index);
                    row.style.cssText = "display:flex;align-items:center;gap:6px;margin:5px 0;";
                    const label = document.createElement("span");
                    label.textContent = `${index + 1}. ${file}`;
                    label.title = file;
                    label.style.cssText = "flex:1;min-width:0;overflow-wrap:anywhere;";
                    row.appendChild(label);
                    for (const [offset, symbol, description] of [[-1, "↑", t("Move up", "上へ")], [1, "↓", t("Move down", "下へ")]]) {
                        const button = document.createElement("button");
                        button.type = "button";
                        button.textContent = symbol;
                        button.title = description;
                        button.setAttribute("aria-label", `${description}: ${index + 1}. ${file}`);
                        button.disabled = index + offset < 0 || index + offset >= files.length;
                        button.style.cssText = "flex:none;width:30px;height:28px;cursor:pointer;";
                        button.addEventListener("click", () => changeOrder(index, offset));
                        row.appendChild(button);
                    }
                    orderPanel.appendChild(row);
                });
            };
            const previousCallback = filesWidget.callback;
            filesWidget.callback = function () {
                const value = previousCallback?.apply(this, arguments);
                renderOrder();
                return value;
            };
            this.addDOMWidget("reference_order", "irodori_reference_order", referencePanel, {
                serialize: false,
                getMinHeight: () => 140,
                getMaxHeight: () => 260,
                onDraw: renderOrder,
            });
            const onConfigure = this.onConfigure;
            this.onConfigure = function () {
                const value = onConfigure?.apply(this, arguments);
                renderOrder();
                return value;
            };
            renderOrder();
            const refreshButton = this.addWidget("button", t("Refresh audio file list", "音声ファイル一覧を更新"), null, async () => {
                try {
                    const response = await api.fetchApi("/object_info/IrodoriTTSLoadReferenceAudios");
                    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
                    const info = await response.json();
                    const spec = info.IrodoriTTSLoadReferenceAudios.input.required.files;
                    const values = spec[1].options;
                    if (!Array.isArray(values)) throw new Error(t("Invalid reference audio list.", "参照音声一覧の形式が不正です。"));
                    filesWidget.inputSpec?.options?.splice(0, filesWidget.inputSpec.options.length, ...values);
                    filesWidget.options.values = values;
                    picker.refresh();
                    // Preserve selections so a missing file never silently changes the voice.
                    this.setDirtyCanvas(true, true);
                } catch (error) {
                    alert(`${t("Failed to refresh reference audio files.", "参照音声一覧の更新に失敗しました。")}\n${error.message}`);
                }
            }, { serialize: false });
            watchLocale(this, () => {
                refreshButton.label = t("Refresh audio file list", "音声ファイル一覧を更新");
                filesWidget.options.placeholder = t("Select reference audio (multiple files allowed)", "参照音声を選択（複数可）");
                if (filesWidget.inputSpec) filesWidget.inputSpec.placeholder = filesWidget.options.placeholder;
                renderOrder();
                this.setDirtyCanvas(true, true);
            });
            return result;
        };
    },
});
