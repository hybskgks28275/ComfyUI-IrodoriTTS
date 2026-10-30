/** Keep native media controls in sync with the DOM host used by both renderers. */
export function installNativeAudioLayout(node, widget, env = globalThis) {
    const audio = widget.element;
    const requestFrame = env.requestAnimationFrame?.bind(env) ?? ((fn) => env.setTimeout(fn, 0));
    const cancelFrame = env.cancelAnimationFrame?.bind(env) ?? env.clearTimeout?.bind(env);
    let frame = null;
    let disposed = false;
    let host = null;
    let row = null;
    const resize = env.ResizeObserver ? new env.ResizeObserver(() => schedule()) : null;
    const mutations = env.MutationObserver ? new env.MutationObserver(() => schedule()) : null;
    const setStyle = (element, name, value) => {
        if (element?.style[name] !== value) element.style[name] = value;
    };
    function sync() {
        if (disposed || !audio.isConnected || !audio.parentElement) return;
        const parent = audio.parentElement;
        const vueRow = parent.closest?.(".lg-node-widget");
        if (host !== parent || row !== vueRow) {
            host = parent;
            row = vueRow;
            resize?.disconnect();
            resize?.observe(audio);
            resize?.observe(host);
            if (row) resize?.observe(row);
        }
        // A Vue host may retain a narrow measurement even though the widget row
        // spans the full node. Repair only this widget's own host, not the node
        // or any clipping used to hide widgets behind other nodes.
        if (row) {
            setStyle(host, "width", "100%");
            setStyle(host, "minWidth", "0px");
            setStyle(host, "maxWidth", "100%");
            setStyle(host, "boxSizing", "border-box");
            setStyle(host, "contain", "inline-size");
            setStyle(host, "alignSelf", "stretch");
        }
        const contentWidth = (element) => {
            if (!element) return 0;
            const style = env.getComputedStyle?.(element);
            const padding = (parseFloat(style?.paddingLeft) || 0) + (parseFloat(style?.paddingRight) || 0);
            return Math.max(0, (element.clientWidth || 0) - padding);
        };
        // The host contains the player, so its measured width can contain our
        // previous width. Never take the maximum of those two dependent sizes.
        // Inline-size containment breaks that feedback in the Vue grid, while
        // the node's logical width is an independent upper bound in both modes.
        const nodeWidth = Number(node.size?.[0] ?? node.width ?? 0);
        const nodeLimit = Math.max(0, nodeWidth - 2 * (widget.margin ?? 10));
        const measured = row ? contentWidth(host.parentElement) : contentWidth(host);
        const available = measured > 0 ? measured : nodeLimit;
        const width = Math.floor(nodeLimit > 0 ? Math.min(available, nodeLimit) : available);
        if (width <= 0) return; // Detached/hidden nodes are measured again on reveal.
        setStyle(audio, "width", `${width}px`);
        setStyle(audio, "minWidth", "0px");
        setStyle(audio, "maxWidth", "100%");
        setStyle(audio, "height", "54px");
        setStyle(audio, "flex", "0 0 54px");
    }
    function schedule() {
        if (disposed || frame !== null) return;
        frame = requestFrame(() => {
            frame = null;
            sync();
        });
    }
    // The second frame also covers Vue moving the element after onExecuted.
    function refresh() {
        sync();
        schedule();
    }
    mutations?.observe(audio, { attributes: true, attributeFilter: ["style", "class"] });
    const events = ["loadstart", "loadedmetadata", "canplay", "emptied"];
    for (const event of events) audio.addEventListener(event, refresh);
    const afterResize = widget.options.afterResize;
    widget.options.afterResize = function (...args) {
        afterResize?.apply(this, args);
        refresh();
    };
    refresh();
    return {
        refresh,
        dispose() {
            disposed = true;
            if (frame !== null) cancelFrame?.(frame);
            frame = null;
            resize?.disconnect();
            mutations?.disconnect();
            for (const event of events) audio.removeEventListener(event, refresh);
            widget.options.afterResize = afterResize;
        },
    };
}
