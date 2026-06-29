#pragma once

#include <stdint.h>

#define ZMK_COM_REPORT_MAGIC 'Z'
#define ZMK_COM_PROTOCOL_VERSION 1U
#define ZMK_COM_REPORT_SIZE 32U
#define ZMK_COM_REPORT_HEADER_SIZE 4U
#define ZMK_COM_REPORT_PAYLOAD_SIZE (ZMK_COM_REPORT_SIZE - ZMK_COM_REPORT_HEADER_SIZE)

#define ZMK_COM_SEQUENCE_MIN 0U
#define ZMK_COM_SEQUENCE_MAX UINT8_MAX

enum zmk_com_message_type {
    ZMK_COM_MESSAGE_LAYER_STATE = 0x01,
    ZMK_COM_MESSAGE_STATE_REQUEST = 0x02,
    ZMK_COM_MESSAGE_RGB_COMMAND = 0x10,
};

enum zmk_com_rgb_flags {
    ZMK_COM_RGB_FLAG_SET_COLOR = 0x01,
    ZMK_COM_RGB_FLAG_SET_EFFECT = 0x02,
    ZMK_COM_RGB_FLAG_TURN_ON = 0x04,
    ZMK_COM_RGB_FLAG_TURN_OFF = 0x08,
};

#define ZMK_COM_RGB_FLAG_MASK                                                                     \
    (ZMK_COM_RGB_FLAG_SET_COLOR | ZMK_COM_RGB_FLAG_SET_EFFECT | ZMK_COM_RGB_FLAG_TURN_ON |       \
     ZMK_COM_RGB_FLAG_TURN_OFF)

#define ZMK_COM_RGB_SATURATION 100U
#define ZMK_COM_RGB_BRIGHTNESS_MAX 100U
#define ZMK_COM_RGB_HUE_MAX 359U
#define ZMK_COM_RGB_EFFECT_SOLID 0U
#define ZMK_COM_RGB_EFFECT_BREATHE 1U
#define ZMK_COM_RGB_EFFECT_SPECTRUM 2U
#define ZMK_COM_RGB_EFFECT_SWIRL 3U
#define ZMK_COM_RGB_EFFECT_MAX ZMK_COM_RGB_EFFECT_SWIRL

struct zmk_com_report {
    uint8_t magic;
    uint8_t version;
    uint8_t type;
    uint8_t sequence;
    uint8_t payload[ZMK_COM_REPORT_PAYLOAD_SIZE];
};

struct zmk_com_layer_state_payload {
    uint8_t active_layer;
    uint8_t reserved[ZMK_COM_REPORT_PAYLOAD_SIZE - 1U];
};

struct zmk_com_rgb_command_payload {
    uint8_t flags;
    uint8_t effect;
    uint16_t hue_le;
    uint8_t brightness;
    uint8_t reserved[ZMK_COM_REPORT_PAYLOAD_SIZE - 5U];
};
