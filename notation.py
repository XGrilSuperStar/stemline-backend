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
    # a solo voice recorded on purpose (hum / sing / whistle): no band bleed,
    # so thresholds can be gentler than for a separated vocal stem
    "hum":    {"fmin": 65.0, "fmax": 1400.0, "mono": True,  "title": "Voice",
               "onset": 0.45, "frame": 0.3, "min_ms": 110, "vel": 0.25,
               "dip_split": True},
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


def _hum_to_midi(path, tempo, fmin=65.0, fmax=1000.0, min_ms=90):
    """Single-voice pitch tracking (pYIN) -> notes.

    Basic Pitch is polyphonic and invents extra notes from overtones when fed
    a lone voice. pYIN follows exactly one pitch at a time, which is what a
    hum / sung line is."""
    import librosa
    import numpy as np
    import pretty_midi

    y, sr = librosa.load(path, sr=22050, mono=True, duration=120)
    hop = 256
    if y.size < sr * 0.2:
        return pretty_midi.PrettyMIDI(initial_tempo=tempo)
    f0, voiced, _ = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=sr,
                                 frame_length=2048, hop_length=hop)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    n = min(len(f0), len(rms))
    f0, voiced, rms = f0[:n], voiced[:n], rms[:n]
    hop_s = hop / float(sr)

    midi_f = np.full(n, np.nan)
    ok = voiced & ~np.isnan(f0)
    # Open a gap wherever the voice dips well below its nearby peak ("doo-doo",
    # consonants, breaths): pYIN alone bridges those and runs notes together.
    w = int(0.15 / (hop / float(sr)))
    local_max = np.array([rms[max(0, i - w): i + w + 1].max() for i in range(n)])
    ok &= rms >= 0.3 * local_max
    midi_f[ok] =69.0 + 12.0 * np.log2(f0[ok] / 440.0)
    if ok.sum() < 3:
        return pretty_midi.PrettyMIDI(initial_tempo=tempo)

    # pYIN sometimes locks onto half or double the real frequency (a note an
    # octave off, or a stray low "extra" note). Pull any frame that sits far
    # from the voice's nearby median back by octaves.
    idx = np.where(ok)[0]
    if idx.size > 5:
        w2 = int(0.8 / (hop / float(sr)))
        vals = midi_f[idx]
        for j, i in enumerate(idx):
            lo = np.searchsorted(idx, i - w2)
            hi = np.searchsorted(idx, i + w2, side="right")
            ref = np.median(vals[lo:hi])
            v = midi_f[i]
            while v - ref > 9.5:
                v -= 12
            while ref - v > 9.5:
                v += 12
            midi_f[i] = v

    # Singers are rarely exactly in tune with A440: measure how far off they
    # sit on average (circular median of the cents offset) and correct it.
    frac = midi_f[ok] - np.round(midi_f[ok])
    ang = np.angle(np.mean(np.exp(2j * np.pi * frac))) / (2 * np.pi)
    midi_f = midi_f - ang

    # Median-smooth the pitch track so vibrato and glitches don't make notes.
    sm = midi_f.copy()
    k = 2
    for i in range(n):
        if np.isnan(midi_f[i]):
            continue
        w = midi_f[max(0, i - k): i + k + 1]
        w = w[~np.isnan(w)]
        sm[i] = np.median(w)
    pitch = np.where(np.isnan(sm), -1, np.round(sm)).astype(int)

    # Run-length encode, then absorb runs too short to be real notes.
    runs = []
    for i, p in enumerate(pitch):
        if runs and runs[-1][0] == p:
            runs[-1][2] = i + 1
        else:
            runs.append([int(p), i, i + 1])
    min_frames = max(2, int(round(min_ms / 1000.0 / hop_s)))
    changed = True
    while changed:
        changed = False
        for idx, (p, a, b) in enumerate(runs):
            if p == -1 or (b - a) >= min_frames:
                continue
            left = runs[idx - 1] if idx > 0 else None
            right = runs[idx + 1] if idx + 1 < len(runs) else None
            if left and right and left[0] == right[0] and left[0] != -1:
                left[2] = right[2]
                del runs[idx:idx + 2]
            elif left and left[0] != -1 and (not right or right[0] == -1 or (left[2] - left[1]) >= (right[2] - right[1])):
                left[2] = b
                del runs[idx]
            elif right and right[0] != -1:
                right[1] = a
                del runs[idx]
            else:
                runs[idx][0] = -1
            changed = True
            break
    # glue neighbours that ended up with the same pitch
    merged = []
    for r in runs:
        if merged and merged[-1][0] == r[0] and r[0] != -1:
            merged[-1][2] = r[2]
        else:
            merged.append(list(r))

    loud = float(np.percentile(rms, 95)) or 1.0
    pm = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    inst = pretty_midi.Instrument(program=0)
    for p, a, b in merged:
        if p < 0 or (b - a) < min_frames:
            continue
        vel = int(np.clip(40 + 80 * float(np.mean(rms[a:b])) / loud, 30, 120))
        inst.notes.append(pretty_midi.Note(velocity=vel, pitch=int(p),
                                           start=a * hop_s, end=b * hop_s))
    pm.instruments.append(inst)
    return pm


def _drop_quiet_notes(midi, share):
    """Drop ghost detections: notes much quieter than the loud ones."""
    import numpy as np
    for inst in midi.instruments:
        if not inst.notes:
            continue
        loud = float(np.percentile([n.velocity for n in inst.notes], 90))
        inst.notes = [n for n in inst.notes if n.velocity >= share * loud]


def _fix_octave_outliers(midi, span=3, jump=10):
    """A sung note an octave away from the notes around it is almost always a
    tracking error (the end of a recording is where it happens most). Move it
    by octaves toward the neighbouring notes."""
    import numpy as np
    for inst in midi.instruments:
        notes = sorted(inst.notes, key=lambda n: n.start)
        for i, n in enumerate(notes):
            near = [m.pitch for m in notes[max(0, i - span): i] + notes[i + 1: i + 1 + span]]
            if len(near) < 2:
                continue
            ref = float(np.median(near))
            while n.pitch - ref >= jump:
                n.pitch -= 12
            while ref - n.pitch >= jump:
                n.pitch += 12
        # Also compare with the whole line: a run of low notes (the end of a
        # take) can drag the local median down with it and hide the error.
        if len(notes) >= 6:
            top = float(np.median([n.pitch for n in notes]))
            for n in notes:
                while top - n.pitch >= jump:
                    n.pitch += 12
                while n.pitch - top >= jump + 2:
                    n.pitch -= 12


def _drop_weak_short_notes(midi, short=0.2, keep_share=0.7, tail_share=0.5):
    """Sung line cleanup: a note under `short` seconds only counts if it is
    clearly loud (breaths, consonants and slides are short AND quiet), and
    quiet notes trailing off the end of the take are cut."""
    import numpy as np
    for inst in midi.instruments:
        if len(inst.notes) < 6:
            continue
        loud = float(np.percentile([n.velocity for n in inst.notes], 90))
        inst.notes = [n for n in inst.notes
                      if (n.end - n.start) >= short or n.velocity >= keep_share * loud]
        notes = sorted(inst.notes, key=lambda n: n.start)
        while len(notes) > 4 and notes[-1].velocity < tail_share * loud:
            notes.pop()
        inst.notes = notes


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


def _clean_fragments(midi, short=0.15, join_gap=0.08, drop_below=0.10):
    """Tidy tiny stray notes: a short note next to the same pitch is glued on,
    a short note right beside a longer note within a semitone is absorbed,
    and a very short lone note is dropped."""
    for inst in midi.instruments:
        notes = sorted(inst.notes, key=lambda n: n.start)
        changed = True
        while changed:
            changed = False
            for i, n in enumerate(notes):
                if n.end - n.start >= short:
                    continue
                prev = notes[i - 1] if i > 0 else None
                nxt = notes[i + 1] if i + 1 < len(notes) else None
                same = [x for x in (prev, nxt) if x and x.pitch == n.pitch
                        and (n.start - x.end <= join_gap if x is prev else x.start - n.end <= join_gap)]
                if same:
                    x = same[0]
                    x.start, x.end = min(x.start, n.start), max(x.end, n.end)
                    notes.pop(i); changed = True; break
                near = [x for x in (prev, nxt) if x and abs(x.pitch - n.pitch) <= 1
                        and x.end - x.start > 2 * (n.end - n.start)
                        and (n.start - x.end <= join_gap if x is prev else x.start - n.end <= join_gap)]
                if near or n.end - n.start < drop_below:
                    notes.pop(i); changed = True; break
        inst.notes = notes


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


def _ensure_gap(midi, gap=0.10, min_len=0.06, max_trim=0.4):
    """End a note early when it sits too close to the next one, so a clear rest
    shows between notes in the downloaded MIDI. A note gives up at most
    `max_trim` of its own length, so short notes aren't squashed to nothing."""
    for inst in midi.instruments:
        notes = sorted(inst.notes, key=lambda n: n.start)
        for a, b in zip(notes, notes[1:]):
            room = b.start - a.end
            if room < gap:
                length = a.end - a.start
                new_end = max(b.start - gap, a.end - max_trim * length)
                new_end = min(new_end, a.end)
                if new_end - a.start >= min_len:
                    a.end = new_end


def _collapse_slides(midi, max_gap=0.06, short=0.16):
    """A sung slide between two notes makes the detector write a staircase of
    short notes one or two semitones apart. Fold each such short note into its
    longer neighbour so a slide reads as one note, not several."""
    for inst in midi.instruments:
        notes = sorted(inst.notes, key=lambda n: n.start)
        changed = True
        while changed:
            changed = False
            for i in range(len(notes) - 1):
                a, b = notes[i], notes[i + 1]
                la, lb = a.end - a.start, b.end - b.start
                diff = abs(a.pitch - b.pitch)
                if (b.start - a.end) <= max_gap and 1 <= diff <= 2 and min(la, lb) < (short if diff == 1 else 0.12):
                    keep, drop = (a, b) if la >= lb else (b, a)
                    keep.start = min(a.start, b.start)
                    keep.end = max(a.end, b.end)
                    notes.remove(drop)
                    changed = True
                    break
        inst.notes = notes


def _split_on_volume_dips(midi, rms, hop_s, depth=0.3, min_part=0.10, min_dip=0.03):
    """The pitch model can't tell two sung notes of the SAME pitch apart ("la la
    la" comes out as one long note). The volume can: between repeated notes the
    voice dips. Split a note wherever the loudness falls below `depth` x the
    quieter of the peaks on either side. Each part must be at least `min_part`
    seconds, so vibrato or a small wobble doesn't chop a held note."""
    import numpy as np
    r = np.convolve(rms, np.ones(3) / 3.0, mode="same")
    m = max(2, int(round(min_part / hop_s)))
    for inst in midi.instruments:
        out = []
        for n in inst.notes:
            a = int(n.start / hop_s)
            b = min(len(r), int(n.end / hop_s))
            seg = r[a:b]
            starts_ends = []
            cut = 0
            i = cut + m
            while i < len(seg) - m:
                lo, hi = max(0, i - 3), min(len(seg), i + 4)
                if seg[i] <= seg[lo:hi].min():
                    left = seg[cut:i].max()
                    right = seg[i:min(len(seg), i + 3 * m)].max()
                    if seg[i] < depth * min(left, right):
                        # widen the dip to where the volume climbs back above half way
                        lim = 0.5 * min(left, right)
                        j0 = i
                        while j0 > cut and seg[j0 - 1] < lim:
                            j0 -= 1
                        j1 = i
                        while j1 < len(seg) - 1 and seg[j1 + 1] < lim:
                            j1 += 1
                        if (j1 - j0 + 1) * hop_s >= min_dip:   # a real pause, not a brief wobble
                            starts_ends.append((cut, max(cut + 1, j0)))
                            cut = j1 + 1
                            i = cut + m
                            continue
                i += 1
            starts_ends.append((cut, len(seg)))
            if len(starts_ends) == 1:
                out.append(n)
                continue
            for s_i, e_i in starts_ends:
                s = n.start if s_i == 0 else (a + s_i) * hop_s
                e = n.end if e_i >= len(seg) else (a + e_i) * hop_s
                if e - s >= min_part * 0.75:
                    out.append(type(n)(velocity=n.velocity, pitch=n.pitch, start=s, end=e))
        inst.notes = sorted(out, key=lambda x: x.start)


def _trim_note_ends(midi, rms, hop_s, frac=0.3, min_len=0.09):
    """The pitch model keeps a note alive through echo / reverb / decay tails, so
    the rests between notes shrink to almost nothing. End each note where the
    loudness has fallen below `frac` of that note's own peak instead."""
    import numpy as np
    r = np.convolve(rms, np.ones(3) / 3.0, mode="same")
    for inst in midi.instruments:
        for n in inst.notes:
            a = int(n.start / hop_s)
            b = min(len(r), int(n.end / hop_s))
            if b - a < 4:
                continue
            seg = r[a:b]
            pk = int(np.argmax(seg))
            lim = frac * seg[pk]
            end_i = None
            for i in range(pk, len(seg) - 2):
                if seg[i] < lim and seg[i + 1] < lim and seg[i + 2] < lim:
                    end_i = i
                    break
            if end_i is not None:
                new_end = (a + end_i) * hop_s
                if new_end - n.start >= min_len and new_end < n.end:
                    n.end = new_end


def _force_chord_line(midi, max_notes=6):
    """Polyphonic instruments (guitar, keys): after quantizing, notes starting
    together form one chord that ends where the next chord begins. No partial
    overlaps means a single voice, so the tab staff can be added."""
    for inst in midi.instruments:
        groups = {}
        for n in inst.notes:
            groups.setdefault(round(n.start, 3), []).append(n)
        starts = sorted(groups)
        kept = []
        for i, s in enumerate(starts):
            g = sorted(groups[s], key=lambda n: -n.velocity)[:max_notes]
            end = max(n.end for n in g)
            if i + 1 < len(starts):
                end = min(end, starts[i + 1])
            for n in g:
                n.start = s
                n.end = end
                if n.end - n.start > 1e-4:
                    kept.append(n)
        inst.notes = kept


def _force_single_line(midi):
    """After quantizing, make a one-note-at-a-time instrument truly one line:
    notes that land on the same grid step keep only the strongest, and every
    note ends where the next begins. Overlaps would make the score writer
    split the part into several voices, and the tab staff can't be added then."""
    for inst in midi.instruments:
        notes = sorted(inst.notes, key=lambda n: (round(n.start, 4), -(n.end - n.start) * n.velocity))
        kept = []
        for n in notes:
            if kept and abs(n.start - kept[-1].start) < 1e-4:
                continue
            kept.append(n)
        for a, b in zip(kept, kept[1:]):
            if a.end > b.start:
                a.end = b.start
        inst.notes = [n for n in kept if n.end - n.start > 1e-4]


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


def _detect_meter(midi, bpm):
    """Time signature from the notes themselves: bars start where the heavy
    (long/loud) notes keep landing. Tries 3 and 4 beats per bar and every
    possible bar start; 4/4 wins unless 3/4 is clearly stronger.
    Returns (beats_per_bar, downbeat_offset_in_beats)."""
    import numpy as np
    notes = [n for i in midi.instruments for n in i.notes]
    if len(notes) < 8:
        return 4, 0.0
    b = 60.0 / bpm
    starts = np.array([n.start for n in notes])
    weight = np.array([n.velocity * (n.end - n.start) ** 0.5 for n in notes])
    offs = np.linspace(0, b, 24, endpoint=False)
    def cost(o):
        ph = ((starts - o) / b) % 1.0
        return float(np.mean(np.minimum(ph, 1.0 - ph)))
    off = float(offs[int(np.argmin([cost(o) for o in offs]))])
    idx = np.floor((starts - off) / b + 0.5).astype(int)
    idx -= idx.min()
    pitches = np.array([n.pitch % 12 for n in notes])
    w = np.bincount(idx, weights=weight)
    if w.size < 8 or w.mean() <= 0:
        return 4, 0.0
    # pitch class of the heaviest note starting on each beat
    beat_pc = {}
    for k in np.unique(idx):
        sel = np.where(idx == k)[0]
        beat_pc[int(k)] = int(pitches[sel[np.argmax(weight[sel])]])
    best = {}
    for B in (3, 4):
        for ph in range(B):
            sel = w[ph::B]
            if sel.size < 3:
                continue
            prom = float(sel.mean() / w.mean())
            pcs = [beat_pc[k] for k in range(ph, w.size, B) if k in beat_pc]
            if not pcs:
                continue
            # bars tend to open on the same note (the root): reward that
            same = max(pcs.count(x) for x in set(pcs)) / len(pcs)
            score = prom * (0.5 + same)
            if B not in best or score > best[B][0]:
                best[B] = (score, ph)
    if 4 not in best:
        return 4, 0.0
    use = 4
    if 3 in best and best[3][0] > best[4][0] * 1.1:
        use = 3
    ph = best[use][1]
    # beat index `ph` (counted from the first note's beat) is the downbeat
    first_beat_pos = off + b * (np.floor((starts.min() - off) / b + 0.5))
    return use, float(first_beat_pos + ph * b)


def _quantize_midi(midi, bpm, beats=4, downbeat=None):
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

    # Make the detected downbeat the start of a bar. Notes before it become a
    # pick-up measure (leading rest) instead of being cut off.
    shift = 0.0
    if downbeat is not None:
        bar = beats * 60.0 / bpm
        shift = -downbeat
        while starts.min() + shift < -1e-6:
            shift += bar
        off = (off + shift) % g if shift else off
    out = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    out.time_signature_changes.append(pretty_midi.TimeSignature(beats, 4, 0))
    for inst in midi.instruments:
        new = pretty_midi.Instrument(program=inst.program, is_drum=False, name=inst.name)
        notes = []
        for n in sorted(inst.notes, key=lambda n: n.start):
            s = max(0, int(round((n.start + shift - off) / g)))
            e = max(s + 1, int(round((n.end + shift - off) / g)))
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


def _add_letters(xml):
    """Print the note letter (A, E, F#...) under every note, so pitches can be
    checked without reading the clef."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
        for part in root.findall("part"):
            for m in part.findall("measure"):
                notes = m.findall("note")
                i = 0
                while i < len(notes):
                    grp = [notes[i]]
                    while i + 1 < len(notes) and notes[i + 1].find("chord") is not None:
                        i += 1
                        grp.append(notes[i])
                    names = []
                    for n in grp:
                        p = n.find("pitch")
                        if p is None:
                            continue
                        alter = int(float(p.findtext("alter") or 0))
                        names.append(p.findtext("step") + ("#" * alter if alter > 0 else "b" * -alter))
                    if names:
                        lyr = ET.SubElement(grp[0], "lyric", number="1")
                        ET.SubElement(lyr, "syllabic").text = "single"
                        ET.SubElement(lyr, "text").text = "".join(names) if len(names) == 1 else " ".join(names)
                    i += 1
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
    except Exception:
        return xml


# Open-string MIDI pitches, lowest string first, for the tab staff.
TUNINGS = {
    "bass": [28, 33, 38, 43],            # E A D G
    "guitar": [40, 45, 50, 55, 59, 64],  # E A D G B E
    "other": [40, 45, 50, 55, 59, 64],   # shown as guitar tab
    "piano": [40, 45, 50, 55, 59, 64],   # shown as guitar tab
}
_STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _add_tablature(xml, instrument, tab_only=False):
    """Add tablature (MusicXML string/fret).
    By default a TAB staff is added under the notation staff. With tab_only the
    notation staff is replaced by a single TAB staff, so each note is shown once.
    Only when the score is a single simple voice per measure. Any problem ->
    return the input untouched."""
    tuning = TUNINGS.get(instrument)
    if not tuning:
        return xml
    import copy
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
        parts = root.findall("part")
        if len(parts) != 1:
            return xml
        measures = parts[0].findall("measure")
        if not measures or any(m.find("backup") is not None or m.find("forward") is not None
                               for m in measures):
            return xml
        nstr = len(tuning)
        prev_fret = [0]

        def midi_of(note):
            p = note.find("pitch")
            if p is None:
                return None
            alter = p.findtext("alter")
            return (int(p.findtext("octave")) + 1) * 12 + _STEP[p.findtext("step")] + int(float(alter or 0))

        def place(pitches):
            """Choose a (string, fret) for each pitch of a chord: distinct
            strings, lowest fret near the previous hand position."""
            used, out = set(), {}
            for pitch in sorted(pitches, reverse=True):
                best = None
                for si, open_p in enumerate(tuning):
                    fret = pitch - open_p
                    if fret < 0 or fret > 15 or si in used:
                        continue
                    cost = fret  # lowest fret, open strings first
                    if best is None or cost < best[0]:
                        best = (cost, si, fret)
                if best is None:  # out of range: clamp onto the lowest string
                    best = (0, 0, max(0, pitch - tuning[0]))
                    if 0 in used:
                        continue
                used.add(best[1])
                out[pitch] = (best[1], best[2])
            if out:
                prev_fret[0] = min(f for _, f in out.values())
            return out

        def insert_staff(note, n):
            el = ET.Element("staff")
            el.text = str(n)
            for i, ch in enumerate(list(note)):
                if ch.tag in ("beam", "notations", "lyric", "play"):
                    note.insert(i, el)
                    return
            note.append(el)

        def set_voice(note, n):
            """Explicit <voice> on every note, so the tab staff gets its own
            voice instead of sharing voice 1 with the notation staff."""
            v = note.find("voice")
            if v is not None:
                v.text = str(n)
                return
            el = ET.Element("voice")
            el.text = str(n)
            pos = 0
            for i, ch in enumerate(list(note)):
                if ch.tag in ("pitch", "rest", "unpitched", "duration", "tie", "chord", "grace", "cue"):
                    pos = i + 1
            note.insert(pos, el)

        first = measures[0].find("attributes")
        if tab_only:
            # one TAB staff: the existing notes just gain string/fret, nothing is duplicated
            for tag in ("staves", "clef", "staff-details"):
                for old in first.findall(tag):
                    first.remove(old)
            c = ET.SubElement(first, "clef")
            ET.SubElement(c, "sign").text = "TAB"; ET.SubElement(c, "line").text = "5"
            sd = ET.SubElement(first, "staff-details")
            ET.SubElement(sd, "staff-lines").text = str(nstr)
            for m in measures:
                groups = []
                for n in m.findall("note"):
                    if n.find("chord") is not None and groups:
                        groups[-1].append(n)
                    else:
                        groups.append([n])
                for g in groups:
                    pitches = [midi_of(n) for n in g if midi_of(n) is not None]
                    assign = place(pitches) if pitches else {}
                    for n in g:
                        for tag in ("accidental", "lyric"):
                            for e in n.findall(tag):
                                n.remove(e)
                        p = midi_of(n)
                        if p is not None and p in assign:
                            si, fret = assign[p]
                            nt = n.find("notations")
                            if nt is None:
                                nt = ET.SubElement(n, "notations")
                            tech = ET.SubElement(nt, "technical")
                            ET.SubElement(tech, "string").text = str(nstr - si)  # MusicXML: 1 = highest string
                            ET.SubElement(tech, "fret").text = str(fret)
            return ET.tostring(root, encoding="unicode", xml_declaration=True)

        for tag in ("staves", "clef", "staff-details"):
            for old in first.findall(tag):
                first.remove(old)
        st = ET.SubElement(first, "staves"); st.text = "2"
        c1 = ET.SubElement(first, "clef", number="1")
        if instrument == "bass":
            ET.SubElement(c1, "sign").text = "F"; ET.SubElement(c1, "line").text = "4"
        else:
            ET.SubElement(c1, "sign").text = "G"; ET.SubElement(c1, "line").text = "2"
            if instrument == "guitar":
                ET.SubElement(c1, "clef-octave-change").text = "-1"
        c2 = ET.SubElement(first, "clef", number="2")
        ET.SubElement(c2, "sign").text = "TAB"; ET.SubElement(c2, "line").text = "5"
        sd = ET.SubElement(first, "staff-details", number="2")
        ET.SubElement(sd, "staff-lines").text = str(nstr)

        for m in measures:
            notes = m.findall("note")
            total = sum(int(n.findtext("duration") or 0) for n in notes if n.find("chord") is None)
            for n in notes:
                set_voice(n, 1)
                insert_staff(n, 1)
            bk =ET.SubElement(m, "backup")
            ET.SubElement(bk, "duration").text = str(total)
            # group chord members so they get distinct strings
            groups = []
            for n in notes:
                if n.find("chord") is not None and groups:
                    groups[-1].append(n)
                else:
                    groups.append([n])
            for g in groups:
                pitches = [midi_of(n) for n in g if midi_of(n) is not None]
                assign = place(pitches) if pitches else {}
                for n in g:
                    t = copy.deepcopy(n)
                    for tag in ("beam", "notations", "accidental", "staff", "stem", "lyric"):
                        for e in t.findall(tag):
                            t.remove(e)
                    set_voice(t, 2)
                    insert_staff(t, 2)
                    p = midi_of(n)
                    if p is not None and p in assign:
                        si, fret = assign[p]
                        nt = ET.SubElement(t, "notations")
                        tech = ET.SubElement(nt, "technical")
                        ET.SubElement(tech, "string").text = str(nstr - si)  # MusicXML: 1 = highest string
                        ET.SubElement(tech, "fret").text = str(fret)
                    m.append(t)
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
    except Exception:
        return xml



_MAJOR_PC = [0, 2, 4, 5, 7, 9, 11]
_NAMES_SHARP = {0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B", 6: "F#", 7: "C#",
                -1: "F", -2: "Bb", -3: "Eb", -4: "Ab", -5: "Db", -6: "Gb", -7: "Cb"}


def _pick_key(score):
    """Choose the key signature that needs the FEWEST accidentals for the notes
    actually played (a bass line of A, E and D is written with no sharps, not
    in 'D major' with two). Returns (sharps, label)."""
    weight = {}
    for n in score.recurse().notes:
        for p in n.pitches:
            weight[p.pitchClass] = weight.get(p.pitchClass, 0.0) + float(n.quarterLength)
    if not weight:
        return 0, ""
    best = None
    for sh in range(-4, 5):
        tonic = (sh * 7) % 12                      # major tonic pitch class
        scale = {(tonic + i) % 12 for i in _MAJOR_PC}
        outside = sum(w for pc, w in weight.items() if pc not in scale)
        key = (round(outside, 3), abs(sh), sh)
        if best is None or key < best[0]:
            best = (key, sh, tonic)
    _, sh, tonic = best
    # major or its relative minor: whichever tonic is heavier in the line
    minor_tonic = (tonic + 9) % 12
    is_minor = weight.get(minor_tonic, 0.0) > weight.get(tonic, 0.0)
    name = _NAMES_SHARP[sh]
    if is_minor:
        from music21 import pitch
        name = pitch.Pitch(minor_tonic).name.replace("-", "b") + " minor"
    else:
        name += " major"
    return sh, f"Key: {name}"


def _midi_to_musicxml(midi_bytes, title, bpm=None, beats=4):
    from music21 import converter, expressions, key as m21key, meter, metadata, stream

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

        key_label = ""
        sharps = 0
        try:
            sharps, key_label = _pick_key(score)
        except Exception:
            pass

        for part in score.parts:
            for old in part.recurse().getElementsByClass(m21key.KeySignature):
                old.activeSite.remove(old)
            part.partName = title
            part.partAbbreviation = title
            part.insert(0, m21key.KeySignature(sharps))
            if not list(part.recurse().getElementsByClass(meter.TimeSignature)):
                m0 = part.getElementsByClass(stream.Measure).first()
                (m0 if m0 is not None else part).insert(0, meter.TimeSignature(f"{beats}/4"))
            label = "   |   ".join(x for x in (f"{round(bpm)} BPM" if bpm else "", key_label) if x)
            if label:
                te = expressions.TextExpression(label)
                te.placement = "above"
                m1 = part.getElementsByClass(stream.Measure).first()
                (m1 if m1 is not None else part).insert(0, te)
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

    if instrument != "hum":
        from basic_pitch.inference import predict

    ext =(ext or "wav").lower().lstrip(".")
    with tempfile.TemporaryDirectory() as td:
        audio_path = os.path.join(td, f"stem.{ext}")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        prior = _estimate_bpm(audio_path)
        if instrument == "hum":
            midi = _hum_to_midi(audio_path, prior, settings["fmin"],
                                min(settings["fmax"], 1000.0), settings["min_ms"])
        else:
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
        rms = hop_s = None
        if settings.get("dip_split") or settings["mono"]:
            import librosa
            y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=120)
            hop = 128
            rms = librosa.feature.rms(y=y, frame_length=512, hop_length=hop)[0]
            hop_s = hop / float(sr)

    _drop_quiet_notes(midi, settings["vel"])
    _drop_tiny_notes(midi, settings["min_ms"] / 1000.0)
    if settings.get("fold_above"):
        _fold_octaves(midi, settings["fold_above"])
    _merge_same_pitch(midi)
    if instrument == "hum":
        _fix_octave_outliers(midi)
    if rms is not None:
        if settings.get("dip_split"):
            if instrument == "hum":
                # sung syllables dip less than "la la la": split on shallower dips
                _split_on_volume_dips(midi, rms, hop_s, depth=0.6, min_part=0.08, min_dip=0.02)
            else:
                _split_on_volume_dips(midi, rms, hop_s)
            _collapse_slides(midi)
            if instrument != "hum":   # hum: keep repeated syllables on one pitch separate
                _merge_same_pitch(midi, max_gap=0.04)   # re-join one note that got cut in two
        if instrument == "hum":
            _drop_weak_short_notes(midi, short=0.12, keep_share=0.5)
        if settings["mono"]:
            _trim_note_ends(midi, rms, hop_s)
            _clean_fragments(midi)
    if settings["mono"]:
        _make_monophonic(midi)
    # Download MIDI keeps the performance's real timing (no grid snapping, no
    # leading rest); only the sheet music below is quantized.
    for inst in midi.instruments:
        inst.name = settings["title"]
    import copy
    out_midi = copy.deepcopy(midi)
    if settings["mono"]:
        _ensure_gap(out_midi)
    raw_buf = io.BytesIO()
    out_midi.write(raw_buf)
    raw_midi_bytes = raw_buf.getvalue()
    onsets = [n.start for i in midi.instruments for n in i.notes]
    bpm = _refine_bpm(onsets, prior)
    # Stamp the downloaded MIDI with the same tempo shown on the page (not the
    # first rough guess), keeping every note at the same real-time position.
    import pretty_midi
    fixed = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    for inst in out_midi.instruments:
        ni = pretty_midi.Instrument(program=inst.program, name=inst.name)
        ni.notes = list(inst.notes)
        fixed.instruments.append(ni)
    raw_buf = io.BytesIO()
    fixed.write(raw_buf)
    raw_midi_bytes = raw_buf.getvalue()
    beats, downbeat = _detect_meter(midi, bpm)
    midi = _quantize_midi(midi, bpm, beats, downbeat)
    if settings["mono"]:
        _force_single_line(midi)
    else:
        _force_chord_line(midi)

    if instrument == "hum":
        # Hummed lines: the downloaded MIDI is the grid-snapped version too, so
        # notes start on the beat and are separate (a short rest after each),
        # instead of the raw wobbly timing that sounds like fumbling.
        grid = copy.deepcopy(midi)
        _ensure_gap(grid, gap=0.10, min_len=0.08, max_trim=0.5)
        for inst in grid.instruments:
            inst.name = settings["title"]
        gbuf = io.BytesIO()
        grid.write(gbuf)
        raw_midi_bytes = gbuf.getvalue()

    # Name the track so DAWs (FL Studio's import dialog) list it instead of a blank row.
    for inst in midi.instruments:
        inst.name = settings["title"]

    note_count = sum(len(i.notes) for i in midi.instruments)
    if note_count == 0:
        raise NotationError("No notes were detected in this stem.")

    buf = io.BytesIO()
    midi.write(buf)
    midi_bytes = buf.getvalue()

    xml = _midi_to_musicxml(midi_bytes, settings["title"], bpm, beats)
    # notation staff with the tablature staff underneath; no note-letter labels
    xml = _add_tablature(xml, instrument)
    return {"midi": raw_midi_bytes, "musicxml": xml, "bpm": bpm, "note_count": note_count}


def preview(xml, max_measures=8):
    """Free-tier snippet: keep only the first few measures of every part.
    Tempo, key and time signature live in the first measure, so they stay."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    for part in root.findall("part"):
        for m in part.findall("measure")[max_measures:]:
            part.remove(m)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
