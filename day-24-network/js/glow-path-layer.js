// GlowPathLayer: a deck.gl PathLayer whose paths grow along their length.
//
// Each path carries a time (seconds of travel) at every vertex. The vertex
// shader interpolates that time along each segment, and the fragment shader
// discards everything the clock has not reached yet, so a street fills in
// from the end you reach first to the other.
//
// Colour is the Velographs "polar" ramp: three stops after Viridis
// (#8700A7, #25A39D, #FDE725) smoothed with d3.interpolateRgbBasis, with
// travel time 0..maxTime mapped to 0..1.
// Across the line's width there is a bright core and a soft Gaussian halo;
// line reached in the last few seconds runs whiter and glows harder.

const VS_DECL = /* glsl */ `
  attribute float instanceTimestamps;
  attribute float instanceNextTimestamps;
  varying float vTime;
`;

// vPathPosition.y is the distance along the segment, vPathLength its length.
const VS_MAIN_END = /* glsl */ `
  vTime = mix(instanceTimestamps, instanceNextTimestamps,
              clamp(vPathPosition.y / max(vPathLength, 1e-6), 0.0, 1.0));
`;

const FS_DECL = /* glsl */ `
  uniform float uTime;   // the clock, seconds of travel
  uniform float uMax;    // travel time that maps to the end of the ramp
  uniform float uHalo;   // halo strength
  uniform float uSpark;  // seconds a freshly reached line stays hot
  varying float vTime;

  // Viridis-style ramp from three stops, smoothed the way Velographs does it:
  // d3.interpolateRgbBasis(["#8700A7", "#25A39D", "#FDE725"]), a uniform
  // cubic B-spline through the stops with the ends mirrored as d3 does.
  vec3 polar(float t) {
    vec3 c0 = vec3(135.0, 0.0, 167.0) / 255.0;
    vec3 c1 = vec3(37.0, 163.0, 157.0) / 255.0;
    vec3 c2 = vec3(253.0, 231.0, 37.0) / 255.0;
    float i = t >= 1.0 ? 1.0 : floor(t * 2.0);   // which of the 2 spans
    vec3 v0 = i < 0.5 ? 2.0 * c0 - c1 : c0;
    vec3 v1 = i < 0.5 ? c0 : c1;
    vec3 v2 = i < 0.5 ? c1 : c2;
    vec3 v3 = i < 0.5 ? c2 : 2.0 * c2 - c1;
    float u = (t - i / 2.0) * 2.0, u2 = u * u, u3 = u2 * u;
    vec3 c = ((1.0 - 3.0 * u + 3.0 * u2 - u3) * v0
            + (4.0 - 6.0 * u2 + 3.0 * u3) * v1
            + (1.0 + 3.0 * u + 3.0 * u2 - 3.0 * u3) * v2
            + u3 * v3) / 6.0;
    return clamp(c, 0.0, 1.0);
  }
`;

const FS_MAIN_START = /* glsl */ `
  if (vTime > uTime) discard;   // not reached yet
`;

// geometry.uv.x runs -1..1 across the line's width (0 = centre).
const FS_FILTER_COLOR = /* glsl */ `
  vec3 ramp = polar(clamp(vTime / uMax, 0.0, 1.0));
  float d = abs(geometry.uv.x);
  float core = 1.0 - smoothstep(0.10, 0.26, d);
  float halo = exp(-d * d * 4.0);
  float spark = exp(-max(uTime - vTime, 0.0) / uSpark);   // 1 when just reached
  vec3 rgb = mix(ramp, vec3(1.0), core * 0.85 * spark);
  float alpha = max(core * (0.85 + 0.15 * spark), halo * uHalo * (1.0 + 2.0 * spark));
  color = vec4(rgb, alpha);
`;

export class GlowPathLayer extends deck.PathLayer {
  getShaders() {
    const shaders = super.getShaders();
    shaders.inject = {
      "vs:#decl": VS_DECL,
      "vs:#main-end": VS_MAIN_END,
      "fs:#decl": FS_DECL,
      "fs:#main-start": FS_MAIN_START,
      "fs:DECKGL_FILTER_COLOR": FS_FILTER_COLOR,
    };
    return shaders;
  }

  initializeState(context) {
    super.initializeState(context);
    // One time per vertex; each segment reads its start and end time.
    this.getAttributeManager().addInstanced({
      timestamps: {
        size: 1,
        accessor: "getTimestamps",
        shaderAttributes: {
          instanceTimestamps: { vertexOffset: 0 },
          instanceNextTimestamps: { vertexOffset: 1 },
        },
      },
    });
  }

  draw(params) {
    const { time, maxTime, halo, spark } = this.props;
    params.uniforms = { ...params.uniforms, uTime: time, uMax: maxTime, uHalo: halo, uSpark: spark };
    super.draw(params);
  }
}

GlowPathLayer.layerName = "GlowPathLayer";
GlowPathLayer.defaultProps = {
  getTimestamps: { type: "accessor", value: d => d.ts },
  time: 0,
  maxTime: 2400,
  halo: 0.45,
  spark: 45,
};

// GL blending presets. OVER is ordinary alpha blending, so colours stay true
// where streets are dense; ADDITIVE adds light (rgb += src * alpha) and blooms.
const GL = { SRC_ALPHA: 770, ONE: 1, ONE_MINUS_SRC_ALPHA: 771, FUNC_ADD: 32774 };
export const BLEND = {
  OVER: { depthTest: false, blend: true, blendEquation: GL.FUNC_ADD,
          blendFunc: [GL.SRC_ALPHA, GL.ONE_MINUS_SRC_ALPHA, GL.ONE, GL.ONE_MINUS_SRC_ALPHA] },
  ADDITIVE: { depthTest: false, blend: true, blendEquation: GL.FUNC_ADD,
              blendFunc: [GL.SRC_ALPHA, GL.ONE, GL.ONE, GL.ONE_MINUS_SRC_ALPHA] },
};
