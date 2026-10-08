import { t, watchLocale } from "./i18n.js";
import { app } from "../../scripts/app.js";
import { EMOJIS } from "./emoji_data.js";

app.registerExtension({
    name: "IrodoriTTS.EmojiPalette",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "IrodoriTTSGenerate") return;
        const previous = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = previous?.apply(this, arguments);
            const textWidget = this.widgets.find((w) => w.name === "text");
            const panel = document.createElement("div");
            panel.style.cssText = "box-sizing:border-box;padding:6px;font:13px sans-serif;color:var(--input-text,#ddd);overflow:hidden;";
            const toggle = document.createElement("button");
            toggle.type = "button";
            toggle.textContent = t("Show emojis", "絵文字を表示");
            toggle.setAttribute("aria-expanded", "false");
            const buttonStyle = "padding:6px;cursor:pointer;color:inherit;background:var(--comfy-input-bg,#333);border:1px solid #666;border-radius:4px;";
            toggle.style.cssText = buttonStyle + "width:100%;";
            const body = document.createElement("div");
            body.hidden = true;
            body.setAttribute("role", "region");
            body.setAttribute("aria-label", t("Irodori emoji panel", "Irodori 絵文字パネル"));
            body.style.cssText = "position:fixed;z-index:10000;box-sizing:border-box;width:360px;padding:12px;border:1px solid #666;border-radius:8px;background:var(--comfy-menu-bg,#222);color:var(--input-text,#ddd);font:13px sans-serif;box-shadow:0 6px 24px #0008;overflow:auto;";
            const header = document.createElement("div");
            header.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;";
            const title = document.createElement("strong");
            title.textContent = t("Emojis", "絵文字");
            const close = document.createElement("button");
            close.type = "button";
            close.textContent = t("Close", "閉じる");
            close.style.cssText = buttonStyle;
            header.append(title, close);
            const hint = document.createElement("div");
            hint.textContent = t("Insert at the text cursor or replace the selection. Append if no cursor position is set.", "textのカーソル位置へ挿入。選択範囲は置換します。位置未指定なら末尾へ追加。");
            hint.style.cssText = "margin:6px 0;font-size:12px;";
            const grid = document.createElement("div");
            grid.style.cssText = "display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:4px;max-height:440px;overflow:auto;";
            body.append(header, hint, grid);
            panel.append(toggle);
            body.addEventListener("pointerdown", (e) => e.stopPropagation());
            body.addEventListener("wheel", (e) => e.stopPropagation());
            panel.addEventListener("pointerdown", (e) => e.stopPropagation());
            panel.addEventListener("wheel", (e) => e.stopPropagation());

            // Nodes 2.0 owns a Vue textarea; classic nodes expose inputEl.
            const textarea = () => {
                const host = panel.closest("[data-node-id]");
                if (host) return [...host.querySelectorAll("textarea")].find(
                    (e) => [...e.labels].some((label) => ["text", "Text", "読み上げテキスト", textWidget.label].includes(label.textContent.trim())));
                return textWidget.inputEl;
            };
            let selection;
            let composing = false;
            const remember = (event) => {
                const area = textarea();
                if (!area || (event?.target !== area && document.activeElement !== area)) return;
                selection = { value: area.value, start: area.selectionStart, end: area.selectionEnd };
            };
            const composition = (event) => {
                if (event.target === textarea()) composing = event.type === "compositionstart";
            };
            const controller = new AbortController();
            for (const type of ["selectionchange", "select", "input", "keyup", "pointerup", "focusout"])
                document.addEventListener(type, remember, { capture: true, signal: controller.signal });
            for (const type of ["compositionstart", "compositionend"])
                document.addEventListener(type, composition, { capture: true, signal: controller.signal });
            for (const [emoji, label, description, jaLabel, jaDescription] of EMOJIS) {
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = `${emoji} ${t(label, jaLabel)}`;
                button.title = t(description, jaDescription);
                button.style.cssText = buttonStyle + "text-align:left;";
                // Preserve the active text selection when using the mouse.
                button.addEventListener("pointerdown", (event) => {
                    remember();
                    event.preventDefault();
                });
                button.addEventListener("click", () => {
                    const area = textarea();
                    if (app.canvas?.read_only || textWidget.disabled || area?.readOnly || area?.disabled) return;
                    if (composing) {
                        hint.textContent = t("Finish composing text before choosing an emoji.", "日本語入力を確定してから絵文字を選んでください。");
                        return;
                    }
                    const value = String(textWidget.value ?? "");
                    const start = selection?.value === value ? selection.start : value.length;
                    const end = selection?.value === value ? selection.end : value.length;
                    const next = value.slice(0, start) + emoji + value.slice(end);
                    this.graph?.beforeChange();
                    if (area?.isConnected) {
                        area.focus({ preventScroll: true });
                        area.setSelectionRange(start, end);
                        // Native insertion preserves the textarea's undo history.
                        if (!document.execCommand("insertText", false, emoji)) {
                            area.setRangeText(emoji, start, end, "end");
                            area.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: emoji }));
                        }
                    }
                    if (textWidget.value !== next) {
                        textWidget.value = next;
                        textWidget.callback?.(next);
                    }
                    selection = { value: next, start: start + emoji.length, end: start + emoji.length };
                    this.graph?.afterChange();
                    this.setDirtyCanvas(true, true);
                });
                grid.append(button);
            }
            let open = false;
            let frame;
            const setOpen = (value) => {
                open = value;
                cancelAnimationFrame(frame);
                body.hidden = !open;
                toggle.textContent = open ? t("Hide emojis", "絵文字を隠す") : t("Show emojis", "絵文字を表示");
                toggle.setAttribute("aria-expanded", String(open));
                if (open) {
                    document.body.append(body);
                    position();
                } else {
                    body.remove();
                }
            };
            // A viewport overlay avoids node resizing and clipping in both renderers.
            const position = () => {
                if (!panel.isConnected || this.flags?.collapsed || this.graph !== app.graph) {
                    setOpen(false);
                    return;
                }
                const host = panel.closest("[data-node-id]");
                const rect = (host ?? panel).getBoundingClientRect();
                const width = Math.min(360, Math.max(0, window.innerWidth - 16));
                body.style.width = `${width}px`;
                body.style.maxHeight = `${Math.max(0, window.innerHeight - 16)}px`;
                body.style.left = `${Math.max(8, Math.min(rect.right + 12, window.innerWidth - width - 8))}px`;
                const top = (host ?? textarea() ?? panel).getBoundingClientRect().top;
                body.style.top = `${Math.max(8, Math.min(top, window.innerHeight - body.offsetHeight - 8))}px`;
                frame = requestAnimationFrame(position);
            };
            const paletteWidget = this.addDOMWidget("irodori_emoji_palette", "irodori_emoji_palette", panel, {
                serialize: false,
                getMinHeight: () => 44,
                getMaxHeight: () => 44,
            });
            paletteWidget.serialize = false;
            const savedOrder = this.widgets.filter((w) => w.serialize !== false).map((w) => w.name);
            const modelWidget = this.widgets.find((w) => w.name === "model_name");
            const textIndex = this.widgets.indexOf(textWidget);
            if (textIndex >= 0) {
                this.widgets.splice(this.widgets.indexOf(paletteWidget), 1);
                if (modelWidget) this.widgets.splice(this.widgets.indexOf(modelWidget), 1);
                this.widgets.splice(this.widgets.indexOf(textWidget) + 1, 0,
                    paletteWidget, ...(modelWidget ? [modelWidget] : []));
            }
            // Keep positional workflow files in their original schema order,
            // independently of the visual widget order (including old examples).
            const orderedWidgets = () => this.widgets.filter((w) => w.serialize !== false);
            const configure = this.configure;
            this.configure = function (info) {
                if (Array.isArray(info.widgets_values)) {
                    const values = info.widgets_values;
                    const named = info.widgets_values_named;
                    info = { ...info, widgets_values: orderedWidgets().map((widget) => {
                        if (named && Object.hasOwn(named, widget.name)) return named[widget.name];
                        const index = savedOrder.indexOf(widget.name);
                        return index >= 0 && index < values.length ? values[index] : widget.value;
                    }) };
                }
                return configure.call(this, info);
            };
            const serializeMethod = this.serializeFromStoreState ? "serializeFromStoreState" : "serialize";
            const serialize = this[serializeMethod];
            this[serializeMethod] = function () {
                const data = serialize.apply(this, arguments);
                if (Array.isArray(data.widgets_values)) {
                    const widgets = orderedWidgets();
                    const values = data.widgets_values;
                    data.widgets_values = savedOrder.map((name) =>
                        values[widgets.findIndex((widget) => widget.name === name)]);
                }
                return data;
            };
            toggle.addEventListener("click", () => {
                remember();
                setOpen(!open);
            });
            watchLocale(this, () => {
                toggle.textContent = open ? t("Hide emojis", "絵文字を隠す") : t("Show emojis", "絵文字を表示");
                body.setAttribute("aria-label", t("Irodori emoji panel", "Irodori 絵文字パネル"));
                title.textContent = t("Emojis", "絵文字");
                close.textContent = t("Close", "閉じる");
                hint.textContent = t("Insert at the text cursor or replace the selection. Append if no cursor position is set.", "textのカーソル位置へ挿入。選択範囲は置換します。位置未指定なら末尾へ追加。");
                [...grid.children].forEach((button, index) => {
                    const [emoji, label, description, jaLabel, jaDescription] = EMOJIS[index];
                    button.textContent = `${emoji} ${t(label, jaLabel)}`;
                    button.title = t(description, jaDescription);
                });
            });
            close.addEventListener("click", () => setOpen(false));
            document.addEventListener("keydown", (event) => {
                if (open && event.key === "Escape") setOpen(false);
            }, { signal: controller.signal });
            const removed = this.onRemoved;
            this.onRemoved = function () {
                setOpen(false);
                controller.abort();
                return removed?.apply(this, arguments);
            };
            return result;
        };
    },
});
