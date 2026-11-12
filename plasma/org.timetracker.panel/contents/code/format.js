// Turns an /api/status response into what the panel widget shows. Plain
// functions with no QML dependencies, so they can also be run under node.
// Only whole minutes are shown: time left is rounded up, elapsed time down.

function minutesText(minutes) {
    if (minutes < 60) return minutes + "m";
    var rest = minutes % 60;
    return Math.floor(minutes / 60) + "h " + (rest < 10 ? "0" : "") + rest + "m";
}

function durationText(seconds) {
    return minutesText(Math.round(seconds / 60));
}

function totalsText(today) {
    return durationText(today.counted_s) + " counted of " + durationText(today.target_s)
        + " (" + Math.round(100 * today.progress) + "%), distraction " + durationText(today.distraction_s);
}

// status: decoded /api/status response. sinceFetchSeconds: age of that response.
// Returns {kind, text, tooltip}; kind is one of work, overrun, break,
// distraction, idle, signedoff.
function describe(status, sinceFetchSeconds) {
    var totals = totalsText(status.today);
    var active = status.active;
    if (!active) {
        if (status.today.signed_off_at) {
            return { kind: "signedoff", text: "signed off", tooltip: totals };
        }
        var sessions = status.today.sessions;
        if (sessions.length === 0) {
            return { kind: "idle", text: "no session", tooltip: totals };
        }
        var lastEnd = Date.parse(sessions[sessions.length - 1].end);
        var idle = (Date.parse(status.now) - lastEnd) / 1000 + sinceFetchSeconds;
        return { kind: "idle", text: "idle " + minutesText(Math.floor(idle / 60)), tooltip: totals };
    }
    var label = active.label ? " · " + active.label : "";
    var tooltip = (active.label ? active.label + "\n" : "") + totals;
    if (active.type === "distraction") {
        var elapsed = status.elapsed_s + sinceFetchSeconds;
        return { kind: "distraction", text: "distraction " + minutesText(Math.floor(elapsed / 60)) + label, tooltip: tooltip };
    }
    var remaining = status.remaining_s - sinceFetchSeconds;
    if (active.type === "break") {
        return { kind: "break", text: "break " + minutesText(Math.max(0, Math.ceil(remaining / 60))) + " left", tooltip: tooltip };
    }
    if (remaining <= -60) {
        return { kind: "overrun", text: "+" + minutesText(Math.floor(-remaining / 60)) + " over" + label, tooltip: tooltip };
    }
    if (remaining < 0) {
        return { kind: "overrun", text: "time's up" + label, tooltip: tooltip };
    }
    return { kind: "work", text: minutesText(Math.ceil(remaining / 60)) + " left" + label, tooltip: tooltip };
}
