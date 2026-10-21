"""Bass cleaner loop.

Plain capped loop (no AI model in it): measure the bass stem, clean it,
measure again, and stop as soon as the score hits the target or the
try cap is reached. Always keeps the best-scoring version.

Score (0-100) is based on "leak": how much energy sits above the bass
range compared with the bass range itself. A clean bass stem is almost
all low frequencies; hats, vocals and guitar bleeding in show up as
energy up high. This is a starting metric meant to be tuned by ear.

Try 1 = the stem as it came out of the split.
Tries 2..N = progressively stronger cleanups, each applied to the
ORIGINAL stem (never stacked on a previous cleanup), so quality can't
erode round after round.

Env vars:
  BASS_CLEANER            "on" / "off" (default off)
  BASS_CLEANER_TARGET     stop when score >= this (default 80)
  BASS_CLEANER_MAX_TRIES  hard cap, first pass included (default 3)
"""
import logging
import os
import subprocess

import numpy as np
from scipy import signal

logger = logging.getLogger("bass_cleaner")

SAMPLE_RATE = 22050
BASS_LOW_HZ = 30
BASS_HIGH_HZ = 250
LEAK_ABOVE_HZ = 800

# leak (dB, energy above LEAK_ABOVE_HZ relative to bass band)
# <= LEAK_CLEAN_DB scores 100, >= LEAK_DIRTY_DB scores 0.
LEAK_CLEAN_DB = -35.0
LEAK_DIRTY_DB = -10.0

# A cleanup that makes the stem much quieter has probably eaten real bass.
MIN_LEVEL_KEPT = 0.6

# Cleanup strength per re-clean round (applied to the original stem).
CLEAN_FILTERS = [
    "highpass=f=30,lowpass=f=2500",
    "highpass=f=30,lowpass=f=1500,afftdn=nr=12:nf=-45",
    "highpass=f=30,lowpass=f=1000,afftdn=nr=18:nf=-45",
]


def enabled() -> bool:
    return os.getenv("BASS_CLEANER", "off").strip().lower() in ("1", "on", "true", "yes")


def _load_mono(path: str) -> np.ndarray:
    """Decode any audio file to mono float32 at SAMPLE_RATE via ffmpeg."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", path,
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-",
    ]
    out = subprocess.run(cmd, capture_output=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {out.stderr[-200:]!r}")
    return np.frombuffer(out.stdout, dtype=np.float32)


def measure(path: str) -> dict:
    """Return {"score", "leak_db", "rms"} for a stem file."""
    audio = _load_mono(path)
    if audio.size < SAMPLE_RATE:  # under a second: nothing to judge
        return {"score": 0.0, "leak_db": 0.0, "rms": 0.0}
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < 1e-5:  # silent stem
        return {"score": 0.0, "leak_db": 0.0, "rms": rms}

    freqs, psd = signal.welch(audio, fs=SAMPLE_RATE, nperseg=4096)
    bass = psd[(freqs >= BASS_LOW_HZ) & (freqs <= BASS_HIGH_HZ)].sum()
    high = psd[freqs >= LEAK_ABOVE_HZ].sum()
    leak_db = 10.0 * np.log10((high + 1e-12) / (bass + 1e-12))

    span = LEAK_DIRTY_DB - LEAK_CLEAN_DB
    score = 100.0 * (LEAK_DIRTY_DB - leak_db) / span
    score = float(min(100.0, max(0.0, score)))
    return {"score": score, "leak_db": float(leak_db), "rms": rms}


def _clean(src: str, dst: str, filter_chain: str) -> bool:
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, "-af", filter_chain, dst]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=400)
    return res.returncode == 0 and os.path.exists(dst)


def run_loop(stem_path: str, target: float = None, max_tries: int = None) -> dict:
    """Run the capped clean loop on one bass stem file, in place.

    Returns a summary dict: {"tries", "start_score", "final_score",
    "improved", "stopped"} where stopped is "target", "cap" or "error".
    The stem file is only replaced if a cleaned version scored better.
    """
    if target is None:
        target = float(os.getenv("BASS_CLEANER_TARGET", "80"))
    if max_tries is None:
        max_tries = int(os.getenv("BASS_CLEANER_MAX_TRIES", "3"))
    max_tries = max(1, min(max_tries, 1 + len(CLEAN_FILTERS)))

    ext = os.path.splitext(stem_path)[1]
    original = measure(stem_path)
    best = original
    best_path = None
    tries = 1
    stopped = "cap"
    logger.info(f"bass cleaner try 1 (original): score {original['score']:.0f}, leak {original['leak_db']:.1f} dB")

    try:
        if original["rms"] == 0.0 or original["score"] >= target:
            stopped = "target" if original["score"] >= target else "cap"
        else:
            for round_idx in range(max_tries - 1):
                tries += 1
                cand_path = f"{stem_path}.clean{round_idx}{ext}"
                if not _clean(stem_path, cand_path, CLEAN_FILTERS[round_idx]):
                    logger.warning(f"bass cleaner try {tries}: ffmpeg failed, stopping")
                    stopped = "error"
                    break
                cand = measure(cand_path)
                kept = cand["rms"] / original["rms"] if original["rms"] else 0.0
                logger.info(f"bass cleaner try {tries}: score {cand['score']:.0f}, leak {cand['leak_db']:.1f} dB, level kept {kept:.2f}")
                if kept >= MIN_LEVEL_KEPT and cand["score"] > best["score"]:
                    if best_path and os.path.exists(best_path):
                        os.remove(best_path)
                    best, best_path = cand, cand_path
                else:
                    os.remove(cand_path)
                if best["score"] >= target:
                    stopped = "target"
                    break
        if best_path:
            os.replace(best_path, stem_path)
    finally:
        for i in range(len(CLEAN_FILTERS)):
            leftover = f"{stem_path}.clean{i}{ext}"
            if os.path.exists(leftover):
                os.remove(leftover)

    return {
        "tries": tries,
        "start_score": original["score"],
        "final_score": best["score"],
        "improved": best_path is not None,
        "stopped": stopped,
    }
