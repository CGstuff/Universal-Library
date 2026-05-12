"""
OpenGL shader sources for the asset viewport.

Stripped from World_Library/viewer/gl_shaders.py to just the two shader
programs we need: lit mesh rendering + flat-colored line rendering (for
the ground grid).
"""

from OpenGL.GL import *  # noqa: F403
from OpenGL.GL import shaders as gl_shaders


# ── Mesh shader (lit, single mesh — non-instanced) ──────────────────

MESH_VERT = """
#version 460
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec2 in_uv;

uniform mat4 u_view;
uniform mat4 u_proj;

out vec3 v_normal;
out vec3 v_world_pos;
out vec2 v_uv;

void main() {
    v_world_pos = in_position;
    v_normal = in_normal;
    v_uv = in_uv;
    gl_Position = u_proj * u_view * vec4(in_position, 1.0);
}
"""

MESH_FRAG = """
#version 460
in vec3 v_normal;
in vec3 v_world_pos;
in vec2 v_uv;

out vec4 frag_color;

uniform vec3 u_light_dir;
uniform vec3 u_view_pos;
uniform vec3 u_mesh_color;
uniform int u_has_tex;
uniform sampler2D u_base_tex;

void main() {
    vec3 normal = normalize(v_normal);
    float ndotl = max(dot(normal, u_light_dir), 0.0);

    float ambient = 0.3;
    float diffuse = ndotl * 0.6;

    vec3 view_dir = normalize(u_view_pos - v_world_pos);
    float rim = pow(1.0 - max(dot(normal, view_dir), 0.0), 3.0) * 0.1;

    vec3 albedo = u_mesh_color;
    if (u_has_tex == 1) {
        albedo *= texture(u_base_tex, v_uv).rgb;
    }

    vec3 color = albedo * (ambient + diffuse) + vec3(rim);
    frag_color = vec4(color, 1.0);
}
"""


# ── Line shader (flat color) ────────────────────────────────────────

LINE_VERT = """
#version 460
layout(location = 0) in vec3 in_position;

uniform mat4 u_vp;

void main() {
    gl_Position = u_vp * vec4(in_position, 1.0);
}
"""

LINE_FRAG = """
#version 460
uniform vec4 u_color;
out vec4 frag_color;

void main() {
    frag_color = u_color;
}
"""


# ── Skinning shader (linear blend skinning for rig preview) ─────────

# Hardcoded max joint count. Beyond this we reject the rig for animation
# preview. Fits classic game / character rigs comfortably; film rigs with
# 200+ bones need a UBO/SSBO build that's out of scope for Phase 6.
MAX_JOINTS = 64

SKIN_VERT = f"""
#version 460
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec2 in_uv;
layout(location = 3) in uvec4 in_joints;
layout(location = 4) in vec4  in_weights;

uniform mat4 u_view;
uniform mat4 u_proj;
uniform mat4 u_joints[{MAX_JOINTS}];

out vec3 v_normal;
out vec3 v_world_pos;
out vec2 v_uv;

void main() {{
    // Each palette entry already bakes Y→Z × joint_world × IBM, so applying
    // it to a bind-pose vertex (in glTF Y-up space) gives the final Z-up
    // world position directly.
    mat4 skin =
          u_joints[in_joints.x] * in_weights.x
        + u_joints[in_joints.y] * in_weights.y
        + u_joints[in_joints.z] * in_weights.z
        + u_joints[in_joints.w] * in_weights.w;

    vec4 pos_world = skin * vec4(in_position, 1.0);
    mat3 skin3     = mat3(skin);
    vec3 n_world   = normalize(skin3 * in_normal);

    v_world_pos = pos_world.xyz;
    v_normal    = n_world;
    v_uv        = in_uv;
    gl_Position = u_proj * u_view * pos_world;
}}
"""

# Frag is functionally identical to MESH_FRAG — same lighting model. Keep
# a separate string so future changes (joint debug viz, etc.) don't bleed
# into the static-mesh frag.
SKIN_FRAG = MESH_FRAG


def compile_shader_program(vert_src: str, frag_src: str) -> int:
    """Compile vertex + fragment shaders into a linked program."""
    vs = gl_shaders.compileShader(vert_src, GL_VERTEX_SHADER)
    fs = gl_shaders.compileShader(frag_src, GL_FRAGMENT_SHADER)
    return gl_shaders.compileProgram(vs, fs)


# ── Scale-reference silhouette shader (textured billboard) ──────────────
#
# A unit quad in local [-0.5..0.5] x [0..1] coords is transformed in the
# vertex shader using uniforms (anchor + camera-right + world-up + width
# + height) so the silhouette stays:
#   - feet on the world ground plane (always at anchor.z)
#   - upright (world Z up, never tilted)
#   - facing the camera (right axis = camera's right projected against Z)
# The PNG is sampled directly; pixels below an alpha threshold are
# discarded so the bbox/grid behind the silhouette stays visible.
SILHOUETTE_VERT = """
#version 460
layout(location = 0) in vec2 in_local;
layout(location = 1) in vec2 in_uv;

uniform mat4 u_view;
uniform mat4 u_proj;
uniform vec3 u_anchor;
uniform vec3 u_right;
uniform vec3 u_up;
uniform float u_width;
uniform float u_height;

out vec2 v_uv;

void main() {
    vec3 world_pos = u_anchor
                   + u_right * (in_local.x * u_width)
                   + u_up    * (in_local.y * u_height);
    gl_Position = u_proj * u_view * vec4(world_pos, 1.0);
    v_uv = in_uv;
}
"""

SILHOUETTE_FRAG = """
#version 460
in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_tex;

void main() {
    vec4 c = texture(u_tex, v_uv);
    if (c.a < 0.01) discard;
    frag_color = c;
}
"""
