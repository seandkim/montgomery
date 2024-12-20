import cv2
import numpy as np
import os
from PIL import Image
from typing import List, Optional
import matplotlib.pyplot as plt
import torch
import torch.nn as nn

from montgomery import helper
from montgomery import sam2_helper
from montgomery import mediapipe_helper as mp_helper

from montgomery.helper import GuitarTab, print_verbose
from montgomery.sam2_helper import SAM2MaskResult
from montgomery.mediapipe_helper import HandResult, Handedness


def run_canny_edge(
    image_rgb: np.ndarray, skip_blur=False, show_image=False
) -> np.ndarray:
    result = image_rgb.copy()
    result = cv2.cvtColor(result, cv2.COLOR_RGB2GRAY)
    if not skip_blur:
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


def select_fretboard_mask_result(mask_results: List[SAM2MaskResult]) -> SAM2MaskResult:
    best_mask_result, best_score = None, -1
    for mask_result in mask_results:
        score = helper.rectangularity_score(mask_result.mask)
        # print_verbose(score)
        if score > best_score:
            best_mask_result, best_score = mask_result, score
    return best_mask_result


def get_fretboard_mask_result(
    image_rgb: np.ndarray,
    input_point: np.ndarray,
    input_label: np.ndarray,
    show_all_masks=False,
    ignore_not_found=False,
) -> SAM2MaskResult:
    device = helper.setup_torch_device()
    mask_results = sam2_helper.run_sam2(device, image_rgb, input_point, input_label)
    if ignore_not_found and (mask_results is None or len(mask_results) == 0):
        raise RuntimeError("Mask results not found")
    if show_all_masks:
        for mask_result in mask_results:
            sam2_helper.show_mask(
                image_rgb,
                mask_result,
                point_coords=input_point,
                input_labels=input_label,
                borders=True,
                block=True,
            )
    return select_fretboard_mask_result(mask_results)


# endregion


def get_hand_result(
    image_rgb: np.ndarray, save_image=False, ignore_not_found=False
) -> mp_helper.HandResult:
    min_confidence = 0.1
    with mp_helper.initialize_mp_hands(min_confidence=min_confidence) as hands:
        hand_results = mp_helper.run_mp_hands(hands, image_rgb)
        if ignore_not_found and (hand_results is None or len(hand_results) == 0):
            raise RuntimeError("Hand results not found")

        for hand_result in hand_results:
            if hand_result.handedness == Handedness.LEFT:
                return hand_result
    return None


# Visual Montgomery Result (detecting fretboard mask and hand in one image)
class VisMontResult:
    def __init__(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        canny: np.ndarray,
        hand: HandResult,
    ):
        self.image = image
        self.mask = mask
        self.canny = canny
        self.hand = hand

    def plot_canny_and_fingertips(self, exclude_thumb=False, title=""):
        indices = [0, 1, 2, 3, 4]
        if exclude_thumb:
            indices = [1, 2, 3, 4]
        helper.show_image_with_point(self.canny, self.hand.tips(indices), title=title)


def run_vismont(image_rgb, fretboard_mask_result: SAM2MaskResult):
    hand_result: HandResult = get_hand_result(image_rgb)

    angle_to_rotate_ccw = fretboard_mask_result.get_angle_from_positive_x_axis() - 90
    image_rotated = helper.rotate_ccw(
        image_rgb,
        angle_to_rotate_ccw,
        (image_rgb.shape[1] // 2, image_rgb.shape[0] // 2),
    )
    mask_rotated = fretboard_mask_result.rotate_ccw(angle_to_rotate_ccw)
    hand_rotated = hand_result.rotate_ccw(angle_to_rotate_ccw)
    image_rotated_masked = mask_rotated.apply_to_image(image_rotated)
    canny = run_canny_edge(image_rotated_masked, skip_blur=False)

    return VisMontResult(image_rgb, mask_rotated.mask, canny, hand_rotated)


class HED(nn.Module):
    # Define the HED architecture
    pass


def test_vismont_on_one_image(file):
    image_bgr = Image.open(file)
    image_rgb = np.array(image_bgr.convert("RGB"))
    # helper.show_image(image_rgb)

    # input_point = np.array([[1600, 200]])  # images/raw/guitar.png
    # input_point = np.array([[2670, 558]])  # sweetchild/screenshot.png
    input_point = np.array([[1200, 230]])  # sweetchild/1.png
    input_label = np.array([1])
    fretboard_mask_result: SAM2MaskResult = get_fretboard_mask_result(
        image_rgb, input_point, input_label, show_all_masks=False
    )
    vismont = run_vismont(image_rgb, fretboard_mask_result)

    # HED
    model = HED()
    model.load_state_dict(torch.load("hed_pretrained.pth"))
    model.eval()

    def preprocess(image_path):
        img = cv2.imread(image_path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_resized = cv2.resize(img, (512, 512))  # HED typically uses fixed sizes
        img_normalized = img_resized / 255.0
        img_transposed = img_normalized.transpose((2, 0, 1))  # Channels first
        img_tensor = torch.from_numpy(img_transposed).float().unsqueeze(0)
        return img_tensor, img_resized

    image_tensor, original_image = preprocess(file)
    with torch.no_grad():
        edges = model(image_tensor)
        edges = edges.squeeze().cpu().numpy()
        edges = (edges * 255).astype(np.uint8)

    plt.figure(figsize=(10, 5))
    plt.subplot(1, 2, 1)
    plt.imshow(original_image)
    plt.title("Original Image")
    plt.axis("off")

    plt.subplot(1, 2, 2)
    plt.imshow(edges, cmap="gray")
    plt.title("Detected Edges")
    plt.axis("off")

    plt.show(block=True)

    return vismont


if __name__ == "__main__":
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"  # TODO: needed?
    test_vismont_on_one_image("./files/sweetchild/1.png")
