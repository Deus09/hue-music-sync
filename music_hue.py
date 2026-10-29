"""Sync a Philips Hue BLE light's colour and brightness to computer audio."""

import asyncio
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
import HueBLE
from bleak import BleakScanner

BLOCK_SIZE = 1024
ANALYSIS_SIZE = 4096
SEND_INTERVAL = 0.10
BEAT_REFRACTORY = 0.24
MIN_WARMUP_BLOCKS = 20
SCAN_SECONDS = 12

PALETTE = [
    (0.675, 0.322),  # red
    (0.550, 0.400),  # orange
    (0.409, 0.518),  # green
    (0.170, 0.340),  # turquoise
    (0.167, 0.040),  # blue
    (0.300, 0.150),  # purple
    (0.380, 0.180),  # pink
]

_audio_lock = threading.Lock()
_audio_buffer = np.zeros(ANALYSIS_SIZE, dtype=np.float32)
_audio_sequence = 0
_window_cache = {}
_previous_spectrum = None


def audio_callback(indata, frames, timing, status):
    """Keep the audio callback lightweight; analyse audio in the main loop."""
    global _audio_buffer, _audio_sequence
    block = indata[:, 0].astype(np.float32, copy=True)
    with _audio_lock:
        if len(block) >= ANALYSIS_SIZE:
            _audio_buffer = block[-ANALYSIS_SIZE:].copy()
        else:
            _audio_buffer = np.concatenate((_audio_buffer[len(block):], block))
        _audio_sequence += 1


def find_blackhole():
    for index, device in enumerate(sd.query_devices()):
        if "blackhole" in device["name"].lower() and device["max_input_channels"] > 0:
            return index, float(device["default_samplerate"])
    return None, None


def _hann(size):
    if size not in _window_cache:
        _window_cache[size] = np.hanning(size)
    return _window_cache[size]


def analyse(samples, sample_rate):
    """Return RMS, bass, mids, treble and low-frequency spectral flux."""
    global _previous_spectrum
    samples = samples.astype(np.float64)
    samples = np.diff(samples, prepend=samples[0])  # reduce DC and rumble
    spectrum = np.abs(np.fft.rfft(samples * _hann(len(samples))))
    frequencies = np.fft.rfftfreq(len(samples), 1.0 / sample_rate)

    def band_energy(low, high):
        mask = (frequencies >= low) & (frequencies < high)
        return float(np.sqrt(np.mean(spectrum[mask] ** 2))) if np.any(mask) else 0.0

    rms = float(np.sqrt(np.mean(samples * samples)))
    bass = band_energy(40, 160)
    mids = band_energy(160, 2000)
    treble = band_energy(2000, min(8000, sample_rate / 2))

    if _previous_spectrum is not None and len(_previous_spectrum) == len(spectrum):
        mask = (frequencies >= 40) & (frequencies < min(400, sample_rate / 2))
        differences = spectrum[mask] - _previous_spectrum[mask]
        flux = float(np.sum(differences[differences > 0]))
    else:
        flux = 0.0
    _previous_spectrum = spectrum.copy()
    return rms, bass, mids, treble, flux


def _device_label(device):
    name = device.name or "Unnamed Bluetooth device"
    return f"{name} — {device.address}"


async def discover_hue_device():
    """Find Hue by advertised name, or let the user choose from scan results."""
    print(f"\nBluetooth cihazları taranıyor ({SCAN_SECONDS} saniye)...")
    devices = await BleakScanner.discover(timeout=SCAN_SECONDS)
    if not devices:
        print("Bluetooth cihazı bulunamadı. Lambanın açık ve yakında olduğundan emin olun.")
        return None

    hue_matches = [
        device for device in devices
        if any(token in (device.name or "").lower() for token in ("hue", "iris", "philips"))
    ]

    if len(hue_matches) == 1:
        chosen = hue_matches[0]
        print(f"Hue benzeri cihaz bulundu: {_device_label(chosen)}")
        return chosen

    if len(hue_matches) > 1:
        candidates = hue_matches
        print("Birden fazla Hue/Philips benzeri cihaz bulundu:")
    else:
        candidates = devices
        print(
            "Tarama adında Hue/Iris görünmedi. Bazı lambalar Bluetooth adını yayınlamaz.\n"
            "Lütfen Hue Iris'e ait cihazı listeden seçin:"
        )

    for index, device in enumerate(candidates, start=1):
        print(f"  {index}. {_device_label(device)}")

    while True:
        try:
            answer = input("Cihaz numarası (çıkmak için Enter): ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not answer:
            return None
        try:
            number = int(answer)
        except ValueError:
            print("Lütfen listeden bir numara girin.")
            continue
        if 1 <= number <= len(candidates):
            return candidates[number - 1]
        print("Bu numara listede yok.")


async def connect_light(retries=3):
    for attempt in range(1, retries + 1):
        device = await discover_hue_device()
        if device is None:
            return None
        light = HueBLE.HueBleLight(device)
        try:
            print(f"Bluetooth bağlantısı kuruluyor ({attempt}/{retries})...")
            await light.connect()
            return light
        except Exception as exc:
            print(f"Bağlantı kurulamadı: {type(exc).__name__}: {exc}")
            try:
                await light.disconnect()
            except Exception:
                pass
            if attempt < retries:
                print("Tekrar denenecek...")
                await asyncio.sleep(2)
    return None


async def main():
    global _audio_sequence
    audio_device, sample_rate = find_blackhole()
    if audio_device is None:
        print("BlackHole 2ch bulunamadı. Kurun ve macOS ses çıkışını BlackHole içeren Multi-Output Device yapın.")
        return
    print(f"Ses cihazı #{audio_device}, örnekleme hızı={sample_rate:.0f} Hz")

    light = await connect_light()
    if light is None:
        print("Hue bağlantısı kurulamadı; program kapatılıyor.")
        return

    connected = True
    try:
        await light.set_power(True, transition_ms=0)
        bass_floor = None
        rms_history = deque(maxlen=200)
        flux_history = deque(maxlen=30)
        colour_index = 5
        last_beat = 0.0
        last_send = 0.0
        last_sequence = -1
        last_brightness = 100
        beat_until = 0.0
        warmup = 0
        smoothed_rms = 0.0

        print("\nMüzik senkronizasyonu başladı.")
        print("YouTube veya başka bir uygulamada müzik açın.")
        print("Durdurmak için Ctrl+C — çıkışta ışık kapatılmaya çalışılır.\n")

        with sd.InputStream(
            device=audio_device,
            channels=1,
            samplerate=sample_rate,
            blocksize=BLOCK_SIZE,
            dtype="float32",
            latency="low",
            callback=audio_callback,
        ):
            while True:
                await asyncio.sleep(0.006)
                with _audio_lock:
                    sequence = _audio_sequence
                    samples = _audio_buffer.copy()
                if sequence == last_sequence:
                    continue
                last_sequence = sequence

                now = time.monotonic()
                rms, bass, mids, treble, flux = analyse(samples, sample_rate)
                smoothed_rms = 0.55 * smoothed_rms + 0.45 * rms
                rms_history.append(rms)
                flux_history.append(flux)

                if bass_floor is None:
                    bass_floor = max(bass, 1e-4)
                if warmup < MIN_WARMUP_BLOCKS:
                    warmup += 1
                    bass_floor = 0.7 * bass_floor + 0.3 * bass
                    continue

                flux_median = float(np.median(flux_history))
                flux_mad = float(np.median(np.abs(np.asarray(flux_history) - flux_median)))
                threshold = flux_median + 2.5 * max(flux_mad, 1e-6)
                beat = flux > threshold and rms > 0.002 and now - last_beat > BEAT_REFRACTORY
                if beat:
                    last_beat = now
                    beat_until = now + 0.12
                    colour_index = (colour_index + 1) % len(PALETTE)

                bass_floor = 0.97 * bass_floor + 0.03 * bass
                rms_p90 = (
                    float(np.percentile(np.asarray(rms_history), 90))
                    if len(rms_history) >= 30 else max(smoothed_rms, 1e-4)
                )
                normalised = min(smoothed_rms / max(rms_p90, 1e-6), 1.2)
                target_brightness = int(np.clip(60 + 140 * normalised, 60, 200))
                if treble > mids * 1.5 and treble > 0.001:
                    target_brightness = min(target_brightness + 30, 240)
                if now < beat_until:
                    target_brightness = 245

                colour = PALETTE[colour_index]
                if now - last_send >= SEND_INTERVAL and (
                    beat or abs(target_brightness - last_brightness) >= 10 or now - last_send >= 0.4
                ):
                    try:
                        await light.set_colour_effect(
                            float(colour[0]), float(colour[1]), int(target_brightness),
                            HueBLE.EffectType.NONE, 0, transition_ms=0,
                        )
                        last_brightness = target_brightness
                        last_send = time.monotonic()
                    except Exception as exc:
                        print(f"Bluetooth komut hatası: {type(exc).__name__}: {exc}")
                        raise

    except asyncio.CancelledError:
        raise
    except KeyboardInterrupt:
        print("\nSenkronizasyon durduruluyor...")
    except Exception as exc:
        print(f"Program hatası: {type(exc).__name__}: {exc}")
    finally:
        if connected:
            print("Işık kapatılıyor...")
            try:
                await light.set_power(False)
                await asyncio.sleep(0.5)
                print("Kapatma komutu gönderildi.")
            except Exception as exc:
                print(f"Işık kapatılamadı: {type(exc).__name__}: {exc}")
            try:
                await light.disconnect()
            except Exception as exc:
                print(f"Bluetooth bağlantısı kapatılamadı: {exc}")
        print("Program sonlandı.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
