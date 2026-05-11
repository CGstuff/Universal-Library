"""Orbit camera for the 3D asset viewport."""

from __future__ import annotations

import math

import numpy as np


class OrbitCamera:
    """
    Arcball-style orbit camera.

    Controls:
    - Left-drag: orbit (azimuth + elevation)
    - Middle-drag: pan
    - Scroll: zoom (dolly)
    """

    def __init__(self):
        self.target = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        self.distance = 4.0
        self.azimuth = 45.0
        self.elevation = 25.0
        self.fov = 45.0
        self.near = 0.01
        self.far = 1000.0
        self.aspect = 1.0

        self.min_elevation = -89.0
        self.max_elevation = 89.0
        self.min_distance = 0.05
        self.max_distance = 500.0

    @property
    def eye(self) -> np.ndarray:
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        cos_el = math.cos(el)
        return self.target + self.distance * np.array(
            [cos_el * math.sin(az), cos_el * math.cos(az), math.sin(el)],
            dtype=np.float64,
        )

    def orbit(self, delta_az: float, delta_el: float):
        self.azimuth += delta_az
        self.elevation = max(
            self.min_elevation, min(self.max_elevation, self.elevation + delta_el)
        )

    def pan(self, dx: float, dy: float):
        view = self.get_view_matrix()
        right = np.array([view[0, 0], view[0, 1], view[0, 2]], dtype=np.float64)
        up = np.array([view[1, 0], view[1, 1], view[1, 2]], dtype=np.float64)
        speed = self.distance * 0.002
        self.target += right * dx * speed + up * dy * speed

    def zoom(self, delta: float):
        factor = 1.0 - delta * 0.1
        self.distance = max(
            self.min_distance, min(self.max_distance, self.distance * factor)
        )

    def frame_bbox(self, bbox_min: np.ndarray, bbox_max: np.ndarray, fit_factor: float = 1.3):
        """Position the camera so the bbox fills the view.

        bbox_min / bbox_max: (3,) arrays in world space.
        fit_factor: extra padding around the bbox (1.0 = tight fit).
        """
        center = (bbox_min + bbox_max) * 0.5
        size = np.linalg.norm(bbox_max - bbox_min)
        if size < 1e-6:
            size = 1.0
        self.target = center.astype(np.float64)
        half_fov = math.radians(self.fov) * 0.5
        self.distance = (size * 0.5 * fit_factor) / math.tan(half_fov)
        self.distance = max(self.min_distance, min(self.max_distance, self.distance))
        self.near = max(0.001, self.distance * 0.001)
        self.far = max(self.far, self.distance * 100.0)

    def get_view_matrix(self) -> np.ndarray:
        return look_at(self.eye, self.target, np.array([0, 0, 1], dtype=np.float64))

    def get_projection_matrix(self) -> np.ndarray:
        dynamic_far = max(self.far, self.distance * 5)
        return perspective(self.fov, self.aspect, self.near, dynamic_far)


def look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)

    m = np.eye(4, dtype=np.float64)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m


def perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float64)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m
