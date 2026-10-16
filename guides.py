"""Public guide pages for Stemline101 (static, server-rendered HTML)."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

BASE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>%%TITLE%% — Stemline101</title>
<meta name="description" content="%%DESC%%">
<link rel="canonical" href="https://stemline101.com%%PATH%%">
<style>
  body { background:#111; color:#eee; font-family: system-ui, sans-serif;
         max-width: 720px; margin: 0 auto; padding: 2rem 1.5rem 6rem; line-height: 1.7; }
  h1 { color: #f0a500; line-height: 1.25; }
  h2 { color: #f0a500; margin-top: 2.2rem; font-size: 1.2rem; }
  a { color: #f0a500; }
  .lede { font-size: 1.1rem; color: #ccc; }
  .more { margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid #333; }
  ul, ol { padding-left: 1.4rem; }
  li { margin-bottom: 0.5rem; }
  .card { border:1px solid #333; border-radius:6px; padding:1rem 1.2rem; margin:1rem 0; background:#161616; }
  .card h2 { margin-top:0; }
</style>
</head>
<body>
<a href="/" style="display:inline-block;margin-bottom:1.5rem;color:#f0a500;text-decoration:none;">&larr; Back to Stemline101</a>
%%BODY%%
<div class="more">
  <p><strong>More guides:</strong>
  <a href="/guides">All guides</a> ·
  <a href="/guides/what-are-stems">What are stems?</a> ·
  <a href="/guides/how-ai-stem-separation-works">How AI separation works</a> ·
  <a href="/guides/mixing-stems-bpm-and-key">BPM and key basics</a> ·
  <a href="/guides/getting-cleaner-stems">Getting cleaner stems</a></p>
  <p><a href="/about">About</a> · <a href="/faq">FAQ</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></p>
</div>
<div id="cookie-banner" style="position:fixed; bottom:0; left:0; right:0; background:#1a1a1a; color:#eee; padding:1rem 1.5rem; border-top:1px solid #333; font-family: system-ui, sans-serif; font-size:0.9rem; z-index:9999; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:1rem;">
  <span>We use cookies for essential site function and, with your consent, for advertising. See our <a href="/privacy" style="color:#f0a500;">Privacy Policy</a>.</span>
  <span>
    <button onclick="document.cookie='stemline_consent=accepted; max-age=31536000; path=/'; document.getElementById('cookie-banner').style.display='none';" style="background:#f0a500; color:#111; border:none; padding:0.5rem 1.2rem; border-radius:4px; font-weight:600; cursor:pointer; margin-right:0.5rem;">Accept</button>
    <button onclick="document.cookie='stemline_consent=denied; max-age=31536000; path=/'; document.getElementById('cookie-banner').style.display='none';" style="background:transparent; color:#eee; border:1px solid #555; padding:0.5rem 1.2rem; border-radius:4px; cursor:pointer;">Deny Non-Essential</button>
  </span>
</div>
<script>
  if (document.cookie.indexOf('stemline_consent=') !== -1) {
    var b = document.getElementById('cookie-banner');
    if (b) b.style.display = 'none';
  }
</script>
</body>
</html>
"""


def render(title, desc, path, body):
    return (
        BASE.replace("%%TITLE%%", title)
        .replace("%%DESC%%", desc)
        .replace("%%PATH%%", path)
        .replace("%%BODY%%", body)
    )


INDEX_BODY = """
<h1>Stemline101 Guides</h1>
<p class="lede">Plain-English guides to audio stems, AI stem separation, and mixing parts from different songs together.</p>

<div class="card">
  <h2><a href="/guides/what-are-stems">What Are Audio Stems?</a></h2>
  <p>A beginner's guide to stems: what they are, how they differ from multitracks and masters, and what people use them for.</p>
</div>
<div class="card">
  <h2><a href="/guides/how-ai-stem-separation-works">How AI Stem Separation Works</a></h2>
  <p>How a model can pull vocals, drums, and bass out of a finished song, and why the results are good but never perfect.</p>
</div>
<div class="card">
  <h2><a href="/guides/mixing-stems-bpm-and-key">Mixing Stems from Different Songs: BPM and Key Basics</a></h2>
  <p>How to match tempo and key so parts from different tracks sound like they belong together.</p>
</div>
<div class="card">
  <h2><a href="/guides/getting-cleaner-stems">How to Get Cleaner Stems from Any Song</a></h2>
  <p>Practical tips on source files, dense mixes, and mixer settings that reduce bleed and artifacts.</p>
</div>
"""

WHAT_ARE_STEMS_BODY = """
<h1>What Are Audio Stems?</h1>
<p class="lede">A stem is one part of a song, such as just the vocals or just the drums, saved as its own audio file.</p>

<h2>The short version</h2>
<p>When a song is recorded, it usually starts as dozens of separate tracks: a kick drum microphone, a bass guitar, several vocal takes, synth layers, and more. Those tracks get blended together into one stereo file, which is the song you hear on streaming services. A stem sits between those two extremes. Instead of dozens of individual tracks or one finished mix, you get a handful of groups: all the drums together, all the vocals together, all the bass together, and so on.</p>

<h2>Stems, multitracks, and the master</h2>
<ul>
  <li><strong>Multitrack:</strong> every individual recorded track, often 24 to 100 or more. Producers and engineers work with these.</li>
  <li><strong>Stems:</strong> the multitrack grouped into a few submixes, typically 4 to 8. Each group keeps its own balance, effects, and processing.</li>
  <li><strong>Master:</strong> the final blend of everything, as released.</li>
</ul>
<p>A useful way to remember it: if you add all the stems back together at their original levels, you get the full song again.</p>

<h2>Common stem groups</h2>
<p>There is no single standard, but most separations use some version of these:</p>
<ul>
  <li><strong>Vocals:</strong> lead and backing vocals.</li>
  <li><strong>Drums:</strong> kick, snare, hi-hats, cymbals, and percussion.</li>
  <li><strong>Bass:</strong> bass guitar or synth bass.</li>
  <li><strong>Guitar and keys or synth:</strong> melodic and harmonic instruments, sometimes split further.</li>
  <li><strong>Other:</strong> everything that does not fit the groups above, such as strings, effects, and ambient sounds.</li>
</ul>

<h2>What people use stems for</h2>
<ul>
  <li><strong>DJing and live sets:</strong> layering the vocal from one track over the instrumental of another, or dropping the drums out of a song for a breakdown.</li>
  <li><strong>Remixes and mashups:</strong> building something new from existing parts.</li>
  <li><strong>Practice:</strong> muting the bass or guitar to play along with the rest of the band.</li>
  <li><strong>Karaoke and covers:</strong> removing the lead vocal.</li>
  <li><strong>Study:</strong> soloing one instrument to hear exactly what it is playing.</li>
  <li><strong>Sampling:</strong> grabbing a clean drum break or vocal phrase without the rest of the mix underneath it.</li>
</ul>

<h2>Where stems come from</h2>
<p>Some artists and labels release official stems, especially for remix contests. Producers export stems from their own projects all the time. For everything else, AI separation tools can estimate the stems from a finished song. You can read how that works in our guide to <a href="/guides/how-ai-stem-separation-works">how AI stem separation works</a>.</p>

<h2>A note on rights</h2>
<p>Separating a song does not change who owns it. Use stems from music you own or have permission to use, and check the licensing before you release or perform anything built from someone else's recording.</p>

<h2>Try it</h2>
<p>Stemline101 splits a track into five stems (vocals, drums, bass, guitar, and other) and lets you mix stems from different songs on one board. <a href="/">Open the mixer</a>.</p>
"""

AI_SEPARATION_BODY = """
<h1>How AI Stem Separation Works</h1>
<p class="lede">A finished song is a single audio signal with everything already blended together. Separation models learn to estimate what each ingredient sounded like before the blend.</p>

<h2>Why this is a hard problem</h2>
<p>Mixing is like pouring several colors of paint into one bucket. The sound waves from the voice, the drums, and the bass are added together into one waveform, and there is no simple way to subtract them back out. The same frequencies often overlap too: a kick drum and a bass guitar both live in the low end, and a snare and a vocal consonant can occupy similar ranges. A model cannot just filter by pitch.</p>

<h2>Step one: look at the sound as a picture</h2>
<p>Many separation models start by converting audio into a spectrogram, an image-like view with time on one axis, frequency on the other, and brightness showing loudness. In a spectrogram, different instruments have recognizable shapes. Drum hits show up as short vertical bursts. Sustained synth pads look like long horizontal bands. A voice shows a stack of evenly spaced lines for its harmonics, shifting as the pitch changes.</p>

<h2>Step two: learn from examples</h2>
<p>To teach a model what these shapes mean, researchers train it on large sets of multitrack recordings where the individual parts are known. The training loop is simple in principle: mix the parts together, give the model only the mix, and ask it to predict each part. The prediction is compared with the real stem, and the model is adjusted to reduce the error. After many millions of examples, the model becomes good at recognizing what a vocal, a drum kit, or a bass line tends to look like and sound like.</p>

<h2>Waveform models, spectrogram models, and hybrids</h2>
<ul>
  <li><strong>Spectrogram models</strong> predict a mask over the spectrogram that keeps the parts belonging to one instrument and suppresses the rest.</li>
  <li><strong>Waveform models</strong> work on the raw audio directly, which can preserve phase and the sharp attack of drum hits.</li>
  <li><strong>Hybrid models</strong> do both and combine the results. Meta's open-source Demucs family is a well-known example of this approach.</li>
</ul>

<h2>Why results are good but not perfect</h2>
<p>The model is estimating, not recovering. The original stems are gone for good once a song is mixed, so the output is the model's best reconstruction. That is why you may hear:</p>
<ul>
  <li><strong>Bleed:</strong> a faint trace of drums in the vocal stem, or a ghost of the vocal in the "other" stem.</li>
  <li><strong>Artifacts:</strong> a slightly watery or phasey quality, most noticeable on isolated vocals and cymbals.</li>
  <li><strong>Misplaced sounds:</strong> a keyboard or synth part landing in the "other" stem when you expected it elsewhere, because the model has to decide where a sound belongs.</li>
</ul>
<p>Dense mixes, heavy reverb, and instruments that sound alike are the hardest cases.</p>

<h2>Why it takes a while</h2>
<p>Separation models are large and do a lot of math for every second of audio. Longer songs take longer, and processing is faster on a graphics card (GPU) than on a regular processor. That is why splitting a full track can take a minute or more rather than a moment.</p>

<h2>What to expect in practice</h2>
<p>Modern separation is good enough for DJ sets, practice, remixing, and sampling, especially when the stems sit in a full mix with other parts. It is less suited to situations where you need studio-clean isolated tracks. If you want to get the best results, read our tips on <a href="/guides/getting-cleaner-stems">getting cleaner stems</a>.</p>

<p><a href="/">Try splitting a song in Stemline101</a>.</p>
"""

MIXING_BODY = """
<h1>Mixing Stems from Different Songs: BPM and Key Basics</h1>
<p class="lede">Parts from two different songs only sound right together if they share a tempo and fit the same musical key. Here is how to line them up.</p>

<h2>Start with tempo (BPM)</h2>
<p>BPM, or beats per minute, is how fast a song is. If a drum stem at 100 BPM plays under a vocal recorded at 124 BPM, the beats drift apart within seconds. To fix that, change one or both stems until they match.</p>
<ul>
  <li><strong>Time-stretching</strong> speeds up or slows down audio without changing its pitch. Small changes sound natural. Large ones introduce a smeared or robotic quality, particularly on vocals.</li>
  <li><strong>A good rule of thumb:</strong> try to stay within about 5 to 8 percent of the original tempo. Beyond that, results depend heavily on the material.</li>
  <li><strong>Half-time and double-time:</strong> a 70 BPM track often feels compatible with a 140 BPM track because one beat of the slower song equals two of the faster one. Look for these pairs before stretching too far.</li>
</ul>

<h2>Then match the key</h2>
<p>Two stems can be perfectly in time and still clash if they are in different keys. A vocal in A minor over a bass line in F-sharp minor will sound off, because many notes do not belong together.</p>
<ul>
  <li><strong>Same key</strong> is the safest pairing.</li>
  <li><strong>Relative major and minor</strong> share the same notes. C major and A minor are the classic example.</li>
  <li><strong>Neighboring keys</strong> are close enough to blend well. DJs often use the Camelot wheel, a numbered chart of keys, where matching numbers, numbers one step apart, or the same number with the A and B letters swapped are generally compatible.</li>
</ul>

<h2>Pitch shifting to fit</h2>
<p>If two stems are in different keys, shift one of them up or down in semitones. Shifting by one or two semitones usually sounds fine. Larger moves change the character of voices and instruments, so they work best on drums and bass, and less well on vocals. Drums have no pitch of their own to worry about, which makes them the easiest stem to reuse across keys.</p>

<h2>Line up the beat and the phrase</h2>
<p>Matching BPM keeps stems in time, but they also need to start in the right place. Songs are built from phrases, usually 4, 8, or 16 bars long. Start a new stem on the first beat of a phrase in the other track so the downbeats line up and the sections change together.</p>

<h2>Keep the mix from getting crowded</h2>
<ul>
  <li><strong>Pick one bass.</strong> Two bass lines at once fight for the same low frequencies and turn muddy.</li>
  <li><strong>Pick one lead.</strong> Two lead vocals compete unless one is clearly in the background.</li>
  <li><strong>Use EQ to make room.</strong> Roll off some low end on a vocal or guitar stem so it does not collide with the bass and drums.</li>
  <li><strong>Balance the levels.</strong> Stems from different songs come at different loudness. Adjust the gain on each channel until they sit together.</li>
</ul>

<h2>A simple workflow</h2>
<ol>
  <li>Choose two songs with similar tempos or half-time and double-time relationships.</li>
  <li>Split both into stems.</li>
  <li>Load the drums and bass from the first song and the vocal from the second.</li>
  <li>Match the tempo, then shift the key if the vocal clashes.</li>
  <li>Set where each stem starts, check the downbeats, and adjust the levels and EQ.</li>
</ol>

<h2>Doing this in Stemline101</h2>
<p>The mixer has a master tempo control, a key control with Key Lock, per-channel EQ and gain, and a +CUE button that sets where an individual stem starts playing. <a href="/">Open the mixer</a> and try loading stems from two different songs. If your stems sound rough, our guide to <a href="/guides/getting-cleaner-stems">getting cleaner stems</a> can help.</p>
"""

CLEANER_BODY = """
<h1>How to Get Cleaner Stems from Any Song</h1>
<p class="lede">You cannot make a separation model perfect, but a few choices before and after splitting make a noticeable difference.</p>

<h2>Start with the best file you have</h2>
<ul>
  <li><strong>Use WAV or a high-bitrate MP3</strong> from a source you legally own. Heavily compressed audio has already lost detail the model would use to tell instruments apart.</li>
  <li><strong>Avoid files that were re-encoded several times.</strong> Each round of lossy compression adds artifacts that the model can mistake for part of an instrument.</li>
  <li><strong>Choose the original release</strong> over a live recording, a bootleg, or a version with applause and room noise, when you have the option.</li>
</ul>

<h2>Know which songs separate well</h2>
<p>Some music is easy for a model and some is hard.</p>
<ul>
  <li><strong>Easier:</strong> clearly arranged songs where each instrument has its own space, such as pop and hip hop productions with a clean vocal, punchy drums, and a distinct bass.</li>
  <li><strong>Harder:</strong> dense or distorted arrangements, wall-of-sound rock, heavy reverb, orchestral recordings, and music where several instruments play the same notes together.</li>
  <li><strong>Very loud masters</strong> can be tricky because limiting and clipping squash the differences between sounds.</li>
</ul>

<h2>Expect some bleed</h2>
<p>A little leakage between stems is normal. A faint hi-hat in the vocal stem or a trace of vocal in the "other" stem is the model making a judgement call, not a sign that something went wrong. Our guide to <a href="/guides/how-ai-stem-separation-works">how AI stem separation works</a> explains why.</p>

<h2>Clean up with the mixer</h2>
<ul>
  <li><strong>Use EQ to hide bleed.</strong> If a bass stem has a bit of cymbal hiss, pull the high band down. If a vocal has low rumble, pull the low band down.</li>
  <li><strong>Let the full mix mask it.</strong> Bleed is far less noticeable when the stem plays alongside the others than when it is soloed. Judge a stem in context, not just on its own.</li>
  <li><strong>Lower the stem slightly</strong> if its artifacts stand out. A small gain reduction often hides them.</li>
  <li><strong>Check the "other" stem.</strong> Instruments like keys, strings, and effects can end up there. Listen to it before you decide a part is missing.</li>
</ul>

<h2>Pick the right stems for the job</h2>
<p>Different stems tolerate separation differently. Drums and bass usually come out strong and are the easiest to reuse. Vocals are the most revealing because any watery or phasey sound stands out. For a mashup, you may get the most polished result by using a vocal under a full instrumental from another track, rather than soloing the vocal by itself.</p>

<h2>When results are not good enough</h2>
<p>If a particular song never separates cleanly, try a different version of the track, such as the radio edit or the original studio mix, before giving up. Different masters of the same song can separate differently.</p>

<p>Ready to try it? <a href="/">Split a song in Stemline101</a>, or read about <a href="/guides/mixing-stems-bpm-and-key">matching BPM and key</a> when you start mixing stems from different songs.</p>
"""


@router.get("/guides", response_class=HTMLResponse)
async def guides_index():
    return render(
        "Guides",
        "Plain-English guides to audio stems, AI stem separation, and mixing stems from different songs.",
        "/guides",
        INDEX_BODY,
    )


@router.get("/guides/what-are-stems", response_class=HTMLResponse)
async def guide_what_are_stems():
    return render(
        "What Are Audio Stems?",
        "A beginner's guide to audio stems: what they are, how they differ from multitracks and masters, and how people use them.",
        "/guides/what-are-stems",
        WHAT_ARE_STEMS_BODY,
    )


@router.get("/guides/how-ai-stem-separation-works", response_class=HTMLResponse)
async def guide_how_ai_separation_works():
    return render(
        "How AI Stem Separation Works",
        "How AI models separate vocals, drums, and bass from a finished song, and why results are good but never perfect.",
        "/guides/how-ai-stem-separation-works",
        AI_SEPARATION_BODY,
    )


@router.get("/guides/mixing-stems-bpm-and-key", response_class=HTMLResponse)
async def guide_mixing_stems():
    return render(
        "Mixing Stems from Different Songs: BPM and Key Basics",
        "How to match tempo and key so stems from different songs sound good together.",
        "/guides/mixing-stems-bpm-and-key",
        MIXING_BODY,
    )


@router.get("/guides/getting-cleaner-stems", response_class=HTMLResponse)
async def guide_cleaner_stems():
    return render(
        "How to Get Cleaner Stems from Any Song",
        "Practical tips on source files, dense mixes, and mixer settings that reduce bleed and artifacts in separated stems.",
        "/guides/getting-cleaner-stems",
        CLEANER_BODY,
    )
