import { t, locale, watchLocale } from "./i18n.js";
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "IrodoriTTS.SaveAudioPreview",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "IrodoriTTSSaveAudio") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            const audio = document.createElement("audio");
            audio.controls = true;
            audio.preload = "metadata";
            audio.setAttribute("aria-label", t("Preview saved audio", "保存音声の試聴"));
            audio.style.cssText = "display:block;width:100%;height:54px;min-width:0;";
            const panel = document.createElement("div");
            panel.style.cssText = "box-sizing:border-box;padding:6px;width:100%;";
            panel.append(audio);
            panel.addEventListener("pointerdown", (event) => event.stopPropagation());
            panel.addEventListener("keydown", (event) => event.stopPropagation());
            const setSource = (value) => {
                const source = typeof value === "string" ? value : "";
                if (source === (audio.getAttribute("src") ?? "")) return;
                audio.pause();
                if (source) audio.src = source;
                else audio.removeAttribute("src");
                audio.load();
            };
            // Keep the audioUI name for ComfyUI's cached-output restoration, but
            // use a custom DOM type so Nodes 2.0 preserves native HTML controls.
            const widget = this.addDOMWidget("audioUI", "irodori_native_audio", panel, {
                serialize: false,
                getValue: () => audio.getAttribute("src") ?? "",
                setValue: setSource,
                getMinHeight: () => 66,
                getMaxHeight: () => 66,
            });
            widget.serialize = false;
            const executed = this.onExecuted;
            this.onExecuted = function (message) {
                executed?.apply(this, arguments);
                const file = message.audio?.[0];
                if (!file) return;
                const query = new URLSearchParams({
                    filename: file.filename,
                    subfolder: file.subfolder ?? "",
                    type: file.type ?? "output",
                });
                setSource(api.apiURL(`/view?${query}`));
            };
            const removed = this.onRemoved;
            this.onRemoved = function () {
                audio.pause();
                audio.removeAttribute("src");
                audio.load();
                return removed?.apply(this, arguments);
            };
            watchLocale(this, () => {
                audio.lang = locale();
                audio.setAttribute("aria-label", t("Preview saved audio", "保存音声の試聴"));
            });
            return result;
        };
    },
});
