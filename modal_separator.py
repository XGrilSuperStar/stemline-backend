"""
Stemline GPU separation service on Modal.

Vocals come from BS-Roformer (much cleaner than Demucs' vocal stem).
Drums / bass / guitar / piano / other come from Demucs htdemucs_6s.
Returns a zip of six mp3s named vocals, drums, bass, guitar, piano, other.

Deploy:   modal deploy modal_separator.py
Secret:   modal secret create stemline-auth STEMLINE_SECRET=<long random string>

API (all need header  X-Stemline-Secret):
  POST /submit            raw audio bytes in body  ->  {"call_id": "..."}
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


@app.function(
    gpu="A10G",
    image=image,
    timeout=1200,
    volumes={MODEL_DIR: models_vol},
    # Stay warm briefly after a job so back-to-back splits skip the model load,
    # then scale to zero so an idle GPU never bills.
    scaledown_window=300,
)
def separate(audio: bytes) -> bytes:
    import glob, io, shutil, subprocess, tempfile, time, zipfile

    work = tempfile.mkdtemp(prefix="sep_")
    src = os.path.join(work, "song.wav")
    raw = os.path.join(work, "upload.bin")
    open(raw, "wb").write(audio)

    # Full-length stereo 44.1k WAV, same as the backend does for Demucs.
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-vn", "-ar", "44100",
         "-ac", "2", "-c:a", "pcm_s16le", src],
        check=True,
    )

    # --- Demucs 6-stem (same settings as production) ---
    t = time.time()
    demucs_out = os.path.join(work, "demucs")
    subprocess.run(
        ["demucs", "-n", "htdemucs_6s", "-d", "cuda", "--shifts", "1", "--overlap", "0.5",
         "--mp3", "--mp3-bitrate", "192", "-o", demucs_out, src],
        check=True,
    )
    print(f"demucs {time.time() - t:.1f}s")
    stem_dir = os.path.join(demucs_out, "htdemucs_6s", "song")

    # --- BS-Roformer vocals ---
    t = time.time()
    from audio_separator.separator import Separator

    rof_out = os.path.join(work, "roformer")
    sep = Separator(
        output_dir=rof_out,
        model_file_dir=f"{MODEL_DIR}/audio-separator",
        output_single_stem="Vocals",
        output_format="WAV",
        use_autocast=True,  # fp16 on the GPU: much faster, no audible quality change
        mdxc_params={"batch_size": 4, "overlap": 8, "segment_size": 256},
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
    # Replace Demucs' vocals with the Roformer ones, as 192k mp3 to match.
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", voc, "-b:a", "192k",
         os.path.join(stem_dir, "vocals.mp3")],
        check=True,
    )

    models_vol.commit()  # persist any freshly downloaded weights

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name in STEMS:
            z.write(os.path.join(stem_dir, f"{name}.mp3"), f"{name}.mp3")
    shutil.rmtree(work, ignore_errors=True)
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
