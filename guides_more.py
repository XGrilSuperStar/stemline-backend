"""Additional public guide pages for Stemline101.

Each entry feeds the guides index, the "More guides" footer, the routes, and
the sitemap (see guides.py and main.py).
"""

MORE_GUIDES = [
    {
        "slug": "how-to-remove-vocals-from-a-song",
        "short": "Remove vocals",
        "title": "How to Remove Vocals from a Song (Instrumental and Acapella)",
        "desc": "How to remove vocals from a song or isolate them, why AI separation beats the old phase trick, and what results to expect.",
        "summary": "Make an instrumental or an acapella from any song, and why AI separation works far better than the old phase-cancellation trick.",
        "body": """
<h1>How to Remove Vocals from a Song (Instrumental and Acapella)</h1>
<p class="lede">Removing the vocal gives you an instrumental. Keeping only the vocal gives you an acapella. Both come from the same step: separating the song into stems.</p>

<h2>The old trick: phase cancellation</h2>
<p>Before AI tools, the common method was phase cancellation. A stereo song is two channels, left and right. If you flip the polarity of one channel and add the two together, anything that sits exactly in the center of the mix cancels out. Lead vocals are usually panned to the center, so they get quieter or disappear.</p>
<p>The trouble is that plenty of other things sit in the center too. The kick drum, the snare, and the bass guitar often go there as well, so they fade along with the voice. Reverb on the vocal is spread across both channels, so a ghostly echo of the voice stays behind. Mono recordings cannot be processed this way at all, because the two channels are identical and everything cancels. The result is usually thin, hollow, and full of artifacts.</p>

<h2>The modern way: AI stem separation</h2>
<p>AI separation models do not rely on panning. They learn what a voice looks and sounds like and estimate the vocal as its own track, while the drums, bass, guitar, and everything else stay intact. Because the vocal comes out as a separate stem, you can do either job: mute it for an instrumental, or solo it for an acapella. If you want the background on how this works, read <a href="/guides/how-ai-stem-separation-works">how AI stem separation works</a>.</p>

<h2>Making an instrumental</h2>
<ol>
  <li>Upload an MP3 or WAV and let it split into stems.</li>
  <li>Load all five stems onto the mixer.</li>
  <li>Mute the vocals channel.</li>
  <li>Play the song through and listen for leftovers. If you hear a faint echo of the voice, lowering the "other" stem a little or trimming its high end can hide it.</li>
</ol>
<p>This is the usual approach for karaoke, for practicing a vocal part, and for putting new vocals over an existing backing track.</p>

<h2>Making an acapella</h2>
<p>Solo the vocals channel, or mute everything else. The isolated voice is handy for mashups, for studying phrasing, and for remixes. An acapella pulled from a finished song will usually carry a trace of reverb tails and a little bleed from loud drums. Those are normal, and they are less noticeable once the acapella sits inside a new mix.</p>

<h2>What about backing vocals?</h2>
<p>Models tend to group lead and backing vocals together in the vocal stem, so muting that channel removes both. Some harmonies and ad-libs that are heavily processed can end up in the "other" stem instead. If a few background voices remain after you mute the vocals, check the "other" channel.</p>

<h2>Tips for better results</h2>
<ul>
  <li><strong>Start with the best file you have.</strong> A WAV or high-bitrate MP3 gives the model more detail to work with. See our guide to <a href="/guides/getting-cleaner-stems">getting cleaner stems</a>.</li>
  <li><strong>Pick songs with a clear vocal.</strong> Dry, upfront vocals separate more cleanly than ones buried in heavy reverb or layered with guitars.</li>
  <li><strong>Judge the instrumental in context.</strong> A faint vocal ghost is easy to hear when you listen alone with headphones, and much harder to notice at a party or under new vocals.</li>
</ul>

<h2>A note on rights</h2>
<p>Removing vocals does not change who owns the song. Use instrumentals and acapellas from music you own or have permission to use, and check the licensing before you perform or release anything built from someone else's recording.</p>

<p>Want to try it? <a href="/">Split a song in Stemline101</a>.</p>
""",
    },
    {
        "slug": "how-to-make-a-mashup",
        "short": "Make a mashup",
        "title": "How to Make a Mashup Using Stems",
        "desc": "A step-by-step guide to making a mashup: choosing songs, matching tempo and key, layering vocals over instrumentals, and mixing the result.",
        "summary": "A step-by-step project for blending the vocal from one song with the instrumental of another.",
        "body": """
<h1>How to Make a Mashup Using Stems</h1>
<p class="lede">A mashup puts parts of two or more songs together so they sound like one new track. Stems make that possible, because you can take the vocal from one song and the drums and bass from another.</p>

<h2>Step 1: Pick songs that can work together</h2>
<p>The best mashups start with a good pairing. Look for songs that share at least one of these:</p>
<ul>
  <li><strong>Similar tempo.</strong> Two songs within a few BPM of each other need very little stretching. Songs at half or double each other's speed also work well.</li>
  <li><strong>The same or a neighboring key.</strong> This keeps the vocal melody from clashing with the chords underneath.</li>
  <li><strong>Contrasting roles.</strong> A song with a strong vocal pairs nicely with a song that has a groove and a sparse top end. Two busy, vocal-heavy songs usually fight each other.</li>
</ul>
<p>Our guide to <a href="/guides/mixing-stems-bpm-and-key">BPM and key basics</a> covers how to check and match both.</p>

<h2>Step 2: Split both songs</h2>
<p>Upload each song and let it separate into stems. Splitting takes time, so do it ahead and keep the results in your library. Then you can load them quickly when you start mixing.</p>

<h2>Step 3: Choose a foundation and a topline</h2>
<p>Most mashups use one song as the foundation and another as the topline.</p>
<ul>
  <li><strong>Foundation:</strong> the drums and bass (and often the guitar or "other" stem) from one song.</li>
  <li><strong>Topline:</strong> the vocal from the second song.</li>
</ul>
<p>Load the foundation stems onto their channels, then add the vocal. Resist the urge to use everything. Two basslines or two lead vocals at the same time make the mix muddy and confusing.</p>

<h2>Step 4: Match tempo and key</h2>
<p>Bring the vocal and the foundation to the same tempo. Small adjustments sound natural, and large ones start to sound robotic, especially on vocals. Then listen for key clashes. If the vocal sounds off against the chords, shift its pitch by a semitone or two, or shift the foundation instead.</p>

<h2>Step 5: Line up the downbeats</h2>
<p>Even at the same tempo, the two parts need to start on the same beat. Songs are built in phrases of 4, 8, or 16 bars. Start the vocal where one of its phrases begins, and line that up with the start of a phrase in the foundation. If it feels slightly early or late, nudge the stem's start point until the downbeats hit together.</p>

<h2>Step 6: Balance and EQ</h2>
<ul>
  <li>Set the gain on each channel so no stem jumps out. Stems from different songs arrive at different loudness.</li>
  <li>Cut some low end from the vocal so it does not compete with the bass and kick.</li>
  <li>If the foundation has a prominent midrange part, make a little room by pulling that band down slightly where the vocal sits.</li>
</ul>

<h2>Step 7: Add shape</h2>
<p>A mashup that stays the same the whole way through gets boring. Try bringing stems in and out: start with only drums, add the bass, then bring the vocal in on a chorus. Drop the drums for a breakdown, then bring them back for the final section. Even simple changes in which stems are playing give the track a sense of movement.</p>

<h2>Common problems</h2>
<ul>
  <li><strong>It sounds crowded.</strong> Remove a stem. Fewer parts almost always sound better.</li>
  <li><strong>The vocal sounds robotic.</strong> You stretched or shifted it too far. Pick a different song, or move the other stems toward the vocal instead.</li>
  <li><strong>It feels off the beat.</strong> The downbeats are misaligned by a fraction. Adjust the start point rather than the tempo.</li>
  <li><strong>The vocal has a watery quality.</strong> That is a separation artifact. It is usually masked once the vocal plays with the rest of the mix.</li>
</ul>

<h2>A note on rights</h2>
<p>A mashup is built from other people's recordings. Using it privately or for practice is one thing, but releasing or performing it publicly may require permission from the rights holders. Check the licensing before you share anything widely.</p>

<p>Ready to build one? <a href="/">Open the Stemline101 mixer</a>.</p>
""",
    },
    {
        "slug": "how-to-make-a-ringtone-from-a-song",
        "short": "Make a ringtone",
        "title": "How to Make a Ringtone from a Song",
        "desc": "How to turn a favorite song into a custom ringtone, choose the best section, use stems for a cleaner loop, and set it on iPhone or Android.",
        "summary": "Pick the best 20 to 30 seconds of a song, clean it up with stems, and set it as your ringtone.",
        "body": """
<h1>How to Make a Ringtone from a Song</h1>
<p class="lede">A good ringtone is a short, recognizable slice of a song that you can hear over background noise. Here is how to pick one and, if you want, use stems to make it stronger.</p>

<h2>Step 1: Choose the right section</h2>
<p>You only need 20 to 30 seconds. A few things make a section work as a ringtone:</p>
<ul>
  <li><strong>A strong hook.</strong> The chorus or a memorable riff is easier to recognize than a verse.</li>
  <li><strong>A clear start.</strong> Pick a point where the sound begins on a beat, so the ringtone starts right away instead of fading in slowly.</li>
  <li><strong>Not too quiet.</strong> A soft intro will get lost in a pocket or a busy room.</li>
</ul>

<h2>Step 2: Decide what should play</h2>
<p>This is where stems help. Instead of using the whole song as-is, you can shape what you hear.</p>
<ul>
  <li><strong>Instrumental only.</strong> Mute the vocals if you want something less intrusive, especially for a work phone.</li>
  <li><strong>Drums and bass.</strong> A rhythmic ringtone that is punchy and easy to notice without any melody.</li>
  <li><strong>Vocal hook on its own.</strong> Solo the vocals to pull out one memorable line for a ringtone that is instantly recognizable.</li>
  <li><strong>Drop what is distracting.</strong> If a section has a busy guitar part you do not like, mute that stem and keep the rest.</li>
</ul>
<p>To get these stems, upload the song and let it separate. Our guide to <a href="/guides/how-to-remove-vocals-from-a-song">removing vocals from a song</a> walks through the basics.</p>

<h2>Step 3: Trim it to length</h2>
<p>Once you have the mix you like, export it and trim it in any audio editor. Some points to keep in mind:</p>
<ul>
  <li>iPhone ringtones are limited to 40 seconds. Android phones are more flexible, but 20 to 30 seconds is plenty for any phone.</li>
  <li>Cut at a natural boundary, such as the end of a phrase, so the loop does not sound chopped.</li>
  <li>Add a very short fade at the start and a longer one at the end to avoid clicks and an abrupt cutoff.</li>
</ul>

<h2>Step 4: Set it on your phone</h2>
<p>The exact steps depend on your phone and software version, so check your phone's own help pages if the menus look different.</p>
<ul>
  <li><strong>iPhone:</strong> ringtones use the .m4r format. You can convert and add the file with the Music app or Finder, or create one in GarageBand, then choose it under Settings, Sounds &amp; Haptics, Ringtone.</li>
  <li><strong>Android:</strong> most phones accept MP3 files. Copy the file into your phone's Ringtones folder, then choose it under Settings, Sound, Phone ringtone.</li>
</ul>

<h2>Tips for a ringtone you will not get sick of</h2>
<ul>
  <li>Test it in a noisy place. Something that sounds great with headphones can disappear in a car or a crowded room.</li>
  <li>Avoid very bass-heavy mixes, since small phone speakers cannot reproduce low frequencies.</li>
  <li>Keep the volume consistent. If you boost a quiet section, listen for distortion.</li>
</ul>

<h2>A note on rights</h2>
<p>Making a ringtone for your own phone from music you own is a very common personal use. Selling or distributing ringtones made from other people's recordings is a different matter and may require permission.</p>

<p>Want to try it? <a href="/">Split a song in Stemline101</a>.</p>
""",
    },
    {
        "slug": "dj-techniques-with-stems",
        "short": "DJ techniques",
        "title": "DJ Techniques with Stems: Transitions, Layering, and Bass Swaps",
        "desc": "Practical DJ techniques using stems: acapella over instrumental, bass swaps with EQ, drum layering, and building energy by adding and removing parts.",
        "summary": "Practical ways to use stems in a live set: bass swaps, acapella layering, drum loops, and building energy.",
        "body": """
<h1>DJ Techniques with Stems: Transitions, Layering, and Bass Swaps</h1>
<p class="lede">Stems turn a song from one block into separate parts you can bring in and out. That opens up transitions and layers that are hard to do with two finished tracks.</p>

<h2>Prepare before you play</h2>
<p>Splitting a song takes time, so do it ahead of your set. Build your library with the songs you plan to play, then load stems as you need them. It is also worth checking the tempo and key of the songs you want to blend. Our guide to <a href="/guides/mixing-stems-bpm-and-key">BPM and key basics</a> explains how to match them.</p>

<h2>Technique 1: Acapella over an instrumental</h2>
<p>This is the classic stem move. Keep the drums, bass, and other parts of the first song running, and bring in the vocal from a second song. It works best when both songs are close in tempo and in compatible keys. Start with the vocal channel's fader down, then bring it up on the first beat of a phrase.</p>

<h2>Technique 2: The bass swap</h2>
<p>When you blend two songs, both basslines playing at once sounds muddy. A bass swap solves that.</p>
<ol>
  <li>Bring in the new song with its low EQ turned down, so you hear the drums and top end but not its bass.</li>
  <li>Let both songs run together for a phrase or two.</li>
  <li>At a phrase change, pull the old song's low EQ down and bring the new song's low EQ up at the same time.</li>
</ol>
<p>With stems, you can do it even more cleanly by muting the old bass stem outright as you open the new one.</p>

<h2>Technique 3: Drum layering</h2>
<p>Laying the drums from one song under the music of another adds energy or changes the groove. A steady drum stem is also a useful bridge between two songs with different feels: bring in drums from the next song first, so the beat carries you over before the melody changes.</p>

<h2>Technique 4: Dropping parts for a breakdown</h2>
<p>Mute the drums for a few bars and let the vocal and the melody hang by themselves, then bring the drums back in on a downbeat. The contrast makes the return of the beat feel bigger. You can also do the opposite and drop the vocal to let the instrumental breathe.</p>

<h2>Technique 5: Building energy by adding parts</h2>
<p>A simple way to make a set feel like it is going somewhere is to add stems one at a time. Start with drums and bass, add the guitar or "other" stem, and save the vocal for last. Each new element lifts the energy without raising the overall volume.</p>

<h2>Keep the mix clean</h2>
<ul>
  <li><strong>One bass at a time.</strong> Always.</li>
  <li><strong>One lead vocal at a time.</strong> Two vocals compete unless one is clearly in the background.</li>
  <li><strong>Watch your levels.</strong> Stems from different songs arrive at different loudness. Set the gain on each channel before you rely on it.</li>
  <li><strong>Use EQ to carve space.</strong> Roll the lows off a vocal or guitar stem so it does not fight the kick and bass.</li>
</ul>

<h2>Phrasing matters</h2>
<p>Bring new parts in on the first beat of a phrase, usually every 8 or 16 bars. Transitions that land on a phrase boundary sound intentional, and transitions that land mid-phrase sound sloppy even when the tempo is perfectly matched.</p>

<h2>Practice and monitoring</h2>
<p>A separate headphone output lets you listen to a stem privately before it goes out to the room. Stemline's mixer has a cue output for this, which needs a second audio device to work. Practice your moves at home with a few favorite songs until bringing parts in and out feels automatic.</p>

<h2>A note on rights</h2>
<p>Performing mixes built from other people's recordings can require licenses, depending on where and how you play. Venues often hold the licenses for live performances, but check the rules for anything you record, stream, or release.</p>

<p>Ready to practice? <a href="/">Open the Stemline101 mixer</a>.</p>
""",
    },
    {
        "slug": "how-to-sample-drum-breaks-and-vocal-phrases",
        "short": "Sampling",
        "title": "How to Sample Drum Breaks and Vocal Phrases from Stems",
        "desc": "How to sample from a song: finding a drum break or vocal phrase, isolating it with stems, trimming it cleanly, and using it in your own music.",
        "summary": "Find a drum break or vocal phrase, isolate it, trim it cleanly, and put it to work in your own music.",
        "body": """
<h1>How to Sample Drum Breaks and Vocal Phrases from Stems</h1>
<p class="lede">Sampling means taking a short piece of a recording and reusing it. The hard part has always been getting the piece without the rest of the song on top of it. Stems make that much easier.</p>

<h2>What makes a good sample</h2>
<ul>
  <li><strong>A drum break:</strong> a section where the drums play alone or nearly alone, usually just a bar or two.</li>
  <li><strong>A vocal phrase:</strong> a short line, a shout, or an ad-lib that has a clear start and end.</li>
  <li><strong>A bass note or riff:</strong> a short pattern that loops cleanly.</li>
  <li><strong>A texture:</strong> a sustained chord, a sweep, or an ambient sound from the "other" stem.</li>
</ul>

<h2>Step 1: Find the part you want</h2>
<p>Listen to the song for sections where one instrument stands out. Intros, breakdowns, and the spaces between verses and choruses are good places to look. Make a note of where the sound starts and ends.</p>

<h2>Step 2: Isolate it with stems</h2>
<p>Upload the song and let it split. Then solo the stem that holds your sound: drums for a break, vocals for a phrase, bass for a riff. Because the other instruments are out of the way, you can hear the sample cleanly and pick the exact start and end points. Expect a little bleed from the other parts. A hint of vocal in a drum stem is normal, and it is less obvious once the sample sits in a new track.</p>

<h2>Step 3: Mark and trim the region</h2>
<p>Select the part of the waveform you want. A few tips:</p>
<ul>
  <li><strong>Start just before the first hit.</strong> Cutting right on the attack keeps the sample punchy. Starting a little early adds silence you can trim later.</li>
  <li><strong>End on a natural point.</strong> For a loop, end where the pattern would repeat. For a one-shot, let the sound ring out a bit before the cut.</li>
  <li><strong>Avoid clicks.</strong> If you cut in the middle of a loud waveform, you will hear a click. A very short fade in and out on the edges prevents it.</li>
</ul>
<p>In Stemline101, you can mark a region on a stem's waveform and save it to a sample library. The <a href="/sampler">sampler page</a> lets you trim it more precisely. Saved samples can be loaded back onto the mixer.</p>

<h2>Step 4: Make it fit your track</h2>
<ul>
  <li><strong>Tempo:</strong> if a drum break plays at a different speed than your project, stretch it to match. Small changes sound natural, and big ones can smear the hits.</li>
  <li><strong>Pitch:</strong> a vocal phrase or bass note may need shifting by a semitone or two so it matches your key. See our guide to <a href="/guides/mixing-stems-bpm-and-key">BPM and key basics</a>.</li>
  <li><strong>Layering:</strong> put a sampled snare on top of your own drum pattern to add character, or lay a vocal phrase over a new beat.</li>
</ul>

<h2>Creative ideas</h2>
<ul>
  <li>Chop a drum break into single hits and re-arrange them into a new pattern.</li>
  <li>Repeat a single vocal syllable as a rhythmic hook.</li>
  <li>Reverse a sample for a swell that leads into a drop.</li>
  <li>Lower the pitch of a sample to make it heavier, or raise it for a brighter, thinner sound.</li>
</ul>

<h2>A note on rights</h2>
<p>A sample is a piece of someone's recording and, usually, someone's composition too. Using samples privately while you practice or experiment is common. If you plan to release or sell something that contains a sample, you generally need clearance from the rights holders. Check the rules that apply to you before you publish.</p>

<p>Want to try it? <a href="/">Open Stemline101</a>.</p>
""",
    },
    {
        "slug": "practice-along-with-stems",
        "short": "Practice along",
        "title": "How to Practice Your Instrument Along with Stems",
        "desc": "How musicians use stems to practice: mute your part, play along with the rest of the band, slow things down, and learn parts by ear.",
        "summary": "Mute your own instrument and play along with the original band, slow tricky parts down, and learn by ear.",
        "body": """
<h1>How to Practice Your Instrument Along with Stems</h1>
<p class="lede">One of the best uses of stems has nothing to do with remixing. If you play bass, guitar, drums, or sing, you can take your own part out of a song and play it yourself with the rest of the band behind you.</p>

<h2>The basic idea</h2>
<p>Upload a song you want to learn, let it split into stems, and mute the channel for your instrument. Everything else keeps playing, so you get a backing track made from the real recording, not a generic one.</p>

<h2>By instrument</h2>
<ul>
  <li><strong>Bass players:</strong> mute the bass stem and lock in with the drums. This is a good way to work on feel and timing, since the kick and bass are meant to move together.</li>
  <li><strong>Guitarists:</strong> mute the guitar stem and play the parts yourself. If the song has both rhythm and lead guitar, check the "other" stem as well, since some parts can land there.</li>
  <li><strong>Drummers:</strong> mute the drums and play along to the bass, guitar, and vocals. It is a great way to practice keeping steady time when you have no click track.</li>
  <li><strong>Singers:</strong> mute the vocals for a karaoke-style backing track, or keep them quiet in the background as a guide while you learn the melody. Our guide to <a href="/guides/how-to-remove-vocals-from-a-song">removing vocals</a> has more.</li>
</ul>

<h2>Learn parts by ear</h2>
<p>Soloing a stem is also a way to hear what a player is doing. Solo the bass to catch the exact notes, or solo the drums to work out a fill. Hearing the part alone is much easier than trying to pick it out of a full mix. Then alternate: listen to the isolated part, play it yourself, and then play along with the full band.</p>

<h2>Slow it down</h2>
<p>A hard passage is easier to learn at a slower speed. Lower the tempo until you can play it cleanly, then gradually speed it back up. Use a tempo control that keeps the pitch the same, so the song stays in tune with your instrument while it slows down. Stemline's mixer has a tempo control and a key lock for this.</p>

<h2>Change the key to suit you</h2>
<p>If a song sits too high for your voice or in an awkward key for your instrument, shift the pitch by a few semitones until it feels comfortable. Moving a song down a step or two is a common way for singers to find the right range.</p>

<h2>A simple practice routine</h2>
<ol>
  <li>Listen to the full song once, paying attention to your part.</li>
  <li>Solo your instrument's stem and learn the tricky sections slowly.</li>
  <li>Mute your stem and play along at a slower tempo.</li>
  <li>Bring the tempo up in small steps until you reach the original speed.</li>
  <li>Finish by playing the whole song through with your stem muted.</li>
</ol>

<h2>Tips for better practice tracks</h2>
<ul>
  <li><strong>Expect a little bleed.</strong> You may hear a faint trace of your instrument in the other stems. That is normal and comes from the separation process, as described in <a href="/guides/how-ai-stem-separation-works">how AI stem separation works</a>.</li>
  <li><strong>Use a clean source file.</strong> A WAV or high-quality MP3 gives better results. See <a href="/guides/getting-cleaner-stems">getting cleaner stems</a>.</li>
  <li><strong>Take notes.</strong> Write down the sections that gave you trouble so you can come back to them.</li>
</ul>

<h2>Sheet music and tab</h2>
<p>If you want to see the notes as well as hear them, Stemline101 offers sheet music and tablature as a Premium feature, built from the separated stems.</p>

<p>Ready to practice? <a href="/">Split a song in Stemline101</a>.</p>
""",
    },
]

SLUGS = [g["slug"] for g in MORE_GUIDES]
