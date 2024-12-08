import math
from typing import List, Optional
import cv2
import os
import torch

import numpy as np
import matplotlib.pyplot as plt

# region verbose
VERBOSE = False


def print_verbose(*args, **kwargs):
    if VERBOSE:
        print(args, kwargs)


VERBOSE = os.environ.get("PYTHON_VERBOSE_MODE")
if VERBOSE is not None and VERBOSE.lower() == "true":
    VERBOSE = True
    print("VERBOSE mode is enabled")
# endregion


class Point:
    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z

    def rotate_ccw(self, angle_in_degree, cx, cy):
        d = -math.radians(angle_in_degree)
        X = self.x - cx
        Y = self.y - cy
        Z = self.z
        Xr = X * math.cos(d) - Y * math.sin(d)
        Yr = X * math.sin(d) + Y * math.cos(d)
        x_rot = Xr + cx
        y_rot = Yr + cy
        return Point(x_rot, y_rot, self.z)


def show_image(image: np.array, gray=False):
    plt.figure(figsize=(10, 10))
    if gray:
        plt.imshow(image, cmap="gray")
    else:
        plt.imshow(image)
    plt.axis("on")
    plt.show(block=True)


def show_image_with_point(image: np.array, points: List[Point], gray=False):
    plt.figure(figsize=(10, 10))
    if gray:
        plt.imshow(image, cmap="gray")
    else:
        plt.imshow(image)

    for point in points:
        plt.plot(point.x, point.y, "ro")
    plt.axis("on")
    plt.show(block=True)


def setup_torch_device() -> torch.device:
    # if using Apple MPS, fall back to CPU for unsupported ops
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

    # select the device for computation
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    print(f"using device: {device}")

    if device.type == "cuda":
        # use bfloat16 for the entire notebook
        torch.autocast("cuda", dtype=torch.bfloat16).__enter__()
        # turn on tfloat32 for Ampere GPUs (https://pytorch.org/docs/stable/notes/cuda.html#tensorfloat-32-tf32-on-ampere-devices)
        if torch.cuda.get_device_properties(0).major >= 8:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
    elif device.type == "mps":
        print(
            "\nSupport for MPS devices is preliminary. SAM 2 is trained with CUDA and might "
            "give numerically different outputs and sometimes degraded performance on MPS. "
            "See e.g. https://github.com/pytorch/pytorch/issues/84936 for a discussion."
        )
    np.random.seed(3)
    return device


def get_bounding_box(image_binary: np.array):
    coords = np.column_stack(np.where(image_binary > 0))
    if coords.size == 0:
        raise ValueError("image_binary is empty.")
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)
    return x_min, y_min, x_max, y_max


# e.g. 3 o'clock needle => 0, 12 o'clock needle => 90
# Use PCA to find orientation
def get_angle_from_positive_x_axis(image_binary: np.ndarray) -> np.float64:
    coords = np.column_stack(np.where(image_binary > 0))
    if coords.shape[0] == 0:
        raise ValueError("image is empty.")
    mean = np.mean(coords, axis=0)
    centered = coords - mean
    cov = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = eigvals.argsort()[::-1]
    eigvecs = eigvecs[:, order]
    angle_in_degree = np.degrees(np.arctan2(*eigvecs[:, 0][::-1]))
    return 180 - angle_in_degree


def rotate_ccw(
    image: np.ndarray,
    angle_in_degree: np.float64,
    center: Optional[tuple[int, int]] = None,
) -> np.ndarray:
    (h, w) = image.shape[:2]
    if center is None:
        center = (w // 2, h // 2)

    M = cv2.getRotationMatrix2D(center, angle_in_degree, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    return rotated


def crop_with_mask(image: np.ndarray, mask: np.ndarray, show_image=False):
    # Step 1: Get orientation
    if show_image:
        show_image(image, gray=True)
    mask_angle = get_angle_from_positive_x_axis(mask)
    print_verbose(f"Mask orientation: {mask_angle:.2f} degrees")
    # Step 2: Rotate mask to align long side horizontally
    rotated = rotate_ccw(image, 90 - mask_angle)
    rotated_mask = rotate_ccw(mask, 90 - mask_angle)
    if show_image:
        show_image(rotated, gray=True)
    if show_image:
        show_image(rotated_mask, gray=True)

    # Step 3: Crop the rotated mask
    # x_min, y_min, x_max, y_max = get_bounding_box(rotated_mask)
    # cropped = rotated[y_min : y_max + 1, x_min : x_max + 1]
    masked = np.copy(rotated)
    masked[rotated_mask == 0] = np.array([0, 0, 0])
    if show_image:
        show_image(masked, gray=True)
    return masked
