# voice-type

Voice-to-text toolkit for Wayland compositors (niri, sway, Hyprland). Speak into your mic, get text typed into the focused window — or translate Russian words to English with a popup dictionary.

Zero Python dependencies. Uses only the standard library.

## Features

- **Voice → Type**: Press a hotkey, speak, press again — transcribed text is typed into the focused window (any editor, terminal, browser)
- **Voice Translate (RU → EN)**: Say a Russian word or phrase, see the English translation with 3 context examples in a rofi popup. The translated word is **underlined** in each example sentence
- **Vocabulary Integration**: Press Enter in the translation popup to save the word as a flashcard to your vocabulary app (optional)
- **Multi-language**: Separate hotkeys for English and Russian transcription
- **Toggle design**: One hotkey starts recording, same hotkey stops and processes — no daemon needed

## How It Works

```
┌──────────┐    ┌─────────────┐    ┌──────────┐    ┌─────────┐
│ Mic      │───→│ pw-record   │───→│ Groq     │───→│ wtype   │
│ (hotkey) │    │ (PipeWire)  │    │ Whisper  │    │ (type)  │
└──────────┘    └─────────────┘    └──────────┘    └─────────┘

Translate mode:
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────┐    ┌──────────┐
│ Mic      │───→│ Whisper  │───→│ LLM      │───→│ rofi │───→│ App API  │
│ (hotkey) │    │ (STT)    │    │ (translate)│   │ popup│    │ (save)   │
└──────────┘    └──────────┘    └──────────┘    └──────┘    └──────────┘
```

## Screenshots

### Voice Translate popup (rofi)
The translated word is highlighted with underline in each context sentence:

```
🇷🇺  выдержка

🇬🇧  endurance

1) His endurance was tested during the marathon.
    ↳ Его выдержка была проверена во время марафона.

2) The job requires both patience and endurance.
    ↳ Работа требует как терпения, так и выдержки.

3) She showed remarkable endurance under pressure.
    ↳ Она проявила замечательную выдержку под давлением.

⏎  Enter = save to vocabulary  |  Esc = dismiss
```

## Requirements

- **Linux** with **Wayland** (tested on niri + Arch Linux)
- **Python 3.10+** (stdlib only, no pip packages)
- **PipeWire** — `pw-record` for microphone capture
- **wtype** — types text into the focused Wayland window
- **rofi** — popup for translate mode
- **notify-send** — desktop notifications
- **Groq API key** (free) — for Whisper speech-to-text and LLM translation

### Install dependencies (Arch Linux)

```bash
sudo pacman -S python pipewire wtype rofi libnotify
```

### Get a Groq API key

1. Go to https://console.groq.com/keys
2. Sign up (free, Google/GitHub login)
3. Create an API key

## Installation

```bash
# Clone the repo
git clone https://github.com/AStepanov/voice-type.git
cd voice-type

# Run the installer
./install.sh

# Edit config with your API key
nano config.json
```

The installer:
- Creates a symlink `~/.local/bin/voice-type` → `voice-type.py`
- Copies `config.example.json` → `config.json` (if not exists)
- Checks that all dependencies are installed

### Manual installation

```bash
# 1. Clone anywhere
git clone https://github.com/AStepanov/voice-type.git ~/voice-type

# 2. Create config
cp config.example.json config.json
# Edit config.json — at minimum set "api_key"

# 3. Symlink to PATH
ln -s ~/voice-type/voice-type.py ~/.local/bin/voice-type

# 4. Make sure ~/.local/bin is in your PATH
```

## Configuration

Edit `config.json`:

```json
{
  "provider": "groq",
  "api_key": "gsk_YOUR_KEY_HERE",
  "model": "whisper-large-v3",
  "language": "",
  "translate_model": "llama-3.3-70b-versatile",
  "app_url": "http://localhost:3009",
  "app_login": "",
  "app_password": "",
  "app_topic_id": ""
}
```

### Required fields

| Field | Description |
|-------|-------------|
| `provider` | `"groq"` (recommended) or `"openrouter"` |
| `api_key` | Your Groq API key (`gsk_...`) |
| `model` | Whisper model: `"whisper-large-v3"` (best accuracy) or `"whisper-large-v3-turbo"` (faster) |

### Optional fields

| Field | Description |
|-------|-------------|
| `language` | Default language hint. Leave `""` for auto-detect, or set `"en"`, `"ru"`, `"uk"`, etc. |
| `translate_model` | LLM for translation. Default: `"llama-3.3-70b-versatile"` |
| `app_url` | Backend URL for vocabulary integration (optional) |
| `app_login` | Login for vocabulary app (optional) |
| `app_password` | Password for vocabulary app (optional) |
| `app_topic_id` | UUID of the vocabulary topic to save cards to (optional) |

## Keybindings

Add these to your compositor config. Examples below for different compositors:

### niri (`~/.config/niri/config.kdl`)

```kdl
binds {
    Mod+Shift+E  hotkey-overlay-title="Voice-to-text (English)"   { spawn "voice-type" "en"; }
    Mod+Shift+R  hotkey-overlay-title="Voice-to-text (Russian)"   { spawn "voice-type" "ru"; }
    Mod+Shift+A  hotkey-overlay-title="Voice translate (RU → EN)"  { spawn "voice-type" "translate"; }
}
```

### sway (`~/.config/sway/config`)

```
bindsym $mod+Shift+e exec voice-type en
bindsym $mod+Shift+r exec voice-type ru
bindsym $mod+Shift+a exec voice-type translate
```

### Hyprland (`~/.config/hypr/hyprland.conf`)

```
bind = $mainMod SHIFT, E, exec, voice-type en
bind = $mainMod SHIFT, R, exec, voice-type ru
bind = $mainMod SHIFT, A, exec, voice-type translate
```

## Usage

### Voice → Type (English)

1. Press **Mod+Shift+E** — notification "Recording (EN)..."
2. Speak in English
3. Press **Mod+Shift+E** again — notification "Processing..."
4. Transcribed text is typed into the focused window

### Voice → Type (Russian)

Same as above but with **Mod+Shift+R**.

### Voice Translate (RU → EN)

1. Press **Mod+Shift+A** — notification "Recording (RU → EN)..."
2. Say a Russian word or phrase
3. Press **Mod+Shift+A** again
4. A rofi popup appears with:
   - The Russian word you said
   - English translation (bold)
   - 3 example sentences with the word underlined
   - Russian translation for each example
5. **Enter** — saves as a vocabulary card (if app is configured)
6. **Escape** — dismiss

## VPN Split-Tunnel

If you use a VPN (e.g., Windscribe) that routes through datacenter IPs, Groq will block your requests with a 403 error. The included `groq-route.sh` script adds direct routes for Groq's Cloudflare IPs, bypassing the VPN tunnel.

```bash
# Install as a systemd service (persists across reboots)
sudo cp groq-route.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now groq-route.service
```

This only affects traffic to Groq's API IPs (`172.64.149.20`, `104.18.38.236`). All other traffic continues through your VPN.

## File Structure

```
voice-type/
├── voice-type.py          # Main script (single file, stdlib only)
├── config.json            # Your config (gitignored)
├── config.example.json    # Config template
├── install.sh             # Installer script
├── groq-route.sh          # VPN split-tunnel route script
├── groq-route.service     # Systemd unit for persistent routes
├── .run/                  # Runtime data (gitignored, auto-created)
│   ├── recording.pid      # PID of pw-record process
│   ├── recording.wav      # Temporary audio file
│   ├── mode               # Current recording mode
│   └── app_token          # Cached JWT token for app API
└── README.md
```

## Vocabulary Integration (Optional)

If you have a REST API backend for vocabulary flashcards (e.g., a NestJS app), voice-type can save translated words as cards.

Configure these fields in `config.json`:

```json
{
  "app_url": "http://localhost:3009",
  "app_login": "your_login",
  "app_password": "your_password",
  "app_topic_id": "uuid-of-your-topic"
}
```

The app API must support:
- `POST /api/auth/login` — returns `{ data: { token: "jwt..." } }`
- `POST /api/vocabulary/words` — creates a card with `{ topicId, word, translation }`

Leave these fields empty to use voice-type without vocabulary integration.

## Troubleshooting

### 403 error from Groq
Your IP is blocked (datacenter/VPN). See [VPN Split-Tunnel](#vpn-split-tunnel) section.

### "Recording too short"
You pressed the hotkey twice too fast. Hold for at least 1 second.

### No sound captured
Check that PipeWire is running and your mic is the default source:
```bash
pw-record --list-targets
```

### wtype doesn't work
Make sure you're on Wayland (not XWayland). Some apps (e.g., Electron with `--disable-gpu`) may not receive wtype input.

## License

MIT
