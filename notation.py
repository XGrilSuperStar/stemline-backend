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
    # onset/frame = Basic Pitch confidence thresholds (higher = fewer, surer notes)
    # min_ms = shortest note kept; vel = drop notes quieter than this share of
    # the loud ones (ghost detections).
    "bass":   {"fmin": 30.0, "fmax": 400.0,  "mono": True,  "title": "Bass",
               "onset": 0.6, "frame": 0.4, "min_ms": 110, "vel": 0.35, "fold_above": 55},
    "vocals": {"fmin": 80.0, "fmax": 1100.0, "mono": True,  "title": "Vocals",
               "onset": 0.55, "frame": 0.35, "min_ms": 100, "vel": 0.3},
    "guitar": {"fmin": 80.0, "fmax": 1400.0, "mono": False, "title": "Guitar",
               "onset": 0.5, "frame": 0.3, "min_ms": 100, "vel": 0.25},
    "piano":  {"fmin": 27.0, "fmax": 4200.0, "mono": False, "title": "Keys / Synth",
               "onset": 0.5, "frame": 0.3, "min_ms": 100, "vel": 0.25},
    "other":  {"fmin": None, "fmax": None,   "mono": False, "title": "Other",
               "onset": 0.5, "frame": 0.3, "min_ms": 110, "vel": 0.25},
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


def _drop_quiet_notes(midi, share):
    """Drop ghost detections: notes much quieter than the loud ones."""
    import numpy as np
    for inst in midi.instruments:
        if not inst.notes:
            continue
        loud = float(np.percentile([n.velocity for n in inst.notes], 90))
        inst.notes = [n for n in inst.notes if n.velocity >= share * loud]


def _drop_tiny_notes(midi, min_seconds):
    for inst in midi.instruments:
        inst.notes = [n for n in inst.notes if (n.end - n.start) >= min_seconds]


def _fold_octaves(midi, top):
    """A bass can't play above `top`: such a note is almost always the 2nd
    harmonic being picked up, so bring it down by octaves."""
    for inst in midi.instruments:
        for n in inst.notes:
            while n.pitch > top:
                n.pitch -= 12


def _merge_same_pitch(midi, max_gap=0.03):
    """Basic Pitch sometimes splits one held note in two: glue them back."""
    for inst in midi.instruments:
        out = []
        for n in sorted(inst.notes, key=lambda n: (n.pitch, n.start)):
            prev = out[-1] if out else None
            if (prev and prev.pitch == n.pitch and n.start - prev.end <= max_gap
                    and n.velocity <= 1.3 * prev.velocity):
                prev.end = max(prev.end, n.end)
                prev.velocity = max(prev.velocity, n.velocity)
            else:
                out.append(n)
        inst.notes = sorted(out, key=lambda n: n.start)


def _make_monophonic(midi):
    """Keep ONE note at a time: the strongest (loudness x length) wins, notes
    that overlap a winner are dropped. Kills harmonics, octave blips and
    fragments that a single-line instrument can't actually play."""
    for inst in midi.instruments:
        ranked = sorted(inst.notes, key=lambda n: (n.end - n.start) * n.velocity, reverse=True)
        kept = []
        for n in ranked:
            clash = False
            for k in kept:
                overlap = min(n.end, k.end) - max(n.start, k.start)
                if overlap > 0.04 or overlap > 0.3 * (n.end - n.start):
                    clash = True
                    break
            if not clash:
                kept.append(n)
        kept.sort(key=lambda n: n.start)
        for a, b in zip(kept, kept[1:]):
            if a.end > b.start:
                a.end = b.start
        inst.notes = kept


def _refine_bpm(onsets, prior):
    """Pick the tempo (70-160) whose 8th-note grid the note onsets sit on best.
    Beat trackers often land on 2/3 or 3/2 of the real tempo; the notes
    themselves tell us which tempo is right. Ties go to the librosa estimate."""
    import numpy as np
    onsets = np.asarray(onsets, dtype=float)
    if onsets.size < 6:
        return prior
    cands = np.arange(70.0, 160.01, 0.5)
    errs = []
    for bpm in cands:
        g = 30.0 / bpm  # eighth note in seconds
        best = 1.0
        for off in np.linspace(0, g, 24, endpoint=False):
            ph = ((onsets - off) / g) % 1.0
            e = float(np.mean(np.minimum(ph, 1.0 - ph)))  # 0 = on grid, .5 = worst
            best = min(best, e)
        errs.append(best)
    errs = np.asarray(errs)
    ok = np.where(errs <= errs.min() + 0.02)[0]
    pick = ok[np.argmin(np.abs(np.log(cands[ok] / prior)))]
    return float(cands[pick])


def _quantize_midi(midi, bpm):
    """Snap note starts/ends to a 16th-note grid at `bpm`, then return a new
    PrettyMIDI. No triplets, no tiny rests: one clean grid."""
    import numpy as np
    import pretty_midi

    g = 15.0 / bpm  # 16th note in seconds
    starts = np.array([n.start for i in midi.instruments for n in i.notes])
    if starts.size == 0:
        return midi
    offs = np.linspace(0, g, 32, endpoint=False)
    def cost(off):
        ph = ((starts - off) / g) % 1.0
        return float(np.mean(np.minimum(ph, 1.0 - ph)))
    off = float(offs[int(np.argmin([cost(o) for o in offs]))])

    out = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    for inst in midi.instruments:
        new = pretty_midi.Instrument(program=inst.program, is_drum=False, name=inst.name)
        notes = []
        for n in sorted(inst.notes, key=lambda n: n.start):
            s = max(0, int(round((n.start - off) / g)))
            e = max(s + 1, int(round((n.end - off) / g)))
            notes.append([s, e, n.pitch, n.velocity])
        for a, b in zip(notes, notes[1:]):  # no overlaps on one line / same pitch
            if a[2] == b[2] or b[0] - a[1] < 0:
                a[1] = max(a[0] + 1, min(a[1], b[0]))
            if 0 < b[0] - a[1] <= 1 and True:
                a[1] = b[0]  # fill one-16th gaps instead of writing tiny rests
        for s, e, p, v in notes:
            new.notes.append(pretty_midi.Note(velocity=v, pitch=p, start=s * g, end=e * g))
        out.instruments.append(new)
    return out


def _midi_to_musicxml(midi_bytes, title):
    from music21 import converter, key as m21key, metadata, stream

    with tempfile.TemporaryDirectory() as td:
        mid_path = os.path.join(td, "in.mid")
        with open(mid_path, "wb") as f:
            f.write(midi_bytes)
        score = converter.parse(mid_path, quantizePost=True, quarterLengthDivisors=(4,))
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

        prior = _estimate_bpm(audio_path)
        _, midi, note_events = predict(
            audio_path,
            _get_model(),
            onset_threshold=settings["onset"],
            frame_threshold=settings["frame"],
            minimum_note_length=settings["min_ms"],
            minimum_frequency=settings["fmin"],
            maximum_frequency=settings["fmax"],
            midi_tempo=prior,
        )

    _drop_quiet_notes(midi, settings["vel"])
    _drop_tiny_notes(midi, settings["min_ms"] / 1000.0)
    if settings.get("fold_above"):
        _fold_octaves(midi, settings["fold_above"])
    _merge_same_pitch(midi)
    if settings["mono"]:
        _make_monophonic(midi)
    onsets = [n.start for i in midi.instruments for n in i.notes]
    bpm = _refine_bpm(onsets, prior)
    midi = _quantize_midi(midi, bpm)

    note_count = sum(len(i.notes) for i in midi.instruments)
    if note_count == 0:
        raise NotationError("No notes were detected in this stem.")

    buf = io.BytesIO()
    midi.write(buf)
    midi_bytes = buf.getvalue()

    xml = _midi_to_musicxml(midi_bytes, settings["title"])
    return {"midi": midi_bytes, "musicxml": xml, "bpm": bpm, "note_count": note_count}
