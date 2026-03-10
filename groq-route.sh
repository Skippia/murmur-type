#!/bin/bash
# Add direct routes for Groq API IPs, bypassing Windscribe VPN.
# Groq uses Cloudflare anycast — these IPs are stable.
GATEWAY=$(ip route show default dev wlan0 2>/dev/null | awk '{print $3}' | head -1)
[ -z "$GATEWAY" ] && exit 0

for ip in 172.64.149.20 104.18.38.236; do
    ip route replace "$ip/32" via "$GATEWAY" dev wlan0 2>/dev/null
done
