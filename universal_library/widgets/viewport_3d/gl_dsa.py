"""OpenGL 4.6 DSA (Direct State Access) helpers for PyOpenGL.

PyOpenGL's DSA wrappers use C-style calling conventions that differ
from the convenience patterns used in older GL calls. This module
provides Pythonic wrappers that handle the argument translation.

Ported from World_Library_private_new/viewer/gl_dsa.py — no app coupling.
"""

from __future__ import annotations

import logging
import numpy as np

from OpenGL.GL import *  # noqa: F403

logger = logging.getLogger(__name__)

_dsa_available: bool | None = None


def check_dsa() -> bool:
    """Check if GL 4.6 DSA functions are available. Call after GL context init."""
    global _dsa_available
    try:
        buf = GLuint(0)
        glCreateBuffers(1, buf)
        glDeleteBuffers(1, buf)
        _dsa_available = True
        logger.info("GL 4.6 DSA: available")
    except Exception as e:
        _dsa_available = False
        logger.error(f"GL 4.6 DSA not available: {e}")
    return _dsa_available


def dsa_ok() -> bool:
    return _dsa_available is True


def dsa_create_buffer() -> int:
    buf = GLuint(0)
    glCreateBuffers(1, buf)
    return int(buf.value)


def dsa_buffer_storage(buffer: int, data, dynamic: bool = False):
    flags = GL_DYNAMIC_STORAGE_BIT if dynamic else 0
    if isinstance(data, (int, np.integer)):
        glNamedBufferStorage(buffer, int(data), None, flags)
    elif isinstance(data, np.ndarray):
        glNamedBufferStorage(buffer, data.nbytes, data, flags)
    else:
        glNamedBufferStorage(buffer, len(data), data, flags)


def dsa_buffer_sub_data(buffer: int, offset: int, data):
    if isinstance(data, np.ndarray):
        glNamedBufferSubData(buffer, offset, data.nbytes, data)
    else:
        glNamedBufferSubData(buffer, offset, len(data), data)


def dsa_create_vao() -> int:
    vao = GLuint(0)
    glCreateVertexArrays(1, vao)
    return int(vao.value)


def dsa_vao_vertex_buffer(vao: int, binding: int, buffer: int,
                          offset: int = 0, stride: int = 0):
    glVertexArrayVertexBuffer(vao, binding, buffer, offset, stride)


def dsa_vao_element_buffer(vao: int, buffer: int):
    glVertexArrayElementBuffer(vao, buffer)


def dsa_vao_attrib_format(vao: int, attrib: int, size: int,
                          gl_type=None, normalized: bool = False,
                          offset: int = 0):
    if gl_type is None:
        gl_type = GL_FLOAT
    glVertexArrayAttribFormat(vao, attrib, size, gl_type,
                              GL_TRUE if normalized else GL_FALSE, offset)


def dsa_vao_attrib_binding(vao: int, attrib: int, binding: int):
    glVertexArrayAttribBinding(vao, attrib, binding)


def dsa_enable_vao_attrib(vao: int, attrib: int):
    glEnableVertexArrayAttrib(vao, attrib)
