# Integrations and Current Setup

This Home Assistant configuration enables a minimal set of core features and a
local voice assistant. Below is an overview of the configured integrations.

## Core

- **`default_config`** – loads the default set of Home Assistant integrations.
- **`frontend`** – pulls themes from `themes/` so the web UI can use custom styles.
- **`automation`**, **`script`**, and **`scene`** – include definitions from the
  respective YAML files in the repository root.

## Voice Assistant

- **Speech‑to‑Text (`stt`)** – connects to a Wyoming server running on
  `192.168.1.239:10300`.
- **Text‑to‑Speech (`tts`)** – connects to a Wyoming server on
  `192.168.1.239:10301`.
- **Assist Pipeline** – defines `local_wyoming`, a fully local pipeline using the
  above STT/TTS providers with the built‑in `homeassistant` conversation engine.

## Custom Commands

- **`rest_command.ollama_summary`** – posts text to an Ollama instance at
  `http://192.168.1.69:11434/v1/chat/completions` for summarisation.

## Custom Components

- **HACS** – the Home Assistant Community Store is available under
  `custom_components/hacs` for managing community integrations.
- **Duke Energy** – installs the official Duke Energy integration from
  `homeassistant/core` to import utility usage statistics.
