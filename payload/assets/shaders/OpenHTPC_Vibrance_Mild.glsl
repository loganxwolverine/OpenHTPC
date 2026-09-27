// SPDX-License-Identifier: Apache-2.0
// OPENHTPC mild adaptive vibrance for SDR/DVD material.

//!DESC OPENHTPC Vibrance Mild
//!HOOK MAIN
//!BIND HOOKED

vec4 hook() {
    vec4 src = HOOKED_tex(HOOKED_pos);
    vec3 rgb = src.rgb;
    float y = dot(rgb, vec3(0.2126, 0.7152, 0.0722));
    float hi = max(rgb.r, max(rgb.g, rgb.b));
    float lo = min(rgb.r, min(rgb.g, rgb.b));
    float chroma = hi - lo;

    float low_sat_weight = 1.0 - smoothstep(0.08, 0.42, chroma);

    float rg = rgb.r - rgb.g;
    float gb = rgb.g - rgb.b;
    float skin_like =
        smoothstep(0.015, 0.12, rg) *
        smoothstep(-0.03, 0.10, gb) *
        smoothstep(0.12, 0.32, y) *
        (1.0 - smoothstep(0.82, 0.96, y));

    float amount = 0.14 * low_sat_weight * (1.0 - 0.72 * skin_like);
    vec3 out_rgb = vec3(y) + (rgb - vec3(y)) * (1.0 + amount);
    return vec4(clamp(out_rgb, 0.0, 1.0), src.a);
}
