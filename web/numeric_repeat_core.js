// Keep native number-widget steps, bounds and callbacks; add only press-and-hold.
export function installNumericRepeat(widget) {
    if (widget.type !== "number" || typeof widget.incrementValue !== "function"
        || typeof widget.decrementValue !== "function") return () => {};

    const previous = widget.onPointerDown;
    let stopActive;
    widget.onPointerDown = function (pointer, currentNode, canvas) {
        stopActive?.();
        const event = pointer.eDown;
        const width = this.width || currentNode.size[0];
        const x = event?.canvasX - currentNode.pos[0];
        const direction = x >= 15 && x < 40 ? -1 : x > width - 40 && x <= width - 15 ? 1 : 0;
        if (event?.button !== 0 || !direction || this.disabled || this.computedDisabled
            || canvas.read_only || !currentNode.graph) {
            return previous?.apply(this, arguments) ?? false;
        }

        const graph = currentNode.graph;
        let timer;
        let stopped = false;
        const stop = () => {
            if (stopped) return;
            stopped = true;
            clearTimeout(timer);
            for (const name of ["pointerup", "pointercancel", "blur", "pointerdown"])
                window.removeEventListener(name, stop, true);
            window.removeEventListener("keydown", onKey, true);
            document.removeEventListener("visibilitychange", onVisibility);
            graph.afterChange?.();
            stopActive = undefined;
        };
        const onKey = (e) => { if (e.key === "Escape") stop(); };
        const onVisibility = () => { if (document.hidden) stop(); };
        const advance = () => {
            if (stopped) return false;
            if (!pointer.isDown || currentNode.graph !== graph || canvas.graph !== graph
                || this.disabled || this.computedDisabled || canvas.read_only) {
                stop();
                return false;
            }
            const before = this.value;
            try {
                const options = { e: event, node: currentNode, canvas };
                if (direction > 0) this.incrementValue(options);
                else this.decrementValue(options);
                currentNode.setDirtyCanvas(true, true);
            } catch (error) {
                stop();
                throw error;
            }
            if (this.value === before) {
                stop();
                return false;
            }
            return true;
        };
        const repeat = () => { if (advance()) timer = setTimeout(repeat, 75); };

        // Owning the pointer prevents a second increment on release or a value prompt.
        pointer.onClick = () => {};
        pointer.onDoubleClick = () => {};
        pointer.onDragStart = () => {};
        pointer.onDrag = (move) => {
            const moveX = move.canvasX - currentNode.pos[0];
            const inside = direction < 0 ? moveX >= 15 && moveX < 40
                : moveX > width - 40 && moveX <= width - 15;
            if (!inside || Math.abs(move.canvasY - event.canvasY) > 12) stop();
        };
        pointer.onDragEnd = stop;
        pointer.finally = () => { stop(); canvas.node_widget = null; };
        stopActive = stop;
        graph.beforeChange?.();
        for (const name of ["pointerup", "pointercancel", "blur", "pointerdown"])
            window.addEventListener(name, stop, true);
        window.addEventListener("keydown", onKey, true);
        document.addEventListener("visibilitychange", onVisibility);
        if (advance()) timer = setTimeout(repeat, 350);
        return true;
    };
    return () => {
        stopActive?.();
        widget.onPointerDown = previous;
    };
}
