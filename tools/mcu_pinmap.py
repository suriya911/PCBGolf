"""STM32H725 LQFP-144 -> LQFP-100 pin remap.

Keys are pin names on the original STM32H725ZGTx, values are the pin on the
STM32H725VGTx that takes over that signal. Pins that exist on both packages and
keep their signal are not listed. Every move keeps the peripheral the firmware
needs (ADC input, FDCAN, SDMMC1, USB) - only the GPIO/AF config changes.
"""

REMAP = {
    # status RGB LED - plain GPIO, PE3 doesn't exist on the 100 pin part
    "PE3": "PE4",   # LED_G
    "PE4": "PE5",   # LED_R
    # SBU voltage sense (port F is gone), all still ADC inputs
    "PF7": "PA2",   # ADC12_INP14
    "PF8": "PA3",   # ADC12_INP15
    "PF9": "PA7",   # ADC12_INP7
    "PF10": "PB0",  # ADC12_INP9
    "PF11": "PC5",  # CH3_IMON, ADC12_INP8
    # button GPIO (still also on BOOT0)
    "PE15": "PE7",
    # CAN2 on FDCAN3: PG9/PG10 -> PD13/PD12 (AF5)
    "PG9": "PD13",
    "PG10": "PD12",
    # signals that were on PD12/PD13 move out of the way
    "PD12": "PC6",  # CH3_SBU1_IGN
    "PD13": "PC7",  # CH3_SBU2_RELAY
    # PD6/PD7/PE0/PE1 don't exist on LQFP-100
    "PD6": "PE8",   # CH2_SBU1_RELAY
    "PD7": "PB2",   # CAN2_EN
    "PE0": "PA8",   # CH4_SBU2_IGN
    "PE1": "PA15",  # CH4_SBU2_RELAY
}

# Pins on the old part with no equivalent that are simply dropped.
# PDR_ON is hard-wired on the 100 pin package, so its pull-up (R11) goes too.
DROPPED = {"PDR_ON": "R11"}
