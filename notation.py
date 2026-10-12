"""Audio stem -> MIDI + MusicXML sheet music.

Pipeline: Basic Pitch (audio -> notes) -> light clean-up per instrument ->
music21 (quantize + key signature) -> MusicXML. All pieces are free and
open source. Heavy imports happen lazily so the rest of the app never pays
for them unless the feature is actually used.
"""

import io
import os
import tempfile
import threading

# Per-instrument settings. Frequency ranges keep Basic Pitch from reporting
# harmonics/rumble as notes; "mono" collapses overlapping notes into a single
# melodic line, which is what a bass line or a vocal melody actually is.
INSTRUMENT_SETTINGS = {
    "bass":   {"fmin": 30.0, "fmax": 400.0,  "mono": True,  "title": "Bass"},
    "vocals": {"fmin": 80.0, "fmax": 1100.0, "mono": True,  "title": "Vocals"},
    "guitar": {"fmin": 80.0, "fmax": 1400.0, "mono": False, "title": "Guitar"},
    "piano":  {"fmin": 27.0, "fmax": 4200.0, "mono": False, "title": "Keys / Synth"},
    "other":  {"fmin": None, "fmax": None,   "mono": False, "title": "Other"},
}
UNSUPPORTED = {"drums"}  # pitch-based transcription is meaningless for drums

_model = None
_model_lock = threading.Lock()


class NotationError(Exception):
    pass


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            from basic_pitch import ICASSP_2022_MODEL_PATH
            from basic_pitch.inference import Model
            _model = Model(ICASSP_2022_MODEL_PATH)
        return _model


def _estimate_bpm(path):
    """Estimate tempo so note lengths quantize to sensible values."""
    import librosa
    import numpy as np

    y, sr = librosa.load(path, sr=22050, mono=True, duration=120)
    if y.size < sr:  # under a second of audio
        return 120.0
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0]) if np.size(tempo) else 120.0
    if not bpm or bpm != bpm:
        return 120.0
    # Fold half/double-time guesses into a readable range.
    while bpm < 70:
        bpm *= 2
    while bpm > 160:
        bpm /= 2
    return round(bpm, 1)


def _make_monophonic(midi):
    """Collapse overlapping notes into one melodic line (in place)."""
    for inst in midi.instruments:
        notes = sorted(inst.notes, key=lambda n: (n.start, -n.velocity))
        kept = []
        for n in notes:
            if kept and n.start < kept[-1].end:
                prev = kept[-1]
                overlap = prev.end - n.start
                shorter = min(prev.end - prev.start, n.end - n.start)
                if shorter > 0 and overlap / shorter > 0.6 and n.velocity <= prev.velocity:
                    continue  # mostly hidden under a stronger note: drop it
                prev.end = max(prev.start + 0.03, n.start)
            kept.append(n)
        inst.notes = kept


def _drop_tiny_notes(midi, min_seconds=0.06):
    for inst in midi.instruments:
        inst.notes = [n for n in inst.notes if (n.end - n.start) >= min_seconds]


def _midi_to_musicxml(midi_bytes, title):
    from music21 import converter, key as m21key, metadata, stream

    with tempfile.TemporaryDirectory() as td:
        mid_path = os.path.join(td, "in.mid")
        with open(mid_path, "wb") as f:
            f.write(midi_bytes)
        score = converter.parse(mid_path, quantizePost=True)
        if not isinstance(score, stream.Score):
            wrapper = stream.Score()
            wrapper.insert(0, score)
            score = wrapper

        if not list(score.recurse().notes):
            raise NotationError("No notes were detected in this stem.")

        score.metadata = metadata.Metadata()
        score.metadata.title = title
        score.metadata.composer = "Transcribed by Stemline101"

        try:
            detected = score.analyze("key")
            sharps = detected.sharps
        except Exception:
            sharps = 0

        for part in score.parts:
            for old in part.recurse().getElementsByClass(m21key.KeySignature):
                old.activeSite.remove(old)
            part.insert(0, m21key.KeySignature(sharps))
            if sharps < 0:  # flat key: spell accidentals as flats
                for n in part.recurse().notes:
                    pitches = n.pitches
                    for p in pitches:
                        if p.accidental is not None and p.accidental.alter > 0:
                            p.getEnharmonic(inPlace=True)

        out_path = os.path.join(td, "out.musicxml")
        score.write("musicxml", fp=out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            return f.read()


def transcribe(audio_bytes, ext, instrument):
    """Return {"midi": bytes, "musicxml": str, "bpm": float, "note_count": int}."""
    if instrument in UNSUPPORTED:
        raise NotationError("Drums can't be turned into sheet music yet.")
    settings = INSTRUMENT_SETTINGS.get(instrument)
    if not settings:
        raise NotationError(f"Unknown instrument: {instrument}")

    from basic_pitch.inference import predict

    ext = (ext or "wav").lower().lstrip(".")
    with tempfile.TemporaryDirectory() as td:
        audio_path = os.path.join(td, f"stem.{ext}")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        bpm = _estimate_bpm(audio_path)
        _, midi, note_events = predict(
            audio_path,
            _get_model(),
            minimum_frequency=settings["fmin"],
            maximum_frequency=settings["fmax"],
            midi_tempo=bpm,
        )

    _drop_tiny_notes(midi)
    if settings["mono"]:
        _make_monophonic(midi)

    note_count = sum(len(i.notes) for i in midi.instruments)
    if note_count == 0:
        raise NotationError("No notes were detected in this stem.")

    buf = io.BytesIO()
    midi.write(buf)
    midi_bytes = buf.getvalue()

    xml = _midi_to_musicxml(midi_bytes, settings["title"])
    return {"midi": midi_bytes, "musicxml": xml, "bpm": bpm, "note_count": note_count}
