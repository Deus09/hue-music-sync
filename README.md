# Hue Music Sync

Sync a compatible Philips Hue Bluetooth light with the music playing on your Mac. The program analyses system audio and changes the light's colour and brightness in time with the beat.

> **Status:** Personal/community project. Tested in one macOS setup with a Philips Hue Iris over Bluetooth. Other Hue models and operating systems may behave differently.

## Features

- Discovers nearby Bluetooth devices at startup; no UUID editing required.
- Automatically selects a uniquely advertised Hue/Philips/Iris device when possible.
- If the light's Bluetooth name is hidden or several candidates are found, displays a list so you can select the right device.
- Analyses audio from BlackHole and uses spectral flux for beat/onset detection.
- Attempts to turn the light off when stopped with `Ctrl+C`.

## Requirements

- macOS with Bluetooth enabled (the current setup has been tested on macOS).
- A Hue Bluetooth-compatible light, switched on and within range.
- Python 3.10 or newer recommended.
- [BlackHole 2ch](https://existential.audio/blackhole/) for capturing system audio.

A Hue Bridge is not used by this project. Bluetooth support and the HueBLE library's compatibility may vary by light model and OS.

## Setup on macOS

### 1. Install BlackHole

Install BlackHole 2ch using the instructions on its official website. Open **Audio MIDI Setup** and create a **Multi-Output Device** containing both your normal audio output (for example, Mac speakers) and **BlackHole 2ch**. Select that Multi-Output Device as macOS's sound output so you can hear the music while the program analyses it.

### 2. Download this project

Clone the repository, or download it as a ZIP from GitHub and extract it.

```bash
git clone https://github.com/OWNER/hue-music-sync.git
cd hue-music-sync
```

Replace `OWNER` with the repository owner's GitHub username if cloning from your own fork.

### 3. Create the environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run

```bash
python music_hue.py
```

Keep the Hue light switched on. The program scans for nearby Bluetooth devices. If it cannot identify the light by its advertised name, choose the matching device number from the list. You do not need to copy or edit a Bluetooth UUID.

Play music in your browser or another app. To stop, return to Terminal and press **Control+C**. The program will attempt to turn off the light before disconnecting. If Bluetooth has already disconnected, it may not be able to deliver the off command.

## Troubleshooting

- **BlackHole not found:** confirm it is installed and appears as an input device in Audio MIDI Setup / `sounddevice`.
- **No Hue device found:** turn the light on, move the Mac closer, close apps that may be controlling the light, and run the scan again. Some devices do not advertise a readable name, so select carefully from the scan list.
- **macOS pairing message:** the BLE library may print that manual pairing is unsupported. Follow macOS Bluetooth prompts if shown; behaviour depends on the Hue model and macOS version.
- **No music response:** ensure macOS output is set to the Multi-Output Device containing BlackHole and your speakers/headphones.
- **Light does not turn off on exit:** the off command requires a working Bluetooth connection. Use the Hue app or physical control if the device is no longer reachable.

## Privacy

This application analyses local audio samples to estimate rhythm and loudness. It does not upload audio or send it to a server.

## Safety and limitations

This is an unofficial community project and is not affiliated with or endorsed by Signify/Philips Hue. Bluetooth identifiers, advertised device names, and support can vary between systems. Use at your own risk.

## License

MIT — see [LICENSE](LICENSE).
