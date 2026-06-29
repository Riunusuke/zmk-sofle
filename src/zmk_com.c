#include <errno.h>
#include <stdbool.h>
#include <stdint.h>

#include <drivers/behavior.h>
#include <raw_hid/events.h>

#include <dt-bindings/zmk/rgb.h>
#include <zephyr/device.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/util.h>

#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/keymap.h>

#include <zmk_com/protocol.h>

LOG_MODULE_REGISTER(zmk_com, CONFIG_ZMK_LOG_LEVEL);

#define ZMK_COM_RGB_BEHAVIOR_DEV DEVICE_DT_NAME(DT_INST(0, zmk_behavior_rgb_underglow))

BUILD_ASSERT(CONFIG_RAW_HID_REPORT_SIZE == ZMK_COM_REPORT_SIZE,
             "zmk-com expects 32-byte raw HID reports");
BUILD_ASSERT(sizeof(struct zmk_com_report) == ZMK_COM_REPORT_SIZE,
             "zmk-com report struct size must match the raw HID report size");

static uint8_t next_sequence;
static zmk_keymap_layer_index_t last_reported_layer = ZMK_KEYMAP_LAYER_ID_INVAL;

static bool zmk_com_header_is_valid(const struct raw_hid_received_event *event,
                                    const struct zmk_com_report **report) {
    if (event->length < ZMK_COM_REPORT_HEADER_SIZE || event->data == NULL) {
        return false;
    }

    *report = (const struct zmk_com_report *)event->data;

    return (*report)->magic == ZMK_COM_REPORT_MAGIC &&
           (*report)->version == ZMK_COM_PROTOCOL_VERSION;
}

static int zmk_com_send_layer_state(zmk_keymap_layer_index_t layer) {
    uint8_t data[ZMK_COM_REPORT_SIZE] = {0};
    struct zmk_com_report *report = (struct zmk_com_report *)data;
    struct zmk_com_layer_state_payload *payload =
        (struct zmk_com_layer_state_payload *)report->payload;

    report->magic = ZMK_COM_REPORT_MAGIC;
    report->version = ZMK_COM_PROTOCOL_VERSION;
    report->type = ZMK_COM_MESSAGE_LAYER_STATE;
    report->sequence = next_sequence++;
    payload->active_layer = layer;

    return raise_raw_hid_sent_event(
        (struct raw_hid_sent_event){.data = data, .length = sizeof(data)});
}

static int zmk_com_invoke_rgb_behavior(uint32_t param1, uint32_t param2) {
    struct zmk_behavior_binding binding = {
        .behavior_dev = ZMK_COM_RGB_BEHAVIOR_DEV,
        .param1 = param1,
        .param2 = param2,
    };
    struct zmk_behavior_binding_event event = {
        .layer = zmk_keymap_highest_layer_active(),
        .position = 0,
        .timestamp = k_uptime_get(),
#if IS_ENABLED(CONFIG_ZMK_SPLIT)
        .source = ZMK_POSITION_STATE_CHANGE_SOURCE_LOCAL,
#endif
    };

    return zmk_behavior_invoke_binding(&binding, event, true);
}

static int zmk_com_apply_rgb_command(const struct zmk_com_rgb_command_payload *payload) {
    uint8_t flags = payload->flags;

    if ((flags & ~ZMK_COM_RGB_FLAG_MASK) != 0U) {
        return -ENOTSUP;
    }

    if ((flags & ZMK_COM_RGB_FLAG_TURN_ON) != 0U && (flags & ZMK_COM_RGB_FLAG_TURN_OFF) != 0U) {
        return -EINVAL;
    }

    if ((flags & ZMK_COM_RGB_FLAG_SET_COLOR) != 0U) {
        uint16_t hue = sys_le16_to_cpu(payload->hue_le);

        if (hue > ZMK_COM_RGB_HUE_MAX || payload->brightness > ZMK_COM_RGB_BRIGHTNESS_MAX) {
            return -EINVAL;
        }

        int err = zmk_com_invoke_rgb_behavior(
            RGB_COLOR_HSB_CMD,
            RGB_COLOR_HSB_VAL(hue, ZMK_COM_RGB_SATURATION, payload->brightness));
        if (err) {
            return err;
        }
    }

    if ((flags & ZMK_COM_RGB_FLAG_SET_EFFECT) != 0U) {
        if (payload->effect > ZMK_COM_RGB_EFFECT_MAX) {
            return -EINVAL;
        }

        int err = zmk_com_invoke_rgb_behavior(RGB_EFS_CMD, payload->effect);
        if (err) {
            return err;
        }
    }

    if ((flags & ZMK_COM_RGB_FLAG_TURN_OFF) != 0U) {
        return zmk_com_invoke_rgb_behavior(RGB_OFF_CMD, 0);
    }

    if ((flags & ZMK_COM_RGB_FLAG_TURN_ON) != 0U) {
        return zmk_com_invoke_rgb_behavior(RGB_ON_CMD, 0);
    }

    return 0;
}

static int zmk_com_on_raw_hid(const zmk_event_t *eh) {
    const struct raw_hid_received_event *event = as_raw_hid_received_event(eh);

    if (event == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    const struct zmk_com_report *report = NULL;
    if (!zmk_com_header_is_valid(event, &report)) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (report->type == ZMK_COM_MESSAGE_STATE_REQUEST) {
        zmk_keymap_layer_index_t active_layer = zmk_keymap_highest_layer_active();
        int err = zmk_com_send_layer_state(active_layer);
        if (err == 0) {
            last_reported_layer = active_layer;
        } else {
            LOG_WRN("Failed to send requested layer state: %d", err);
        }

        return ZMK_EV_EVENT_BUBBLE;
    }

    if (report->type != ZMK_COM_MESSAGE_RGB_COMMAND) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (event->length < ZMK_COM_REPORT_HEADER_SIZE + sizeof(struct zmk_com_rgb_command_payload)) {
        LOG_WRN("Rejected short RGB command: %u", event->length);
        return ZMK_EV_EVENT_BUBBLE;
    }

    int err = zmk_com_apply_rgb_command((const struct zmk_com_rgb_command_payload *)report->payload);
    if (err) {
        LOG_WRN("Rejected RGB command: %d", err);
    }

    return ZMK_EV_EVENT_BUBBLE;
}

static int zmk_com_on_layer_state_changed(const zmk_event_t *eh) {
    const struct zmk_layer_state_changed *event = as_zmk_layer_state_changed(eh);

    if (event == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    zmk_keymap_layer_index_t active_layer = zmk_keymap_highest_layer_active();
    if (active_layer == last_reported_layer) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    int err = zmk_com_send_layer_state(active_layer);
    if (err == 0) {
        last_reported_layer = active_layer;
    } else {
        LOG_WRN("Failed to send layer state: %d", err);
    }

    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(zmk_com_raw_hid, zmk_com_on_raw_hid);
ZMK_SUBSCRIPTION(zmk_com_raw_hid, raw_hid_received_event);

ZMK_LISTENER(zmk_com_layer_state, zmk_com_on_layer_state_changed);
ZMK_SUBSCRIPTION(zmk_com_layer_state, zmk_layer_state_changed);
