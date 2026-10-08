import { t, watchLocale } from "./i18n.js";
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "IrodoriTTS.ReleaseMemory",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "IrodoriTTSGenerate") return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            const panel = document.createElement("div");
            panel.style.cssText = "box-sizing:border-box;padding:6px;font:12px sans-serif;color:var(--input-text,#ddd);";
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = t("Release memory", "メモリ解放");
            button.title = t("Release the TTS model and codec shared by all Irodori Generate nodes without generating audio.", "全Irodori Generateノードで共有するTTSモデルとコーデックを解放します。音声生成は行いません。");
            button.style.cssText = "width:100%;padding:6px;cursor:pointer;color:inherit;background:var(--comfy-input-bg,#333);border:1px solid #666;border-radius:4px;";
            const status = document.createElement("div");
            status.setAttribute("role", "status");
            status.style.cssText = "margin-top:5px;overflow-wrap:anywhere;";
            let statusMessage = () => "";
            const setStatus = (message) => {
                statusMessage = message;
                status.textContent = message();
            };
            panel.append(button, status);
            panel.addEventListener("pointerdown", (event) => event.stopPropagation());
            button.addEventListener("click", async (event) => {
                event.stopPropagation();
                if (button.disabled || app.canvas?.read_only) return;
                button.disabled = true;
                setStatus(() => t("Releasing…", "解放中…"));
                try {
                    const response = await api.fetchApi("/irodori_tts/release", { method: "POST" });
                    const data = await response.json();
                    if (response.status === 409 && data.status === "busy") {
                        setStatus(() => t("Generation or loading is in progress. Wait for completion or cancel before retrying.", "生成・読込中です。完了またはキャンセル後に押してください。"));
                    } else if (!response.ok) {
                        throw new Error(`${response.status} ${response.statusText}`);
                    } else if (data.status === "released") {
                        setStatus(() => t("Released the model and codec.", "モデルとコーデックを解放しました。"));
                    } else if (data.status === "empty") {
                        setStatus(() => t("No model is currently cached.", "保持中のモデルはありません。"));
                    } else {
                        throw new Error(t("Invalid server response.", "サーバーからの応答が不正です。"));
                    }
                } catch (error) {
                    setStatus(() => `${t("Failed to release memory", "解放に失敗しました")}: ${error.message}`);
                } finally {
                    button.disabled = false;
                }
            });
            this.addDOMWidget("irodori_release_memory", "irodori_release_memory", panel, {
                serialize: false,
                getMinHeight: () => 90,
                getMaxHeight: () => 90,
            });
            watchLocale(this, () => {
                button.textContent = t("Release memory", "メモリ解放");
                button.title = t("Release the TTS model and codec shared by all Irodori Generate nodes without generating audio.", "全Irodori Generateノードで共有するTTSモデルとコーデックを解放します。音声生成は行いません。");
                status.textContent = statusMessage();
            });
            return result;
        };
    },
});
