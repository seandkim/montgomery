import cv2
import numpy as np
import os
from PIL import Image
from typing import List
import matplotlib.pyplot as plt

from . import helper
from . import sam2_helper
from . import mediapipe_helper as mp_helper

from .helper import print_verbose, show_image
from .sam2_helper import SAM2MaskResult


def run_canny_edge(image_rgb: np.ndarray, blur=False, show_image=False) -> np.ndarray:
    result = image_rgb.copy()
    result = cv2.cvtColor(result, cv2.COLOR_RGB2GRAY)
    if blur:
        result = cv2.GaussianBlur(result, (5, 5), 1.4)
    result = cv2.Canny(result, 100, 200)

    if show_image:
        plt.subplot(121), plt.imshow(image_rgb, cmap="gray")
        plt.title("Original Image"), plt.xticks([]), plt.yticks([])
        plt.subplot(122), plt.imshow(result, cmap="gray")
        plt.title("Canny Edges"), plt.xticks([]), plt.yticks([])
        plt.show(block=True)

    return result


# region fretboard


def get_fretboard_mask_result(mask_results: List[SAM2MaskResult]) -> SAM2MaskResult:
    # TODO: implement
    return mask_results[1]


def get_fretboard_as_image(image_rgb: np.ndarray, show_image=False) -> np.ndarray:
    device = helper.setup_torch_device()
    mask_results = sam2_helper.run_sam2(device, image_rgb, input_point, input_label)
    if show_image:
        sam2_helper.show_mask(
            annotated_image,
            mask_results,
            point_coords=input_point,
            input_labels=input_label,
            borders=True,
            block=True,
        )
    fretboard_mask_result: SAM2MaskResult = get_fretboard_mask_result(mask_results)
    fretboard_cropped = helper.crop_with_mask(image_rgb, fretboard_mask_result.mask)
    if show_image:
        show_image(fretboard_cropped)
    run_canny_edge(fretboard_cropped, blur=False, show_image=True)
    return image_rgb


# endregion


if __name__ == "__main__":
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

    file = "./images/raw/guitar.png"
    image_bgr = Image.open(file)
    image_rgb = np.array(image_bgr.convert("RGB"))
    input_point = np.array([[1600, 200]])
    input_label = np.array([1])

    fretboard_image: np.ndarray = get_fretboard_as_image(image_rgb)
    canny_result = run_canny_edge(image_rgb)

    min_confidence = 0.1
    with mp_helper.initialize_mp_hands(min_confidence=min_confidence) as hands:
        mp_hand_results = mp_helper.run_mp_hands(hands, image_rgb)
        if mp_hand_results == None:
            print_verbose(
                f"hands not detected: file={file}, min_confidence={min_confidence}"
            )
            exit

        for idx, mp_hand_result in enumerate(mp_hand_results):
            annotated_image = mp_helper.annotate_mp_hand_result(
                image_rgb, mp_hand_result
            )
            # cv2.imwrite(f"{OUTPUT_DIR}/mediapipe_{base}_{idx}.{ext}", annotated_image)
