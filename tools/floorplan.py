"""Generate the stack floorplan (anchors + risers) for a given square board size.

usage: python tools/floorplan.py <side_mm>

Writes placement/B0.json, B1.json, B2.json and placement/risers.json.
Coordinates are shared by all three boards (x right, y down, origin top-left).

Bottom board: USB-C receptacles 8.94 wide / 8.1 deep with the mating face on
the board edge. Two on the top edge, two on the right edge, one on the bottom
edge (right corner); the DC jack on the bottom edge. Same-edge receptacles are
12.95 mm apart (USB-C needs 12.85 between plug centres).
The jack is 7.2 mm tall, so it passes through both upper boards: keepout.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "placement")

USB_HALF_W = 4.47
USB_FRONT = 5.31      # footprint origin to mating face
USB_DEPTH = 8.10
PITCH = 2.0


def plan(S):
    p = {}
    c0 = USB_HALF_W + 1.1          # keeps the shell tab pads 0.2 mm off the side edges
    p["J5"] = [c0, USB_FRONT, 180]
    p["J3"] = [c0 + 12.95, USB_FRONT, 180]
    p["J6"] = [S - USB_FRONT, c0, 90]
    p["J7"] = [S - USB_FRONT, c0 + 12.95, 90]
    p["J8"] = [S - c0, S - USB_FRONT, 0]
    jack_x = S - 17.0
    p["J1"] = [jack_x, S, 90]
    jack = [jack_x - 6.4, S - 11.7, jack_x + 4.0, S]

    right = S - USB_DEPTH          # inner edge of the right-hand receptacles
    gap_y = USB_HALF_W * 2 + 0.13 + 1.3  # just below J6's shell tabs
    zone_b = right - 3.6           # 2-column strip just left of them
    # "at" is only a target here: tools/plan_risers.py moves each group to the nearest
    # spot that is free on every board it passes through.
    strip_x = right - 3.5           # between the MCU (B1) and the right-hand receptacles (B0)
    left_x = 4.0                    # left of the jack, below the MCU
    risers = {
        "P2": {"at": [strip_x, 10.0], "nets": ["CH2_D_P", "CH2_D_N", "CH2_SBU1", "CH2_SBU2", "CH2_PWR_EN", "CH2_IMON"]},
        "P3": {"at": [strip_x, 15.0], "nets": ["CH3_D_P", "CH3_D_N", "CH3_SBU1", "CH3_SBU2", "CH3_PWR_EN", "CH3_IMON"]},
        "P4": {"at": [strip_x, 20.0], "nets": ["CH4_D_P", "CH4_D_N", "CH4_SBU1", "CH4_SBU2", "CH4_PWR_EN", "CH4_IMON"]},
        "P1": {"at": [left_x, S - 13.0], "nets": ["CH1_D_P", "CH1_D_N", "CH1_SBU1", "CH1_SBU2", "CH1_PWR_EN", "CH1_IMON"]},
        "P5": {"at": [left_x, S - 9.0],
               "nets": ["CAN0_H", "CAN0_L", "CAN1_H", "CAN1_L", "CAN2_H", "CAN2_L", "CAN3_H", "CAN3_L"]},
        "P6": {"at": [left_x, S - 5.0], "nets": ["+12V", "+12V#2", "GND", "GND#2", "GND#3", "GND#4"]},
        "P8": {"at": [left_x, S - 2.0], "nets": ["USB_D_P", "USB_D_N"]},
        # MCU <-> top board only: above the right-hand receptacles, B0 not involved
        "P7": {"at": [S - 4.5, 12.0], "span": ["B1", "B2"],
               "nets": ["+3V3", "+3V3#2", "GND#5", "BTN", "LED_R", "LED_G", "LED_B", "SD_CLK", "SD_CMD",
                        "SD_D0", "SD_D1", "SD_D2", "SD_D3", "STM_D_P", "STM_D_N",
                        "CAN0_TX", "CAN0_RX", "CAN0_EN", "CAN1_TX", "CAN1_RX", "CAN1_EN",
                        "CAN2_TX", "CAN2_RX", "CAN2_EN", "CAN3_TX", "CAN3_RX", "CAN3_EN", "GND#6"]},
    }
    boards = {
        "B0": {"outline": [S, S], "parts": {k: p[k] for k in ("J5", "J3", "J6", "J7", "J8", "J1")}, "keepout": []},
        "B1": {"outline": [S, S], "parts": {"U3": [9.2, 9.2, 0]}, "keepout": [jack]},
        "B2": {"outline": [S, S], "parts": {"J2": [6.6, 6.5, 0]}, "keepout": [jack]},
    }
    return boards, risers


def main(S):
    boards, risers = plan(S)
    os.makedirs(OUT, exist_ok=True)
    for name, spec in boards.items():
        json.dump(spec, open(os.path.join(OUT, f"{name}.json"), "w"), indent=1)
    json.dump(risers, open(os.path.join(OUT, "risers.json"), "w"), indent=1)
    print(f"floorplan for {S} mm written")


if __name__ == "__main__":
    main(float(sys.argv[1]))
