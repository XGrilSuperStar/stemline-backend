"""
Stemline GPU separation service on Modal.

Vocals come from BS-Roformer (much cleaner than Demucs' vocal stem).
Drums / bass / guitar / piano / other come from Demucs htdemucs_6s.
Returns a zip of six mp3s named vocals, drums, bass, guitar, piano, other
(the server folds piano into other, so users only ever see five stems).

Deploy:   modal deploy modal_separator.py
Secret:   modal secret create stemline-auth STEMLINE_SECRET=<long random string>

API (all need header  X-Stemline-Secret):
  POST /submit            raw audio bytes in body  ->  {"call_id": "..."}
  POST /submit-bass       raw audio bytes (a bass stem) -> {"call_id": "..."}; result is a bass mp3
  GET  /result/{call_id}  ->  202 while running, 200 + zip when done, 500 on failure
"""
import os
import modal

app = modal.App("stemline-separator")

MODEL_DIR = "/models"
models_vol = modal.Volume.from_name("stemline-models", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("audio-separator[gpu]", "demucs", "soundfile", "fastapi[standard]")
    .env({"TORCH_HOME": f"{MODEL_DIR}/torch"})
)

ROFORMER_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
STEMS = ["vocals", "drums", "bass", "guitar", "piano", "other"]


def _decode_to_wav(audio: bytes, work: str) -> str:
    """Full-length stereo 44.1k WAV, same as the backend does for Demucs."""
    import subprocess
    raw = os.path.join(work, "upload.bin")
    src = os.path.join(work, "song.wav")
    open(raw, "wb").write(audio)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-vn", "-ar", "44100",
         "-ac", "2", "-c:a", "pcm_s16le", src],
        check=True,
    )
    return src


# Demucs and BS-Roformer used to run one after the other on a single GPU.
# They don't depend on each other, so each now gets its own GPU and they run
# at the same time: a split takes as long as the slower of the two, not the
# sum. GPU-seconds (and cost) stay about the same.
@app.function(
    gpu="A10G",
    image=image,
    timeout=1200,
    volumes={MODEL_DIR: models_vol},
    scaledown_window=300,
)
def run_demucs(audio: bytes) -> dict:
    """Demucs htdemucs_6s. Returns {"vocals": mp3 bytes, ..., "other": mp3 bytes}."""
    import shutil, subprocess, tempfile, time

    work = tempfile.mkdtemp(prefix="dem_")
    src = _decode_to_wav(audio, work)
    t = time.time()
    demucs_out = os.path.join(work, "demucs")
    subprocess.run(
        ["demucs", "-n", "htdemucs_6s", "-d", "cuda", "--shifts", "1", "--overlap", "0.5",
         "--mp3", "--mp3-bitrate", "192", "-o", demucs_out, src],
        check=True,
    )
    print(f"demucs {time.time() - t:.1f}s")
    stem_dir = os.path.join(demucs_out, "htdemucs_6s", "song")
    out = {name: open(os.path.join(stem_dir, f"{name}.mp3"), "rb").read() for name in STEMS}
    models_vol.commit()  # persist any freshly downloaded weights
    shutil.rmtree(work, ignore_errors=True)
    return out


@app.function(
    gpu="A10G",
    image=image,
    timeout=1200,
    volumes={MODEL_DIR: models_vol},
    scaledown_window=300,
)
def run_roformer(audio: bytes) -> bytes:
    """BS-Roformer vocals only. Returns a 192k mp3."""
    import shutil, subprocess, tempfile, time

    work = tempfile.mkdtemp(prefix="rof_")
    src = _decode_to_wav(audio, work)
    t = time.time()
    from audio_separator.separator import Separator

    rof_out = os.path.join(work, "roformer")
    sep = Separator(
        output_dir=rof_out,
        model_file_dir=f"{MODEL_DIR}/audio-separator",
        output_single_stem="Vocals",
        output_format="WAV",
        use_autocast=True,  # fp16 on the GPU: much faster, no audible quality change
        mdxc_params={"batch_size": 4, "overlap": 4, "segment_size": 256},
    )
    sep.load_model(ROFORMER_MODEL)
    files = sep.separate(src)
    print(f"roformer {time.time() - t:.1f}s -> {files}")
    voc = None
    for f in files:
        p = f if os.path.isabs(f) else os.path.join(rof_out, f)
        if os.path.exists(p) and "ocals" in os.path.basename(p):
            voc = p
    if voc is None:
        raise RuntimeError(f"BS-Roformer produced no vocals file: {files}")
    out_mp3 = os.path.join(work, "vocals.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", voc, "-b:a", "192k", out_mp3],
        check=True,
    )
    data = open(out_mp3, "rb").read()
    models_vol.commit()  # persist any freshly downloaded weights
    shutil.rmtree(work, ignore_errors=True)
    return data


# Bass-only test engine: BS-RoFormer SW (jarredou), keeping just the bass stem.
# Only called by the backend AFTER a user saves a bass stem (BASS_ENGINE2=on).
# Checkpoint filename varies between audio-separator versions, so try a few;
# override with the BASS_SW_MODEL env var if needed.
BASS_SW_CANDIDATES = ["BS-Roformer-SW.ckpt", "BS-Rofo-SW-Fixed.ckpt"]


@app.function(
    gpu="A10G",
    image=image,
    timeout=1200,
    volumes={MODEL_DIR: models_vol},
    scaledown_window=300,
)
def run_bass_roformer(audio: bytes) -> bytes:
    """BS-RoFormer SW, bass stem only. Returns a 192k mp3."""
    import shutil, subprocess, tempfile, time

    work = tempfile.mkdtemp(prefix="bsw_")
    src = _decode_to_wav(audio, work)
    t = time.time()
    from audio_separator.separator import Separator

    out_dir = os.path.join(work, "bsw")
    sep = Separator(
        output_dir=out_dir,
        model_file_dir=f"{MODEL_DIR}/audio-separator",
        output_single_stem="Bass",
        output_format="WAV",
        use_autocast=True,
        mdxc_params={"batch_size": 4, "overlap": 4, "segment_size": 256},
    )
    candidates = [c for c in [os.environ.get("BASS_SW_MODEL")] + BASS_SW_CANDIDATES if c]
    loaded, last_err = None, None
    for name in candidates:
        try:
            sep.load_model(name)
            loaded = name
            break
        except Exception as e:
            last_err = e
            print(f"bass SW: could not load {name}: {e}")
    if not loaded:
        raise RuntimeError(f"No BS-RoFormer SW checkpoint could be loaded: {last_err}")

    files = sep.separate(src)
    print(f"bass SW ({loaded}) {time.time() - t:.1f}s -> {files}")
    bass = None
    for f in files:
        p = f if os.path.isabs(f) else os.path.join(out_dir, f)
        if os.path.exists(p) and "bass" in os.path.basename(p).lower():
            bass = p
    if bass is None:
        raise RuntimeError(f"BS-RoFormer SW produced no bass file: {files}")
    out_mp3 = os.path.join(work, "bass.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", bass, "-b:a", "192k", out_mp3],
        check=True,
    )
    data = open(out_mp3, "rb").read()
    models_vol.commit()
    shutil.rmtree(work, ignore_errors=True)
    return data


@app.function(image=modal.Image.debian_slim(python_version="3.11"), timeout=1200)
def separate(audio: bytes) -> bytes:
    """Fan out to both GPUs, then zip the six stems (same output as before)."""
    import io, time, zipfile

    t = time.time()
    dem_call = run_demucs.spawn(audio)
    rof_call = run_roformer.spawn(audio)
    stems = dem_call.get()
    try:
        stems["vocals"] = rof_call.get()
    except Exception as e:
        # Roformer failed: keep Demucs' own vocals rather than failing the split.
        print(f"roformer failed, using demucs vocals: {e}")
    print(f"separate total {time.time() - t:.1f}s")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name in STEMS:
            z.writestr(f"{name}.mp3", stems[name])
    return buf.getvalue()


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("stemline-auth")],
    scaledown_window=60,
)
@modal.asgi_app()
def web():
    import hmac
    from fastapi import FastAPI, Header, HTTPException, Request, Response

    api = FastAPI()
    secret = os.environ["STEMLINE_SECRET"]

    def check(x_stemline_secret):
        if not x_stemline_secret or not hmac.compare_digest(x_stemline_secret, secret):
            raise HTTPException(status_code=401, detail="unauthorized")

    @api.post("/submit")
    async def submit(request: Request, x_stemline_secret: str = Header(None)):
        check(x_stemline_secret)
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="empty body")
        call = separate.spawn(body)
        return {"call_id": call.object_id}

    @api.post("/submit-bass")
    async def submit_bass(request: Request, x_stemline_secret: str = Header(None)):
        check(x_stemline_secret)
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="empty body")
        call = run_bass_roformer.spawn(body)
        return {"call_id": call.object_id}

    @api.get("/result/{call_id}")
    async def result(call_id: str, x_stemline_secret: str = Header(None)):
        check(x_stemline_secret)
        call = modal.FunctionCall.from_id(call_id)
        try:
            data = call.get(timeout=0)
        except TimeoutError:
            return Response(status_code=202, content=b"running")
        except Exception as e:  # job itself failed
            return Response(status_code=500, content=str(e)[:500].encode())
        return Response(content=data, media_type="application/zip")

    return api
