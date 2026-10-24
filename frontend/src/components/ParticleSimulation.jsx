import React, { useEffect, useRef, useMemo } from "react";

const MAX_DPR = 2;
const FPS_LIMIT = 30;
const MAX_PARTICLES_CANVAS = 1e5;
const DEBOUNCE_MS = 200;
const SLICE_TIME_MS = 8;
const RESET_POS = -10;
const BASE_JITTER = 0;
const JITTER_AXIS_X = 1;
const JITTER_AXIS_Y = 1;
const DEFAULT_ASPECT = "16 / 9";
const HIDE_CURSOR = false;
const IMAGE_SCALE = 0.7;
const DISCARD_OUTSIDE = true;
const JITTER_SPEED = 8;
const INTERACTION_STRENGTH = 7;
const RETURN_SPEED = 0.03;
const BASE_RADIUS = 3;
const POINT_RADIUS = BASE_RADIUS * 2;
const MIN_DENSITY_PARTICLES = 5e4;
const MAX_DENSITY_PARTICLES = 2e6;
const DEFAULT_IMAGE = "/tree.png";

const QUAD_VS = `
precision highp float;
attribute vec2 a_quad;
varying vec2 v_uv;
void main() {
    v_uv = a_quad * 0.5 + 0.5;
    gl_Position = vec4(a_quad, 0.0, 1.0);
}`;

const SIM_FS = `
precision highp float;
uniform sampler2D u_posTex;
uniform sampler2D u_homeTex;
uniform vec2 u_mouse;
uniform float u_imageScale;
uniform float u_brushSize;
uniform float u_strength;
uniform float u_returnSpeed;
uniform float u_damping;
uniform float u_isInit;
varying vec2 v_uv;

void main() {
    vec4 data = texture2D(u_posTex, v_uv);
    vec2 home = texture2D(u_homeTex, v_uv).rg * u_imageScale;
    float energy = data.b;
    float velE = data.a;

    if (u_isInit > 0.5 || energy != energy || velE != velE) {
        energy = 0.0;
        velE = 0.0;
    }

    float forceE = (0.0 - energy) * (u_returnSpeed * 0.5);

    float d = distance(home, u_mouse);
    if (d < u_brushSize * 2.0 && u_mouse.x > -5.0) {
        float influence = smoothstep(u_brushSize * 2.0, 0.0, d);
        influence *= influence;
        forceE += influence * u_strength * 0.1;
    }

    velE += forceE;
    velE *= u_damping;
    energy += velE;
    energy = max(0.0, energy);

    gl_FragColor = vec4(home, energy, velE);
}`;

const FETCH_STATE = `
vec4 fetchState() {
    if (u_static > 0.5) return vec4(a_home.rg * u_imageScale, 0.0, 0.0);
    return texture2D(u_posTex, a_uv);
}
`;

const DRAW_VS = `
precision highp float;
attribute vec4 a_color;
attribute vec2 a_uv;
attribute vec3 a_random;
attribute vec4 a_home;
varying vec4 v_color;
uniform sampler2D u_posTex;
uniform float u_static;
uniform float u_imageScale;
uniform float u_time;
uniform float u_particleSize;
uniform float u_baseJitter;
uniform float u_interJitter;
uniform vec2 u_jitterAxis;
uniform float u_jitterSpeed;
uniform float u_brushSize;
uniform float u_aspect;
${FETCH_STATE}
void main() {
    v_color = a_color;
    vec4 data = fetchState();
    vec2 homeXY = data.rg;
    float energy = clamp(data.b, 0.0, 2.5);

    vec3 rd = vec3(
        sin(a_random.x * 134.11 + a_random.y * 311.23),
        cos(a_random.y * 111.45 + a_random.z * 277.92),
        sin(a_random.z * 188.77 + a_random.x * 399.11)
    );
    vec2 randDir = (rd / max(length(rd), 0.0001)).xy;

    float t = u_time * u_jitterSpeed;
    float orbitSpeed = 0.5 + a_random.y * 1.5;
    float dir = a_random.z > 0.5 ? 1.0 : -1.0;
    vec2 orbit = vec2(
        sin(t * orbitSpeed * dir + a_random.x * 6.28),
        cos(t * orbitSpeed * dir + a_random.y * 6.28)
    );

    float maxStretch = u_brushSize * (u_interJitter * 0.01);
    float stretchPower = (energy / 2.5) * maxStretch;
    vec2 offset = randDir * u_jitterAxis * (u_baseJitter * 0.01 + stretchPower);

    float orbitRadius = u_brushSize * 0.1 * (energy / 2.5);
    offset += orbit * orbitRadius * (0.2 + a_random.x * 1.8);

    vec2 pos = homeXY + offset;
    gl_PointSize = u_particleSize;
    gl_Position = vec4(pos.x / u_aspect, pos.y, 0.0, 1.0);
}`;

const DRAW_FS = `
precision highp float;
varying vec4 v_color;
uniform float u_alphaComp;
void main() {
    if (length(gl_PointCoord - vec2(0.5)) > 0.5) discard;
    float inv = clamp(1.0 - v_color.a, 0.0, 1.0);
    float a = inv <= 0.0 ? 1.0 : 1.0 - pow(inv, u_alphaComp);
    gl_FragColor = vec4(v_color.rgb * a, a);
}`;

const SHADERS = {
  sim: SIM_FS,
  vs: DRAW_VS,
  fs: DRAW_FS,
  simU: ["u_posTex", "u_homeTex", "u_mouse", "u_imageScale", "u_brushSize", "u_strength", "u_returnSpeed", "u_damping", "u_isInit"],
  drawU: ["u_posTex", "u_static", "u_imageScale", "u_time", "u_particleSize", "u_baseJitter", "u_interJitter", "u_jitterAxis", "u_jitterSpeed", "u_brushSize", "u_alphaComp", "u_aspect"]
};

function createShader(gl, type, src, label) {
  let s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    console.warn("ParticleSimulation " + label + ":", gl.getShaderInfoLog(s));
    return null;
  }
  return s;
}

function createProgram(gl, vsSrc, fsSrc, label) {
  let vs = createShader(gl, gl.VERTEX_SHADER, vsSrc, label + ".vert");
  let fs = createShader(gl, gl.FRAGMENT_SHADER, fsSrc, label + ".frag");
  if (!vs || !fs) return null;
  let p = gl.createProgram();
  gl.attachShader(p, vs);
  gl.attachShader(p, fs);
  gl.linkProgram(p);
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    console.warn("ParticleSimulation " + label + " link:", gl.getProgramInfoLog(p));
    return null;
  }
  return p;
}

function compilePass(gl, vsSrc, fsSrc, uList, label) {
  let p = createProgram(gl, vsSrc, fsSrc, label);
  if (!p) return null;
  let u = {}, nulls = [];
  for (let i = 0; i < uList.length; i++) {
    let loc = gl.getUniformLocation(p, uList[i]);
    if (loc === null) nulls.push(uList[i]);
    u[uList[i]] = loc;
  }
  return { prog: p, u, nulls };
}

function getContext(canvas) {
  let opts = { alpha: true, antialias: false, premultipliedAlpha: true, depth: false, stencil: false, powerPreference: "high-performance" };
  let gl = canvas.getContext("webgl2", opts);
  let isWebgl2 = !!gl;
  let floatRT = false;
  if (gl) {
    floatRT = !!gl.getExtension("EXT_color_buffer_float");
  } else {
    gl = canvas.getContext("webgl", opts) || canvas.getContext("experimental-webgl", opts);
    if (!gl) return null;
    floatRT = !!(gl.getExtension("OES_texture_float") && gl.getExtension("WEBGL_color_buffer_float"));
  }
  if (gl.getParameter(gl.MAX_VERTEX_TEXTURE_IMAGE_UNITS) < 2) {
    floatRT = false;
  }
  return { gl, webgl2: isWebgl2, floatRT };
}

function getFormat(gl, webgl2) {
  return { internal: webgl2 ? gl.RGBA32F : gl.RGBA, format: gl.RGBA, type: gl.FLOAT };
}

function createTexture(gl, fmt, size, data) {
  let t = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texImage2D(gl.TEXTURE_2D, 0, fmt.internal, size, size, 0, fmt.format, fmt.type, data || null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.bindTexture(gl.TEXTURE_2D, null);
  return t;
}

function createFBO(gl, fmt, size) {
  let tex = createTexture(gl, fmt, size, null);
  let fbo = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  let ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return { tex, fbo, ok };
}

const MIN_ALPHA_THRESHOLD = 8;
function createParticleData(rgba, w, h, aspect, targetCount) {
  let step = Math.max(1, Math.sqrt(w * h / Math.max(1, targetCount)));
  let approxCols = Math.ceil(w / step) + 2;
  let approxRows = Math.ceil(h / step) + 2;
  let texSize = Math.max(2, Math.ceil(Math.sqrt(approxCols * approxRows)));
  let cap = texSize * texSize;
  let home = new Float32Array(cap * 4);
  let color = new Float32Array(cap * 4);
  let uv = new Float32Array(cap * 2);
  let rand = new Float32Array(cap * 3);
  let count = 0, currRow = 0, done = false;

  return {
    texSize,
    capacity: cap,
    get count() { return count; },
    get finished() { return done; },
    step(maxMs) {
      let start = (typeof performance !== "undefined" ? performance : Date).now();
      while (currRow < h && count < cap) {
        let g = Math.floor(currRow);
        for (let s = 0; s < w && count < cap; s += step) {
          let D = Math.floor(s);
          let idx = (g * w + D) * 4;
          let aVal = rgba[idx + 3];
          if (aVal < MIN_ALPHA_THRESHOLD) continue;
          let rVal = rgba[idx] / 255;
          let gVal = rgba[idx + 1] / 255;
          let bVal = rgba[idx + 2] / 255;
          let alpha = aVal / 255;

          let a4 = count * 4;
          let a3 = count * 3;
          let a2 = count * 2;

          home[a4] = (s / w * 2 - 1) * aspect;
          home[a4 + 1] = (1 - currRow / h) * 2 - 1;
          home[a4 + 2] = 0;
          home[a4 + 3] = 0;

          color[a4] = rVal;
          color[a4 + 1] = gVal;
          color[a4 + 2] = bVal;
          color[a4 + 3] = alpha;

          rand[a3] = Math.random();
          rand[a3 + 1] = Math.random();
          rand[a3 + 2] = Math.random();

          uv[a2] = (count % texSize + 0.5) / texSize;
          uv[a2 + 1] = (Math.floor(count / texSize) + 0.5) / texSize;
          count++;
        }
        currRow += step;
        let now = (typeof performance !== "undefined" ? performance : Date).now();
        if (maxMs > 0 && now - start >= maxMs) break;
      }
      if (currRow >= h || count >= cap) done = true;
      return done;
    },
    result() {
      return { home, color, uv, rand, count, texSize, gridStep: step, srcH: h };
    }
  };
}

function calculateAlphaComp(gridStep, srcH, scale, canvasH, pSize) {
  let ratio = gridStep * srcH * scale / Math.max(1, canvasH);
  if (!(ratio > 0) || !(pSize > 0)) return 1;
  return Math.max(1, (Math.PI / 4) * pSize * pSize / (ratio * ratio));
}

const DEFAULT_HOVER = { reach: 30, lift: 51, damping: 58 };

export default function ParticleSimulation({
  portraitImage = DEFAULT_IMAGE,
  background = "transparent",
  density = 50,
  dotSize = 30,
  hover = DEFAULT_HOVER,
  style = {}
}) {
  const { reach, lift, damping } = { ...DEFAULT_HOVER, ...(hover || {}) };
  const imgSrc = (typeof portraitImage === "string" ? portraitImage : portraitImage?.src) || DEFAULT_IMAGE;

  const targetParticles = useMemo(() => {
    let pct = Math.max(0, Math.min(100, density)) / 100;
    let base = Math.round(MIN_DENSITY_PARTICLES + pct * (MAX_DENSITY_PARTICLES - MIN_DENSITY_PARTICLES));
    let dpr = (typeof window !== "undefined" && window.devicePixelRatio) || 1;
    if (dpr > 2) base = Math.floor(base * 0.75);
    return base;
  }, [density]);

  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const paramsRef = useRef({});

  paramsRef.current = {
    brush: reach / 100,
    strength: INTERACTION_STRENGTH,
    returnSpeed: RETURN_SPEED,
    damping: Math.max(1, Math.min(100, damping)) / 100,
    jitterSpeed: JITTER_SPEED,
    baseJitter: BASE_JITTER,
    interJitter: lift,
    jitterX: JITTER_AXIS_X,
    jitterY: JITTER_AXIS_Y,
    particleSize: (Math.max(0, Math.min(100, dotSize)) / 100) * POINT_RADIUS,
    imageScale: IMAGE_SCALE,
    density: targetParticles,
    isCanvas: false
  };

  const imgDataRef = useRef(null);
  const reloadKeyRef = useRef(0);

  // Load Image and read pixel buffer
  useEffect(() => {
    let cancelled = false;
    let img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (cancelled) return;
      let w = img.naturalWidth || img.width;
      let h = img.naturalHeight || img.height;
      if (!w || !h) return;

      let offCanvas = document.createElement("canvas");
      offCanvas.width = w;
      offCanvas.height = h;
      let ctx = offCanvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;
      ctx.drawImage(img, 0, 0, w, h);

      let data;
      try {
        data = ctx.getImageData(0, 0, w, h).data;
      } catch (e) {
        console.warn("ParticleSimulation: image tainted or blocked", imgSrc);
        return;
      }
      imgDataRef.current = { data, w, h, aspect: w / h };
      reloadKeyRef.current++;
    };
    img.onerror = () => console.warn("ParticleSimulation: image failed to load", imgSrc);
    img.src = imgSrc;
    return () => { cancelled = true; };
  }, [imgSrc]);

  const mouseRef = useRef({ tx: RESET_POS, ty: RESET_POS, sx: RESET_POS, sy: RESET_POS });

  // WebGL Render Loop & Event Listeners
  useEffect(() => {
    let container = containerRef.current;
    let canvas = canvasRef.current;
    if (!container || !canvas) return;

    let ctxInfo = getContext(canvas);
    if (!ctxInfo) {
      console.warn("ParticleSimulation: WebGL not supported");
      return;
    }

    let { gl, webgl2, floatRT } = ctxInfo;
    let fmt = getFormat(gl, webgl2);
    let simPass = floatRT ? compilePass(gl, QUAD_VS, SHADERS.sim, SHADERS.simU, "sim") : { prog: null, u: {}, nulls: [] };
    let drawPass = compilePass(gl, SHADERS.vs, SHADERS.fs, SHADERS.drawU, "draw");
    if (!drawPass) return;

    let attribs = {
      sim: simPass,
      draw: drawPass,
      aColor: gl.getAttribLocation(drawPass.prog, "a_color"),
      aUv: gl.getAttribLocation(drawPass.prog, "a_uv"),
      aRandom: gl.getAttribLocation(drawPass.prog, "a_random"),
      aHome: gl.getAttribLocation(drawPass.prog, "a_home"),
      aQuad: simPass.prog ? gl.getAttribLocation(simPass.prog, "a_quad") : -1
    };

    let quadBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);

    let dummyTex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, dummyTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([0, 0, 0, 0]));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.bindTexture(gl.TEXTURE_2D, null);

    let colBuf = gl.createBuffer();
    let uvBuf = gl.createBuffer();
    let randBuf = gl.createBuffer();
    let homeBuf = gl.createBuffer();

    let lastDensityKey = "", nextKey = "", changeTime = 0;
    let genTask = null, count = 0, texSize = 0;
    let homeTex = null, fboA = null, fboB = null;
    let ready = false, initialized = false, gridStep = 0, srcH = 0;

    let cleanupBuffers = () => {
      if (homeTex) gl.deleteTexture(homeTex);
      if (fboA) { gl.deleteTexture(fboA.tex); gl.deleteFramebuffer(fboA.fbo); }
      if (fboB) { gl.deleteTexture(fboB.tex); gl.deleteFramebuffer(fboB.fbo); }
      homeTex = null; fboA = null; fboB = null; ready = false;
    };

    let setParticleData = (data) => {
      cleanupBuffers();
      count = data.count;
      texSize = data.texSize;
      if (!count) return;

      homeTex = createTexture(gl, fmt, texSize, data.home);
      gl.bindBuffer(gl.ARRAY_BUFFER, colBuf);
      gl.bufferData(gl.ARRAY_BUFFER, data.color.subarray(0, count * 4), gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, uvBuf);
      gl.bufferData(gl.ARRAY_BUFFER, data.uv.subarray(0, count * 2), gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, randBuf);
      gl.bufferData(gl.ARRAY_BUFFER, data.rand.subarray(0, count * 3), gl.STATIC_DRAW);

      if (!floatRT) {
        gl.bindBuffer(gl.ARRAY_BUFFER, homeBuf);
        gl.bufferData(gl.ARRAY_BUFFER, data.home.subarray(0, count * 4), gl.STATIC_DRAW);
      } else {
        fboA = createFBO(gl, fmt, texSize);
        fboB = createFBO(gl, fmt, texSize);
        if (!fboA.ok || !fboB.ok) {
          console.warn("ParticleSimulation: FBO incomplete");
          cleanupBuffers();
          return;
        }
      }
      gridStep = data.gridStep;
      srcH = data.srcH;
      ready = true;
      initialized = false;
    };

    let setSimUniforms = (pass, p, initFlag, sourceTex) => {
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, sourceTex);
      gl.uniform1i(pass.u.u_posTex, 0);

      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, homeTex);
      gl.uniform1i(pass.u.u_homeTex, 1);

      gl.uniform2f(pass.u.u_mouse, mouseRef.current.sx, mouseRef.current.sy);
      gl.uniform1f(pass.u.u_imageScale, p.imageScale);
      gl.uniform1f(pass.u.u_brushSize, p.brush);
      gl.uniform1f(pass.u.u_strength, p.strength);
      gl.uniform1f(pass.u.u_returnSpeed, p.returnSpeed);
      gl.uniform1f(pass.u.u_damping, p.damping);
      gl.uniform1f(pass.u.u_isInit, initFlag);
    };

    let runSimPass = (pass, aLoc, p, initFlag, targetFbo, sourceTex) => {
      gl.useProgram(pass.prog);
      gl.bindFramebuffer(gl.FRAMEBUFFER, targetFbo.fbo);
      gl.viewport(0, 0, texSize, texSize);
      gl.disable(gl.BLEND);
      setSimUniforms(pass, p, initFlag, sourceTex);

      gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
      gl.enableVertexAttribArray(aLoc);
      gl.vertexAttribPointer(aLoc, 2, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    };

    let initSimulation = (p) => {
      if (!floatRT || !ready) return;
      runSimPass(attribs.sim, attribs.aQuad, p, 1, fboA, homeTex);
      runSimPass(attribs.sim, attribs.aQuad, p, 1, fboB, homeTex);
    };

    let canvasW = 0, canvasH = 0, aspect = 16 / 9;
    let resize = () => {
      let dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      canvasW = canvas.clientWidth || container.clientWidth || 0;
      canvasH = canvas.clientHeight || container.clientHeight || 0;
      let targetW = Math.max(1, Math.round(canvasW * dpr));
      let targetH = Math.max(1, Math.round(canvasH * dpr));
      if (canvas.width !== targetW || canvas.height !== targetH) {
        canvas.width = targetW;
        canvas.height = targetH;
      }
      aspect = targetW / targetH;
      cachedRect = null;
    };

    let cachedRect = null;
    let resetMouse = () => {
      let m = mouseRef.current;
      m.tx = RESET_POS; m.ty = RESET_POS; m.sx = RESET_POS; m.sy = RESET_POS;
    };

    let updateMouse = (clientX, clientY) => {
      if (!cachedRect) cachedRect = container.getBoundingClientRect();
      let r = cachedRect;
      if (!r.width || !r.height) return;
      let padX = r.width * 0.01, padY = r.height * 0.01;
      if (clientX <= r.left + padX || clientX >= r.right - padX || clientY <= r.top + padY || clientY >= r.bottom - padY) {
        resetMouse();
        return;
      }
      let normX = (clientX - r.left) / r.width * 2 - 1;
      let normY = -((clientY - r.top) / r.height * 2 - 1);
      mouseRef.current.tx = normX * (r.width / r.height);
      mouseRef.current.ty = normY;
    };

    let onMouseMove = (e) => {
      if (DISCARD_OUTSIDE && e.target !== container && !container.contains(e.target)) {
        resetMouse();
        return;
      }
      updateMouse(e.clientX, e.clientY);
    };

    let onTouchMove = (e) => {
      if (e.touches[0]) updateMouse(e.touches[0].clientX, e.touches[0].clientY);
    };

    window.addEventListener("mousemove", onMouseMove, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("touchend", resetMouse, { passive: true });
    window.addEventListener("scroll", () => { cachedRect = null; }, { passive: true });
    container.addEventListener("mouseleave", resetMouse);

    resize();
    let ro = new ResizeObserver(resize);
    ro.observe(canvas);

    gl.disable(gl.DEPTH_TEST);
    let animId = 0, lastFrameTime = -1e9, elapsed = 0;
    let prevTime = performance.now();

    let render = (now) => {
      animId = requestAnimationFrame(render);
      let p = paramsRef.current;
      let delta = Math.min((now - prevTime) / 1000, 0.05);
      prevTime = now;
      elapsed += delta;

      // Handle async particle generation
      let curImg = imgDataRef.current;
      let curKey = curImg ? reloadKeyRef.current + "|" + Math.round(p.density) : "";
      if (curKey && curKey !== lastDensityKey && !genTask) {
        if (curKey !== nextKey) {
          nextKey = curKey;
          changeTime = now;
        } else if (now - changeTime >= DEBOUNCE_MS) {
          genTask = createParticleData(curImg.data, curImg.w, curImg.h, curImg.aspect, p.density);
        }
      }

      if (genTask && genTask.step(SLICE_TIME_MS)) {
        setParticleData(genTask.result());
        lastDensityKey = nextKey;
        genTask = null;
      }

      if (!ready || !count) return;

      // Smooth mouse spring interpolation
      let m = mouseRef.current;
      if (m.tx < -5) {
        m.sx += (m.tx - m.sx) * 0.08;
        m.sy += (m.ty - m.sy) * 0.08;
      } else if (m.sx < -5) {
        m.sx = m.tx; m.sy = m.ty;
      } else {
        m.sx += (m.tx - m.sx) * 0.15;
        m.sy += (m.ty - m.sy) * 0.15;
      }

      if (!initialized) {
        initSimulation(p);
        initialized = true;
      }

      // Physics ping-pong simulation
      if (floatRT) {
        runSimPass(attribs.sim, attribs.aQuad, p, 0, fboB, fboA.tex);
        let temp = fboA;
        fboA = fboB;
        fboB = temp;
      }

      // Draw point particles
      gl.useProgram(attribs.draw.prog);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, floatRT ? fboA.tex : dummyTex);
      gl.uniform1i(attribs.draw.u.u_posTex, 0);
      gl.uniform1f(attribs.draw.u.u_static, floatRT ? 0 : 1);
      gl.uniform1f(attribs.draw.u.u_imageScale, p.imageScale);
      gl.uniform1f(attribs.draw.u.u_time, elapsed);
      gl.uniform1f(attribs.draw.u.u_aspect, aspect);
      gl.uniform1f(attribs.draw.u.u_baseJitter, p.baseJitter);
      gl.uniform1f(attribs.draw.u.u_interJitter, p.interJitter);
      gl.uniform2f(attribs.draw.u.u_jitterAxis, p.jitterX, p.jitterY);
      gl.uniform1f(attribs.draw.u.u_jitterSpeed, p.jitterSpeed);
      gl.uniform1f(attribs.draw.u.u_brushSize, p.brush);

      let dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      let scaleNorm = Math.max(1, canvasW / 1200);
      let renderSize = p.particleSize * dpr * scaleNorm;
      gl.uniform1f(attribs.draw.u.u_particleSize, renderSize);
      gl.uniform1f(attribs.draw.u.u_alphaComp, 1 / calculateAlphaComp(gridStep, srcH, p.imageScale, canvas.height, renderSize));

      gl.bindBuffer(gl.ARRAY_BUFFER, colBuf);
      gl.enableVertexAttribArray(attribs.aColor);
      gl.vertexAttribPointer(attribs.aColor, 4, gl.FLOAT, false, 0, 0);

      gl.bindBuffer(gl.ARRAY_BUFFER, uvBuf);
      gl.enableVertexAttribArray(attribs.aUv);
      gl.vertexAttribPointer(attribs.aUv, 2, gl.FLOAT, false, 0, 0);

      gl.bindBuffer(gl.ARRAY_BUFFER, randBuf);
      gl.enableVertexAttribArray(attribs.aRandom);
      gl.vertexAttribPointer(attribs.aRandom, 3, gl.FLOAT, false, 0, 0);

      if (attribs.aHome >= 0) {
        if (floatRT) {
          gl.disableVertexAttribArray(attribs.aHome);
          gl.vertexAttrib4f(attribs.aHome, 0, 0, 0, 0);
        } else {
          gl.bindBuffer(gl.ARRAY_BUFFER, homeBuf);
          gl.enableVertexAttribArray(attribs.aHome);
          gl.vertexAttribPointer(attribs.aHome, 4, gl.FLOAT, false, 0, 0);
        }
      }

      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      if (renderSize > 0) {
        gl.drawArrays(gl.POINTS, 0, count);
      }
    };

    animId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animId);
      ro.disconnect();
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", resetMouse);
      container.removeEventListener("mouseleave", resetMouse);
      cleanupBuffers();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: style.height || "100%",
        minWidth: 0,
        minHeight: 0,
        position: "relative",
        overflow: "hidden",
        touchAction: "none",
        backgroundColor: background,
        cursor: HIDE_CURSOR ? "none" : "auto",
        ...style
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          display: "block",
          pointerEvents: "none"
        }}
      />
    </div>
  );
}
