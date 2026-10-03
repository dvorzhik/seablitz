/* SeaBlitz — синтезированные звуки (Web Audio API, без внешних файлов). */
(function () {
  "use strict";

  let ctx = null;
  let noiseBuf = null;
  let muted = false;
  try { muted = localStorage.getItem("seablitz_muted") === "1"; } catch (e) {}

  function ac() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === "suspended") { try { ctx.resume(); } catch (e) {} }
    return ctx;
  }

  function getNoise(c) {
    if (noiseBuf) return noiseBuf;
    const len = Math.floor(c.sampleRate * 0.8);
    noiseBuf = c.createBuffer(1, len, c.sampleRate);
    const data = noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
    return noiseBuf;
  }

  function playNoise(c, o) {
    const src = c.createBufferSource();
    src.buffer = getNoise(c);
    const filt = c.createBiquadFilter();
    filt.type = o.type || "lowpass";
    filt.frequency.value = o.freq || 1200;
    filt.Q.value = o.q || 1;
    const g = c.createGain();
    const t = c.currentTime;
    g.gain.setValueAtTime(o.gain || 0.4, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + o.dur);
    src.connect(filt).connect(g).connect(c.destination);
    src.start(t);
    src.stop(t + o.dur);
  }

  function playTone(c, o) {
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = o.type || "sine";
    const t = c.currentTime + (o.delay || 0);
    osc.frequency.setValueAtTime(o.freq, t);
    if (o.freqTo) osc.frequency.exponentialRampToValueAtTime(o.freqTo, t + o.dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(o.gain || 0.3, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + o.dur);
    if (o.lfo) {
      const lfo = c.createOscillator();
      const lfoGain = c.createGain();
      lfo.frequency.value = o.lfo.rate || 5;
      lfoGain.gain.value = o.lfo.depth || 25;
      lfo.connect(lfoGain).connect(osc.frequency);
      lfo.start(t);
      lfo.stop(t + o.dur + 0.03);
    }
    osc.connect(g).connect(c.destination);
    osc.start(t);
    osc.stop(t + o.dur + 0.03);
  }

  const Sound = {
    get muted() { return muted; },
    setMuted(v) {
      muted = !!v;
      try { localStorage.setItem("seablitz_muted", muted ? "1" : "0"); } catch (e) {}
    },
    toggle() { Sound.setMuted(!muted); return muted; },
    unlock() { ac(); },
    play(name) {
      if (muted) return;
      const c = ac();
      if (!c) return;
      switch (name) {
        case "fire":
          playNoise(c, { dur: 0.18, gain: 0.32, freq: 700 });
          playTone(c, { freq: 130, freqTo: 60, dur: 0.22, gain: 0.3 });
          break;
        case "select":
          playTone(c, { freq: 660, dur: 0.06, gain: 0.12, type: "square" });
          break;
        case "miss":
          playNoise(c, { dur: 0.22, gain: 0.22, type: "bandpass", freq: 950, q: 0.8 });
          break;
        case "hit":
          playNoise(c, { dur: 0.3, gain: 0.42, freq: 1500 });
          playTone(c, { freq: 95, freqTo: 45, dur: 0.3, gain: 0.35 });
          break;
        case "sunk":
          playNoise(c, { dur: 0.5, gain: 0.5, freq: 1900 });
          playTone(c, { freq: 75, freqTo: 32, dur: 0.5, gain: 0.45 });
          break;
        case "overtime": {
          // «стадионный гудок» + сирена (в духе старой NHL)
          playTone(c, { freq: 233.08, dur: 1.4, gain: 0.22, type: "sawtooth" });
          playTone(c, { freq: 311.13, dur: 1.4, gain: 0.15, type: "sawtooth" });
          playTone(c, {
            freq: 440, dur: 1.6, gain: 0.12, type: "square",
            lfo: { rate: 5.5, depth: 60 },
          });
          playNoise(c, { dur: 0.5, gain: 0.06, type: "highpass", freq: 900 });
          break;
        }
        case "win": {
          // торжественный восходящий фанфарный пассаж + светлый аккорд-финал
          const melody = [523.25, 659.25, 783.99, 1046.5]; // C5 E5 G5 C6
          melody.forEach((f, i) =>
            playTone(c, { freq: f, dur: 0.22, gain: 0.26, type: "triangle", delay: i * 0.12 })
          );
          [523.25, 659.25, 783.99].forEach((f) =>
            playTone(c, { freq: f, dur: 0.7, gain: 0.16, type: "sine", delay: 0.52 })
          );
          playTone(c, {
            freq: 1046.5, freqTo: 1567.98, dur: 0.5, gain: 0.13,
            type: "triangle", delay: 0.6,
          });
          break;
        }
        case "lose": {
          // мрачное «погружение»: нисходящие тоны + низкий гул воды
          const tones = [392.0, 349.23, 293.66, 233.08]; // G4 F4 D4 A#3
          tones.forEach((f, i) =>
            playTone(c, {
              freq: f, freqTo: f * 0.94, dur: 0.42, gain: 0.24,
              type: "sawtooth", delay: i * 0.16,
            })
          );
          playNoise(c, { dur: 0.9, gain: 0.14, freq: 320 });
          playTone(c, { freq: 116.54, freqTo: 58.27, dur: 1.1, gain: 0.26, delay: 0.1 });
          break;
        }
        case "rematch":
          playTone(c, { freq: 520, dur: 0.12, gain: 0.22, type: "triangle" });
          playTone(c, { freq: 780, dur: 0.16, gain: 0.22, type: "triangle", delay: 0.1 });
          break;
      }
    },
  };

  window.Sound = Sound;
})();
