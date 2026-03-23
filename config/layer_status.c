#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zmk/keymap.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/usb/usb.h>
#include <zmk/hid.h>
#include <zmk/endpoints.h>
#include <zmk-raw-hid/raw_hid.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#if IS_ENABLED(CONFIG_ZMK_RAW_HID)

static int layer_status_listener(const zmk_event_t *eh) {
    const struct zmk_layer_state_changed *ev = as_zmk_layer_state_changed(eh);
    if (ev == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    uint8_t highest_layer = zmk_keymap_highest_layer_active();
    
    // Preparar el reporte para enviar por Raw HID
    // El formato será: [ID_Comando, Capa_Activa, 0, 0...]
    // Usamos 0x11 como ID de comando para identificar que es un estado de capa
    uint8_t report[32] = {0};
    report[0] = 0x11; 
    report[1] = highest_layer;

    // Enviar el reporte
    zmk_raw_hid_send(report, sizeof(report));
    
    LOG_DBG("Sent layer status to host: Layer %d", highest_layer);

    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_status, layer_status_listener);
ZMK_SUBSCRIPTION(layer_status, zmk_layer_state_changed);

#endif // IS_ENABLED(CONFIG_ZMK_RAW_HID)