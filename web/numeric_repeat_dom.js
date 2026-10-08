// Nodes 2.0 uses Vue buttons, bypassing LiteGraph's widget.onPointerDown.
// Repeat the native click so Vue keeps control of steps, limits and serialization.
export function installDOMNumericRepeat({ root = document, host = window, readOnly = () => false } = {}) {
    let stopActive;
    let blockedButton;
    let blockTimer;
    let nativeClick = false;
    const clearBlock = () => {
        clearTimeout(blockTimer);
        blockedButton = undefined;
    };
    const onClick = (event) => {
        if (!nativeClick && event.detail > 0 && blockedButton?.contains(event.target)) {
            event.preventDefault();
            event.stopImmediatePropagation();
        }
    };
    const onDown = (event) => {
        stopActive?.();
        clearBlock();
        if (event.button !== 0 || event.isPrimary === false || readOnly()) return;
        const button = event.target.closest?.('button[data-testid="increment"], button[data-testid="decrement"]');
        if (!button?.closest('[node-type="IrodoriTTSGenerate"]')) return;
        const input = button.parentElement.querySelector('input[role="spinbutton"]');
        const usable = () => button.isConnected && !button.disabled && input?.isConnected
            && !input.disabled && !input.readOnly && !root.hidden && !readOnly();
        if (!usable()) return;

        // Handle this pointer gesture here; leave keyboard clicks and text editing native.
        event.preventDefault();
        event.stopImmediatePropagation();
        blockedButton = button;
        let timer;
        let stopped = false;
        const stop = () => {
            if (stopped) return;
            stopped = true;
            clearTimeout(timer);
            for (const name of ["pointerup", "pointercancel", "blur"]) host.removeEventListener(name, stop, { capture: true });
            host.removeEventListener("pointermove", onMove, { capture: true });
            host.removeEventListener("keydown", onKey, { capture: true });
            root.removeEventListener("visibilitychange", onVisibility);
            // Suppress the physical click following pointerup, but never a future gesture.
            blockTimer = setTimeout(clearBlock, 500);
            stopActive = undefined;
        };
        const onMove = (move) => {
            if (move.pointerId !== event.pointerId) return;
            const rect = button.getBoundingClientRect();
            if (!(move.buttons & 1) || move.clientX < rect.left || move.clientX > rect.right
                || move.clientY < rect.top || move.clientY > rect.bottom) stop();
        };
        const onKey = (key) => { if (key.key === "Escape") stop(); };
        const onVisibility = () => { if (root.hidden) stop(); };
        const advance = () => {
            if (stopped || !usable()) { stop(); return false; }
            try {
                nativeClick = true;
                button.click();
            } catch (error) {
                stop();
                throw error;
            } finally {
                nativeClick = false;
            }
            return true;
        };
        const repeat = () => { if (advance()) timer = setTimeout(repeat, 75); };
        stopActive = stop;
        for (const name of ["pointerup", "pointercancel", "blur"]) host.addEventListener(name, stop, true);
        host.addEventListener("pointermove", onMove, true);
        host.addEventListener("keydown", onKey, true);
        root.addEventListener("visibilitychange", onVisibility);
        if (advance()) timer = setTimeout(repeat, 350);
    };
    root.addEventListener("pointerdown", onDown, true);
    root.addEventListener("click", onClick, true);
    return () => {
        stopActive?.();
        clearBlock();
        root.removeEventListener("pointerdown", onDown, { capture: true });
        root.removeEventListener("click", onClick, { capture: true });
    };
}
