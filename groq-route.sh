#!/bin/bash
# Add direct routes for Groq API IPs, bypassing Windscribe VPN.
# Groq uses Cloudflare anycast — these IPs are stable.

notify() {
    local uid=$(id -u skippia 2>/dev/null)
    [ -z "$uid" ] && return
    local bus="unix:path=/run/user/${uid}/bus"
    sudo -u skippia DBUS_SESSION_BUS_ADDRESS="$bus" \
        notify-send -u "${2:-normal}" -t 3000 -a "groq-route" "murmur-type" "$1" 2>/dev/null
}

GATEWAY=$(ip route show default dev wlan0 2>/dev/null | awk '{print $3}' | head -1)
if [ -z "$GATEWAY" ]; then
    notify "Groq route: no wlan0 gateway found" critical
    exit 1
fi

FAILED=""
for ip in 172.64.149.20 104.18.38.236; do
    if ! ip route replace "$ip/32" via "$GATEWAY" dev wlan0 2>/dev/null; then
        FAILED="$FAILED $ip"
    fi
done

if [ -n "$FAILED" ]; then
    notify "Groq route failed for:$FAILED" critical
    exit 1
else
    notify "Groq API bypass active — voice typing ready" normal
    exit 0
fi
