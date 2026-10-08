import { app } from "../../scripts/app.js";
import { installNumericRepeat } from "./numeric_repeat_core.js";
import { installDOMNumericRepeat } from "./numeric_repeat_dom.js";

app.registerExtension({
    name: "IrodoriTTS.NumericPressAndHold",
    setup() {
        installDOMNumericRepeat({ readOnly: () => !!app.canvas?.read_only });
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "IrodoriTTSGenerate") return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            const disposers = (this.widgets ?? []).map(installNumericRepeat);
            const onRemoved = this.onRemoved;
            this.onRemoved = function () {
                disposers.forEach((dispose) => dispose());
                return onRemoved?.apply(this, arguments);
            };
            return result;
        };
    },
});
