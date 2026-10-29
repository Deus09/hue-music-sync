    return None


async def main():
    global _audio_sequence
    audio_device, sample_rate = find_blackhole()
    if audio_device is None:
        print("BlackHole 2ch was not found. Install it and set macOS audio output to a Multi-Output Device that includes BlackHole.")
        return
    print(f"Audio device #{audio_device}, sample rate={sample_rate:.0f} Hz")

    light = await connect_light()
    if light is None:
        print("Could not connect to the Hue light. Exiting.")
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

        print("\nMusic synchronization started.")
        print("Play music in YouTube or another app.")
        print("Press Ctrl+C to stop — the light will be turned off on exit if possible.\n")

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
                        print(f"Bluetooth command error: {type(exc).__name__}: {exc}")
                        raise

    except asyncio.CancelledError:
        raise
    except KeyboardInterrupt:
        print("\nStopping synchronization...")
    except Exception as exc:
        print(f"Program error: {type(exc).__name__}: {exc}")
    finally:
        if connected:
            print("Turning off the light...")
            try:
                await light.set_power(False)
                await asyncio.sleep(0.5)
                print("The turn-off command was sent.")
            except Exception as exc:
                print(f"Could not turn off the light: {type(exc).__name__}: {exc}")
            try:
                await light.disconnect()
            except Exception as exc:
                print(f"Could not close the Bluetooth connection: {exc}")
        print("Program finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
