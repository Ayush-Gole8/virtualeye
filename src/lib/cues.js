/**
 * cues.js — non-speech hazard cues (stereo earcon + vibration).
 *
 * Additive to speech, never a replacement: a cue tells the user *something is
 * closing and roughly where*; the spoken sentence explains what it is.
 *
 * Severity is collapsed onto one shared rank so structural alerts and tracked
 * detections can be compared directly:
 *
 *     3 critical  three 880 Hz beeps   [120,60,120,60,120]
 *     2 high      two   660 Hz beeps   [100,50,100]
 *     1 medium    one   440 Hz beep    [80]
 *
 * Anything below medium ('low' / 'none') produces no cue at all — the whole
 * point of the priority engine is to not fill the user's ears with noise.
 *
 * This module has NO side effects at import time. The AudioContext is owned by
 * the caller, which must create it inside a user gesture.
 */

// Shared severity scale.
export const RANK_CRITICAL = 3;
export const RANK_HIGH = 2;
export const RANK_MEDIUM = 1;

// alerts[] carry 'critical' | 'high' only.
const ALERT_RANK = {
  critical: RANK_CRITICAL,
  high: RANK_HIGH,
};

// detections[] carry 'none' | 'low' | 'medium' | 'high' | 'critical'.
// 'low' and 'none' are deliberately absent — they map to no cue.
const DETECTION_RANK = {
  critical: RANK_CRITICAL,
  high: RANK_HIGH,
  medium: RANK_MEDIUM,
};

const EARCON = {
  [RANK_CRITICAL]: { freq: 880, beeps: 3 },
  [RANK_HIGH]: { freq: 660, beeps: 2 },
  [RANK_MEDIUM]: { freq: 440, beeps: 1 },
};

const VIBRATION = {
  [RANK_CRITICAL]: [120, 60, 120, 60, 120],
  [RANK_HIGH]: [100, 50, 100],
  [RANK_MEDIUM]: [80],
};

const SIDE_PAN = {
  left: -0.7,
  center: 0,
  right: 0.7,
};

// Frame width the frontend captures at (see captureFrame in VisionPage).
export const FRAME_WIDTH = 480;

const BEEP_MS = 90;        // inside the 70-110 ms window
const BEEP_GAP_MS = 70;    // silence between beeps of one earcon
const ATTACK_S = 0.008;    // short ramps so beeps don't click
const RELEASE_S = 0.02;
const PEAK_GAIN = 0.22;    // stays under speech so it never masks it

// Minimum time between two cues that aren't an escalation.
export const MIN_REFIRE_MS = 1500;

const clampPan = (value) => Math.max(-1, Math.min(1, value));

/**
 * Horizontal position of a detection as a pan value in [-1, 1].
 * Prefers cx (continuous) and falls back to the coarse side label.
 */
const panForDetection = (det, frameWidth) => {
  const cx = Number(det?.cx);
  if (Number.isFinite(cx) && frameWidth > 0) {
    return clampPan((cx / frameWidth) * 2 - 1);
  }
  const sidePan = SIDE_PAN[det?.side];
  return typeof sidePan === 'number' ? sidePan : 0;
};

/**
 * Pick the single most severe cue in one /analyze_frame response.
 *
 * @returns {{source: 'alert'|'detection', rank: number, pan: number, label: string}|null}
 *          null when nothing reaches 'medium'.
 */
export function selectCue(data, frameWidth = FRAME_WIDTH) {
  let best = null;

  const consider = (candidate) => {
    // Ties go to the alert-sourced cue: structural hazards (drop-off, overhead,
    // staircase) are the ones a cane cannot find in time.
    if (
      !best
      || candidate.rank > best.rank
      || (candidate.rank === best.rank && candidate.source === 'alert' && best.source !== 'alert')
    ) {
      best = candidate;
    }
  };

  for (const alert of data?.alerts || []) {
    const rank = ALERT_RANK[alert?.priority];
    if (!rank) continue;
    consider({
      source: 'alert',
      rank,
      pan: 0, // structural hazards are always "ahead"
      label: alert?.type || 'hazard',
    });
  }

  for (const det of data?.detections || []) {
    const rank = DETECTION_RANK[det?.urgency];
    if (!rank) continue;
    consider({
      source: 'detection',
      rank,
      pan: panForDetection(det, frameWidth),
      label: det?.class || 'object',
    });
  }

  return best;
}

/** Stable identity for a cue, used to suppress repeats of an ongoing condition. */
export function cueSignature(cue) {
  return cue ? `${cue.source}:${cue.rank}` : null;
}

/**
 * De-duplication. The loop re-sends the same alerts/urgency every ~2500 ms while
 * a condition persists, so an ungated cue would beep forever.
 *
 * Fires when the cue changes, or when it returns after clearing (the caller
 * blanks prev.sig on an empty frame). An escalation bypasses the re-fire gap —
 * a jump to critical is exactly the cue the user cannot afford to miss.
 *
 * @param prev {{sig: string|null, rank: number, ts: number}}
 */
export function shouldFireCue(prev, cue, now, minGapMs = MIN_REFIRE_MS) {
  if (!cue) return false;
  if (prev.sig === cueSignature(cue)) return false; // same condition, still ongoing
  if (cue.rank > prev.rank) return true;            // escalation: never suppress
  return now - prev.ts >= minGapMs;
}

/** StereoPannerNode where available; a transparent GainNode where it isn't. */
const createPanNode = (audioCtx, pan) => {
  if (typeof audioCtx.createStereoPanner === 'function') {
    const panner = audioCtx.createStereoPanner();
    panner.pan.value = clampPan(pan);
    return panner;
  }
  return audioCtx.createGain(); // no panning available — cue still audible
};

/**
 * Schedule the earcon. Returns immediately; the beeps are rendered on the audio
 * thread, so this never delays the caller (speech included).
 */
export function playEarcon(audioCtx, cue) {
  if (!audioCtx || audioCtx.state === 'closed' || !cue) return;

  const spec = EARCON[cue.rank];
  if (!spec) return;

  const start = audioCtx.currentTime + 0.01;

  for (let i = 0; i < spec.beeps; i += 1) {
    const t0 = start + i * ((BEEP_MS + BEEP_GAP_MS) / 1000);
    const t1 = t0 + BEEP_MS / 1000;

    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    const panNode = createPanNode(audioCtx, cue.pan);

    osc.type = 'sine';
    osc.frequency.setValueAtTime(spec.freq, t0);

    gain.gain.setValueAtTime(0, t0);
    gain.gain.linearRampToValueAtTime(PEAK_GAIN, t0 + ATTACK_S);
    gain.gain.setValueAtTime(PEAK_GAIN, t1 - RELEASE_S);
    gain.gain.linearRampToValueAtTime(0, t1);

    osc.connect(gain);
    gain.connect(panNode);
    panNode.connect(audioCtx.destination);

    osc.onended = () => {
      try {
        osc.disconnect();
        gain.disconnect();
        panNode.disconnect();
      } catch {
        // context already torn down
      }
    };

    osc.start(t0);
    osc.stop(t1 + 0.01);
  }
}

/** Vibration pattern for a rank. No-ops where the API is absent (most desktops). */
export function vibrateFor(rank) {
  const pattern = VIBRATION[rank];
  if (!pattern) return false;
  if (typeof navigator === 'undefined' || typeof navigator.vibrate !== 'function') return false;
  try {
    return navigator.vibrate(pattern);
  } catch {
    return false; // some browsers throw when the page is backgrounded
  }
}
