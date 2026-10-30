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
            setStyle(host, "minWidth", "300px");
            setStyle(host, "alignSelf", "stretch");
        }
        const nodeWidth = Number(node.size?.[0] ?? node.width ?? 0);
        const available = row
            ? Math.max(host.clientWidth || 0, host.parentElement?.clientWidth || 0)
            : Math.max(host.clientWidth || 0, nodeWidth - 2 * (widget.margin ?? 10));
        // clientWidth is in logical CSS pixels; getBoundingClientRect includes
        // graph zoom and would progressively shrink or grow the player.
        const width = Math.max(300, Math.floor(available));
        setStyle(audio, "width", `${width}px`);
        setStyle(audio, "minWidth", "300px");
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
