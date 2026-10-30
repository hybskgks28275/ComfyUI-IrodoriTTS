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
            // Nodes 2.0 can measure DOM widgets in a shrink-to-fit flex host.
            // A percentage-only wrapper has zero intrinsic content width there.
            // Mount the native element directly and give layout a stable minimum.
            audio.style.cssText = "display:block;box-sizing:border-box;width:100%;min-width:300px;height:54px;margin:6px 0;flex:0 0 54px;align-self:stretch;";
            audio.addEventListener("pointerdown", (event) => event.stopPropagation());
            audio.addEventListener("keydown", (event) => event.stopPropagation());
            const sourceIdentity = (source) => {
                if (!source) return "";
                try {
                    const url = new URL(source, window.location.href);
                    if (url.pathname.endsWith("/view") && url.searchParams.has("filename")) {
                        return JSON.stringify([url.origin, url.pathname,
                            url.searchParams.get("filename"), url.searchParams.get("subfolder") ?? "",
                            url.searchParams.get("type") ?? "output"]);
                    }
                } catch { /* Keep non-URL sources comparable as strings. */ }
                return source;
            };
            const setSource = (value) => {
                const source = typeof value === "string" ? value : "";
                // Core cached-output restoration and onExecuted can both deliver
                // this file, with different cache-busting query parameters.
                if (sourceIdentity(source) === sourceIdentity(audio.getAttribute("src") ?? "")) return;
                audio.pause();
                if (source) audio.src = source;
                else audio.removeAttribute("src");
                audio.load();
            };
            // Keep the audioUI name for ComfyUI's cached-output restoration, but
            // use a custom DOM type so Nodes 2.0 preserves native HTML controls.
            const widget = this.addDOMWidget("audioUI", "irodori_native_audio", audio, {
                serialize: false,
                getValue: () => audio.getAttribute("src") ?? "",
                setValue: setSource,
                getMinHeight: () => 66,
                getMaxHeight: () => 66,
            });
            widget.serialize = false;
            const computeLayoutSize = widget.computeLayoutSize?.bind(widget);
            widget.computeLayoutSize = (...args) => ({
                ...computeLayoutSize?.(...args), minWidth: 300, minHeight: 66, maxHeight: 66,
            });
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
