// The sounds of the board, synthesized in the browser. There are no audio files:
// each sound is a few milliseconds of filtered noise (the knock of a piece on
// wood) and, for check and game end, a soft tone on top.
//
// Every number that shapes a sound is in VOICES, so the sounds can be retuned
// (or replaced by recorded files) without touching how they are triggered.

import type { SoundName } from "../state/reducer";

export type Sound = SoundName | "low-time";

interface Knock {
  at: number; // seconds after the sound starts
  frequency: number; // centre of the band-pass filter, Hz
  sharpness: number; // filter Q
  length: number; // seconds
  level: number; // 0 to 1
}

interface Tone {
  at: number;
  frequency: number;
  length: number;
  level: number;
}

const VOICES: Record<Sound, { knocks: Knock[]; tones: Tone[] }> = {
  move: { knocks: [{ at: 0, frequency: 820, sharpness: 1.4, length: 0.07, level: 0.55 }], tones: [] },
  capture: {
    knocks: [
      { at: 0, frequency: 1250, sharpness: 1.1, length: 0.05, level: 0.5 },
      { at: 0.045, frequency: 620, sharpness: 1.6, length: 0.09, level: 0.6 },
    ],
    tones: [],
  },
  check: {
    knocks: [{ at: 0, frequency: 820, sharpness: 1.4, length: 0.07, level: 0.5 }],
    tones: [{ at: 0.02, frequency: 880, length: 0.22, level: 0.09 }],
  },
  end: {
    knocks: [{ at: 0, frequency: 620, sharpness: 1.6, length: 0.09, level: 0.5 }],
    tones: [
      { at: 0.03, frequency: 523.25, length: 0.5, level: 0.08 },
      { at: 0.2, frequency: 392, length: 0.7, level: 0.08 },
    ],
  },
  "low-time": { knocks: [], tones: [{ at: 0, frequency: 660, length: 0.12, level: 0.07 }] },
};

const MASTER_LEVEL = 0.8;
const ATTACK = 0.004; // seconds: long enough to avoid a click

let context: AudioContext | null = null;
let noise: AudioBuffer | null = null;

function ensureContext(): AudioContext | null {
  if (typeof AudioContext === "undefined") return null;
  context ??= new AudioContext();
  if (context.state === "suspended") void context.resume();
  return context;
}

function noiseBuffer(audio: AudioContext): AudioBuffer {
  if (noise === null) {
    noise = audio.createBuffer(1, audio.sampleRate / 4, audio.sampleRate);
    const samples = noise.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) samples[index] = Math.random() * 2 - 1;
  }
  return noise;
}

function envelope(audio: AudioContext, start: number, length: number, level: number): GainNode {
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(level * MASTER_LEVEL, start + ATTACK);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
  gain.connect(audio.destination);
  return gain;
}

/**
 * Browsers only allow sound after the reader has interacted with the page.
 * Call this from the first click or key press.
 */
export function unlockSound(): void {
  ensureContext();
}

export function playSound(name: Sound): void {
  const audio = ensureContext();
  if (audio === null || audio.state !== "running") return;
  const now = audio.currentTime;
  const voice = VOICES[name];

  for (const knock of voice.knocks) {
    const source = audio.createBufferSource();
    source.buffer = noiseBuffer(audio);
    const filter = audio.createBiquadFilter();
    filter.type = "bandpass";
    filter.frequency.value = knock.frequency;
    filter.Q.value = knock.sharpness;
    source.connect(filter).connect(envelope(audio, now + knock.at, knock.length, knock.level));
    source.start(now + knock.at);
    source.stop(now + knock.at + knock.length);
  }

  for (const tone of voice.tones) {
    const oscillator = audio.createOscillator();
    oscillator.type = "sine";
    oscillator.frequency.value = tone.frequency;
    oscillator.connect(envelope(audio, now + tone.at, tone.length, tone.level));
    oscillator.start(now + tone.at);
    oscillator.stop(now + tone.at + tone.length);
  }
}
