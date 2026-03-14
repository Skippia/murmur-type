#!/usr/bin/env python3
"""murmur-type — Voice-to-text for Wayland/niri.

Modes:
  murmur-type en        — record → transcribe English → type into focused window
  murmur-type ru        — record → transcribe Russian → type into focused window
  murmur-type translate — record → transcribe → auto-detect language → translate (RU↔EN) → rofi popup
                         Select any line in rofi + Enter → save as vocabulary card
"""

import base64
import json
import os
import signal
import subprocess
import sys
import time
import uuid
import urllib.request
import urllib.error

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
RUN_DIR = os.path.join(SCRIPT_DIR, ".run")
PID_FILE = os.path.join(RUN_DIR, "recording.pid")
AUDIO_FILE = os.path.join(RUN_DIR, "recording.wav")
MODE_FILE = os.path.join(RUN_DIR, "mode")
TOKEN_FILE = os.path.join(RUN_DIR, "app_token")

DEFAULT_CONFIG = {
    "provider": "groq",
    "api_key": "",
    "model": "whisper-large-v3",
    "language": "",
    "translate_provider": "",
    "translate_api_key": "",
    "translate_model": "llama-3.3-70b-versatile",
    "webhook": None,
}

TRANSLATE_ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}
# Webhook config shape:
# {
#   "url": "https://example.com/api/words",
#   "headers": { "X-Api-Key": "..." },
#   "body": { "word": "{{word}}", "translation": "{{translation}}" },
#   "auth": {                          ← optional, for JWT login flow
#     "url": "https://example.com/api/auth/login",
#     "body": { "login": "user", "password": "pass" },
#     "token_path": "data.token"       ← dot-notation path to extract JWT
#   }
# }


def load_config():
    os.makedirs(RUN_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        notify("Config created — set api_key in\n" + CONFIG_FILE, "critical")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        cfg = {**DEFAULT_CONFIG, **json.load(f)}
    if not cfg.get("api_key"):
        notify("Set api_key in\n" + CONFIG_FILE, "critical")
        sys.exit(1)
    return cfg


def notify(msg, urgency="normal", timeout=2500):
    subprocess.run(
        ["notify-send", "-u", urgency, "-t", str(timeout),
         "-a", "murmur-type", "murmur-type", msg],
        capture_output=True,
    )


# ── Recording toggle via PID file ─────────────────────────────────────────────

def is_recording():
    if not os.path.exists(PID_FILE):
        return False
    try:
        pid = int(open(PID_FILE).read().strip())
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError, FileNotFoundError, PermissionError):
        _cleanup_pid()
        return False


def _cleanup_pid():
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass


def start_recording():
    os.makedirs(RUN_DIR, exist_ok=True)
    try:
        os.remove(AUDIO_FILE)
    except FileNotFoundError:
        pass

    proc = subprocess.Popen(
        ["pw-record", "--format", "s16", "--rate", "16000", "--channels", "1", AUDIO_FILE],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))


def stop_recording():
    try:
        pid = int(open(PID_FILE).read().strip())
        os.kill(pid, signal.SIGTERM)
        for _ in range(40):
            try:
                os.kill(pid, 0)
                time.sleep(0.05)
            except ProcessLookupError:
                break
    except (FileNotFoundError, ValueError, ProcessLookupError):
        pass
    _cleanup_pid()


def _remove_audio():
    try:
        os.remove(AUDIO_FILE)
    except FileNotFoundError:
        pass


# ── Transcription: OpenRouter ─────────────────────────────────────────────────

def transcribe_openrouter(config):
    with open(AUDIO_FILE, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode()

    lang_hint = ""
    if config.get("language"):
        lang_hint = f" The language is {config['language']}."

    prompt = "Transcribe this audio exactly as spoken. Output ONLY the transcription text, nothing else. No quotes, no labels, no markdown."

    payload = json.dumps({
        "model": config["model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt + lang_hint},
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
                ],
            }
        ],
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"].strip()


# ── Transcription: Groq ──────────────────────────────────────────────────────

def transcribe_groq(config):
    boundary = uuid.uuid4().hex
    body = b""

    body += f"--{boundary}\r\n".encode()
    body += b"Content-Disposition: form-data; name=\"model\"\r\n\r\n"
    body += config["model"].encode() + b"\r\n"

    lang = config.get("language", "")
    if lang:
        body += f"--{boundary}\r\n".encode()
        body += b"Content-Disposition: form-data; name=\"language\"\r\n\r\n"
        body += lang.encode() + b"\r\n"

    body += f"--{boundary}\r\n".encode()
    body += b"Content-Disposition: form-data; name=\"response_format\"\r\n\r\n"
    body += b"json\r\n"

    with open(AUDIO_FILE, "rb") as f:
        file_data = f.read()

    body += f"--{boundary}\r\n".encode()
    body += b"Content-Disposition: form-data; name=\"file\"; filename=\"recording.wav\"\r\n"
    body += b"Content-Type: audio/wav\r\n\r\n"
    body += file_data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "murmur-type/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
        return result.get("text", "").strip()


# ── Transcription dispatcher ──────────────────────────────────────────────────

def transcribe(config):
    if not os.path.exists(AUDIO_FILE):
        notify("No audio file found", "critical")
        return None

    file_size = os.path.getsize(AUDIO_FILE)
    if file_size < 4000:
        notify("Recording too short", "normal")
        _remove_audio()
        return None

    provider = config.get("provider", "groq")

    try:
        if provider == "groq":
            return transcribe_groq(config)
        else:
            return transcribe_openrouter(config)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")[:200]
        notify(f"API error {e.code}: {err_body}", "critical")
        return None
    except Exception as e:
        notify(f"Transcription failed: {e}", "critical")
        return None
    finally:
        _remove_audio()


# ── Translation via Groq LLM ─────────────────────────────────────────────────

def _is_cyrillic(text):
    """Check if text is predominantly Cyrillic."""
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    return cyrillic > latin


def translate_text(config, text):
    """Translate text between Russian and English (auto-detects direction).
    Returns dict {word, contextSentences, contextTranslations, source_lang} or None."""
    is_ru = _is_cyrillic(text)
    source_lang = "ru" if is_ru else "en"
    source_label = "Russian" if is_ru else "English"
    target_label = "English" if is_ru else "Russian"
    word_count = len(text.split())

    if word_count <= 3:
        prompt = (
            f'Translate the {source_label} word/phrase "{text}" to {target_label}.\n'
            f'Respond with ONLY valid JSON, no markdown, no code fences:\n'
            f'{{"word": "{target_label.lower()} translation",'
            f' "contextSentences": ["sentence 1", "sentence 2", "sentence 3"],'
            f' "contextTranslations": ["translation 1", "translation 2", "translation 3"]}}\n'
            f'Each context sentence must use the {target_label} word in a different real-world context.\n'
            f'Each contextTranslation is the {source_label} translation of the corresponding sentence.'
        )
    else:
        prompt = (
            f'Translate this {source_label} text to {target_label}.\n'
            f'Respond with ONLY valid JSON, no markdown, no code fences.\n'
            f'Use exactly this structure: {{"word": "your {target_label.lower()} translation here"}}\n'
            f'The "word" key MUST contain the full translated text.\n'
            f'Text: "{text}"'
        )

    t_provider = config.get("translate_provider") or config.get("provider", "groq")
    t_api_key = config.get("translate_api_key") or config["api_key"]
    t_endpoint = TRANSLATE_ENDPOINTS.get(t_provider, TRANSLATE_ENDPOINTS["groq"])

    payload = json.dumps({
        "model": config.get("translate_model", "llama-3.3-70b-versatile"),
        "messages": [
            {"role": "system", "content": f"You are a concise {source_label}-{target_label} translator. Always respond with valid JSON only. No markdown, no code fences, no extra text."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 500,
    }).encode()

    req = urllib.request.Request(
        t_endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {t_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "murmur-type/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            raw = result["choices"][0]["message"]["content"].strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            parsed = json.loads(raw)
            parsed["source_lang"] = source_lang
            # LLMs sometimes use alternative key names instead of "word",
            # especially for long text translations — normalize to "word"
            if not parsed.get("word"):
                for alt_key in ("translation", "text", "translated_text", "result"):
                    if parsed.get(alt_key):
                        parsed["word"] = parsed[alt_key]
                        break
            if "word" in parsed:
                if not isinstance(parsed["word"], str):
                    parsed["word"] = str(parsed["word"])
                parsed["word"] = parsed["word"].rstrip(".")
            if not parsed.get("word"):
                notify(f"Translation returned empty result", "critical")
                return None
            return parsed
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        notify(f"Translation parse error: {e}", "critical")
        return None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")[:200]
        notify(f"Translation API error {e.code}: {err_body}", "critical")
        return None
    except Exception as e:
        notify(f"Translation failed: {e}", "critical")
        return None


# ── Rofi popup ────────────────────────────────────────────────────────────────

def _pango_escape(text):
    """Escape special characters for Pango markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _underline_word(sentence, word):
    """Underline occurrences of word in sentence using Pango markup (case-insensitive)."""
    import re
    escaped = _pango_escape(sentence)
    escaped_word = _pango_escape(word)
    # Case-insensitive replace, preserving original case
    pattern = re.compile(re.escape(escaped_word), re.IGNORECASE)
    return pattern.sub(lambda m: f"<u>{m.group()}</u>", escaped)


def _visible_len(pango_text):
    """Return visible character count, stripping Pango markup tags."""
    import re
    return len(re.sub(r'<[^>]+>', '', pango_text))


def _calc_rofi_width(lines, char_px=10, padding=80, max_pct=0.92):
    """Calculate rofi window width in px based on the longest visible line."""
    max_chars = max((_visible_len(line) for line in lines), default=40)
    width = max_chars * char_px + padding
    # Cap at max_pct of primary monitor width
    try:
        out = subprocess.run(
            ["xrandr", "--query"], capture_output=True, text=True, timeout=2,
        ).stdout
        for ln in out.splitlines():
            if " connected primary" in ln or " connected" in ln:
                res = ln.split()[3 if "primary" in ln else 2].split("+")[0]
                screen_w = int(res.split("x")[0])
                return min(width, int(screen_w * max_pct))
    except Exception:
        pass
    return min(width, 2000)


def show_translation_rofi(source_text, data):
    """Show translation in rofi. Returns True if user pressed Enter (save card), False on Escape."""
    word = data.get("word", "").lower()
    source_lang = data.get("source_lang", "ru")

    if source_lang == "ru":
        src_flag, tgt_flag = "🇷🇺", "🇬🇧"
    else:
        src_flag, tgt_flag = "🇬🇧", "🇷🇺"

    lines = [
        f"{src_flag}  {_pango_escape(source_text)}",
        "",
        f"{tgt_flag}  <b>{_pango_escape(word)}</b>",
    ]

    contexts = data.get("contextSentences", [])
    translations = data.get("contextTranslations", [])

    if contexts:
        lines.append("")
        for i, ctx in enumerate(contexts):
            lines.append(f"{i+1}) {_underline_word(ctx, word)}")
            if i < len(translations):
                lines.append(f"    ↳ {_pango_escape(translations[i])}")
            lines.append("")

    lines.append("⏎  Enter = save to vocabulary  |  Esc = dismiss")

    width_px = _calc_rofi_width(lines)
    rofi_input = "\n".join(lines)

    result = subprocess.run(
        ["rofi", "-dmenu", "-p", "Translation",
         "-markup-rows", "-no-custom",
         "-theme-str", f"window {{width: {width_px}px;}}",
         "-theme-str", "listview {lines: " + str(len(lines)) + ";}",
         "-theme-str", "element {padding: 4px 12px;}"],
        input=rofi_input, capture_output=True, text=True,
    )

    return result.returncode == 0


# ── Webhook integration ───────────────────────────────────────────────────────

def _resolve_json_path(data, path):
    """Extract a value from nested dict using dot notation (e.g. 'data.token')."""
    for key in path.split("."):
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return None
    return data


def _webhook_auth(auth_cfg):
    """Authenticate via login endpoint and return Bearer token. Caches to TOKEN_FILE."""
    try:
        token = open(TOKEN_FILE).read().strip()
        if token:
            return token
    except FileNotFoundError:
        pass

    payload = json.dumps(auth_cfg.get("body", {})).encode()

    req = urllib.request.Request(
        auth_cfg["url"],
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            token_path = auth_cfg.get("token_path", "token")
            token = _resolve_json_path(result, token_path)
            if token:
                with open(TOKEN_FILE, "w") as f:
                    f.write(str(token))
                return token
            notify("Webhook auth: token not found in response", "critical")
            return None
    except Exception as e:
        notify(f"Webhook auth failed: {e}", "critical")
        return None


def _build_webhook_body(template, word, translation):
    """Replace {{word}} and {{translation}} placeholders in webhook body template."""
    def replace_value(v):
        if isinstance(v, str):
            return v.replace("{{word}}", word).replace("{{translation}}", translation)
        if isinstance(v, dict):
            return {k: replace_value(val) for k, val in v.items()}
        if isinstance(v, list):
            return [replace_value(item) for item in v]
        return v
    return replace_value(template)


def fire_webhook(config, word, translation):
    """Send word + translation to configured webhook. Returns True on success."""
    wh = config.get("webhook")
    if not wh or not wh.get("url"):
        return False

    headers = {"Content-Type": "application/json"}
    headers.update(wh.get("headers", {}))

    # Optional auth flow
    auth_cfg = wh.get("auth")
    if auth_cfg and auth_cfg.get("url"):
        token = _webhook_auth(auth_cfg)
        if not token:
            return False
        headers["Authorization"] = f"Bearer {token}"

    body_template = wh.get("body", {"word": "{{word}}", "translation": "{{translation}}"})
    body = _build_webhook_body(body_template, word, translation)
    payload = json.dumps(body).encode()

    req = urllib.request.Request(
        wh["url"], data=payload, headers=headers, method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
            return True
    except urllib.error.HTTPError as e:
        # Token expired — clear cache and retry once
        if e.code == 401 and auth_cfg:
            try:
                os.remove(TOKEN_FILE)
            except FileNotFoundError:
                pass
            token = _webhook_auth(auth_cfg)
            if not token:
                return False
            req = urllib.request.Request(
                wh["url"], data=payload,
                headers={**headers, "Authorization": f"Bearer {token}"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp.read()
                    return True
            except Exception:
                pass
        err_body = e.read().decode(errors="replace")[:200]
        notify(f"Webhook failed: {err_body}", "critical")
        return False
    except Exception as e:
        notify(f"Webhook failed: {e}", "critical")
        return False


# ── Type text into focused window ─────────────────────────────────────────────

def type_text(text):
    if not text:
        return
    old = subprocess.run(["wl-paste", "--no-newline"], capture_output=True)
    subprocess.run(["wl-copy", "--", text])
    subprocess.run([
        "wtype", "-M", "ctrl", "-M", "shift",
        "-P", "v", "-p", "v",
        "-m", "shift", "-m", "ctrl",
    ])
    time.sleep(0.15)
    subprocess.run(["wl-copy", "--", old.stdout])


# ── Main ───────────────────────────────────────────────────────────────────────

def save_mode(mode, lang):
    with open(MODE_FILE, "w") as f:
        json.dump({"mode": mode, "language": lang}, f)


def load_mode():
    try:
        with open(MODE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"mode": "type", "language": "en"}


def cleanup_mode():
    try:
        os.remove(MODE_FILE)
    except FileNotFoundError:
        pass


def main():
    config = load_config()
    arg = sys.argv[1] if len(sys.argv) > 1 else "en"

    if is_recording():
        stop_recording()
        saved = load_mode()
        config["language"] = saved["language"]
        mode = saved["mode"]

        notify("Processing...", "low")
        text = transcribe(config)

        if not text:
            notify("No text recognized", "normal")
            cleanup_mode()
            return

        if mode == "translate":
            notify("Translating...", "low")
            data = translate_text(config, text)
            if data:
                translated = data.get("word", "")
                source_lang = data.get("source_lang", "ru")
                user_wants_save = show_translation_rofi(text, data)

                if user_wants_save and config.get("webhook"):
                    notify("Saving...", "low")
                    if source_lang == "ru":
                        en_word, ru_word = translated.lower(), text.lower()
                    else:
                        en_word, ru_word = text.lower(), translated.lower()
                    ok = fire_webhook(config, en_word, ru_word)
                    if ok:
                        notify(f"Card saved: {translated}", "low")
            else:
                notify(f"Heard: {text}\n(translation failed)", "critical")
        else:
            type_text(text)
            preview = text[:60] + ("..." if len(text) > 60 else "")
            notify(f"Typed: {preview}", "low")

        cleanup_mode()
    else:
        os.makedirs(RUN_DIR, exist_ok=True)
        if arg == "translate":
            save_mode("translate", "")
            notify("Recording (RU ↔ EN)...", "low")
        else:
            save_mode("type", arg)
            label = {"en": "EN", "ru": "RU"}.get(arg, arg.upper())
            notify(f"Recording ({label})...", "low")
        start_recording()


if __name__ == "__main__":
    main()
