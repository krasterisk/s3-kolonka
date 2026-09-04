#include "app_wifi.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs.h"
#include "nvs_flash.h"

#define NVS_NS "wifi"
#define WIFI_CONNECTED_BIT BIT0
#define MAX_FAILS 6

static const char *TAG = "wifi";
static EventGroupHandle_t s_events;
static char s_status[48] = "Wi-Fi: starting";
static char s_ip[16] = "0.0.0.0";
static bool s_connected;
static bool s_setup_ap;
static int s_fails;
static httpd_handle_t s_httpd;

extern const uint8_t logo_png_start[] asm("_binary_logo_png_start");
extern const uint8_t logo_png_end[] asm("_binary_logo_png_end");

static void set_status(const char *text)
{
    strncpy(s_status, text, sizeof(s_status) - 1);
    s_status[sizeof(s_status) - 1] = 0;
}

static void trim(char *s)
{
    char *start = s;
    while (*start == ' ' || *start == '\t' || *start == '\r' || *start == '\n') {
        start++;
    }
    if (start != s) {
        memmove(s, start, strlen(start) + 1);
    }
    size_t n = strlen(s);
    while (n > 0 && (s[n - 1] == ' ' || s[n - 1] == '\t' || s[n - 1] == '\r' || s[n - 1] == '\n')) {
        s[--n] = 0;
    }
}

static bool load_creds(char *ssid, size_t ssid_len, char *pass, size_t pass_len)
{
    nvs_handle_t nvs;
    if (nvs_open(NVS_NS, NVS_READONLY, &nvs) != ESP_OK) {
        return false;
    }
    size_t sl = ssid_len;
    size_t pl = pass_len;
    esp_err_t ok = nvs_get_str(nvs, "ssid", ssid, &sl);
    if (ok == ESP_OK) {
        nvs_get_str(nvs, "pass", pass, &pl);
    }
    nvs_close(nvs);
    return ok == ESP_OK && ssid[0] != 0;
}

static void save_creds(const char *ssid, const char *pass)
{
    nvs_handle_t nvs;
    ESP_ERROR_CHECK(nvs_open(NVS_NS, NVS_READWRITE, &nvs));
    ESP_ERROR_CHECK(nvs_set_str(nvs, "ssid", ssid));
    ESP_ERROR_CHECK(nvs_set_str(nvs, "pass", pass ? pass : ""));
    ESP_ERROR_CHECK(nvs_commit(nvs));
    nvs_close(nvs);
}

static void start_httpd(void);

static void start_portal(void)
{
    s_setup_ap = true;
    s_connected = false;
    set_status("Wi-Fi: s3-kolonka");
    strcpy(s_ip, "192.168.4.1");

    wifi_config_t ap = {0};
    memcpy(ap.ap.ssid, "s3-kolonka", 10);
    ap.ap.ssid_len = 10;
    ap.ap.channel = 1;
    ap.ap.max_connection = 4;
    ap.ap.authmode = WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));
    ESP_ERROR_CHECK(esp_wifi_start());
    start_httpd();
    ESP_LOGI(TAG, "setup portal s3-kolonka -> http://192.168.4.1");
}

static const char *fail_text(uint8_t reason)
{
    switch (reason) {
    case WIFI_REASON_NO_AP_FOUND:
        return "Wi-Fi: not found";
    case WIFI_REASON_AUTH_FAIL:
    case WIFI_REASON_AUTH_EXPIRE:
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_ASSOC_FAIL:
        return "Wi-Fi: assoc fail";
    default:
        return NULL;
    }
}

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)base;
    if (id == WIFI_EVENT_STA_START && !s_setup_ap) {
        esp_wifi_connect();
    } else if (id == WIFI_EVENT_STA_DISCONNECTED && !s_setup_ap) {
        wifi_event_sta_disconnected_t *ev = data;
        s_connected = false;
        s_fails++;
        const char *why = fail_text(ev->reason);
        if (why) {
            set_status(why);
        } else {
            char line[48];
            snprintf(line, sizeof(line), "Wi-Fi: fail %u", (unsigned)ev->reason);
            set_status(line);
        }
        ESP_LOGW(TAG, "disconnect reason=%u fails=%d", (unsigned)ev->reason, s_fails);
        if (s_fails >= MAX_FAILS) {
            ESP_LOGW(TAG, "giving up, back to portal");
            esp_wifi_disconnect();
            esp_wifi_stop();
            start_portal();
            return;
        }
        esp_wifi_connect();
    }
}

static void on_ip(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)base;
    (void)id;
    ip_event_got_ip_t *event = data;
    snprintf(s_ip, sizeof(s_ip), IPSTR, IP2STR(&event->ip_info.ip));
    s_connected = true;
    s_fails = 0;
    /* Modem sleep adds 30–100 ms; WS writes to Finland then abort on 50 ms timeout. */
    esp_wifi_set_ps(WIFI_PS_NONE);
    char line[48];
    snprintf(line, sizeof(line), "Wi-Fi: %s", s_ip);
    set_status(line);
    if (s_events) {
        xEventGroupSetBits(s_events, WIFI_CONNECTED_BIT);
    }
}

static void html_escape(const char *in, char *out, size_t out_len)
{
    size_t o = 0;
    for (const char *p = in; *p && o + 6 < out_len; p++) {
        if (*p == '<') {
            memcpy(out + o, "&lt;", 4);
            o += 4;
        } else if (*p == '>') {
            memcpy(out + o, "&gt;", 4);
            o += 4;
        } else if (*p == '&') {
            memcpy(out + o, "&amp;", 5);
            o += 5;
        } else if (*p == '"') {
            memcpy(out + o, "&quot;", 6);
            o += 6;
        } else {
            out[o++] = *p;
        }
    }
    out[o] = 0;
}

static int scan_options(char *out, size_t out_len)
{
    wifi_scan_config_t scan = {
        .show_hidden = true,
        .scan_type = WIFI_SCAN_TYPE_ACTIVE,
    };
    int pos = snprintf(out, out_len, "<option value=\"\" selected disabled>Выберите сеть</option>");
    if (esp_wifi_scan_start(&scan, true) != ESP_OK) {
        return pos + snprintf(out + pos, out_len - (size_t)pos,
                              "<option value=\"\">Скан не удался</option>");
    }

    uint16_t n = 0;
    esp_wifi_scan_get_ap_num(&n);
    if (n == 0) {
        return pos + snprintf(out + pos, out_len - (size_t)pos,
                              "<option value=\"\">Сети 2.4 ГГц не найдены</option>");
    }
    if (n > 24) {
        n = 24;
    }

    wifi_ap_record_t *aps = heap_caps_calloc(n, sizeof(*aps),
                                             MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!aps) {
        aps = calloc(n, sizeof(*aps));
    }
    if (!aps) {
        return snprintf(out, out_len, "<option value=\"\">(no memory)</option>");
    }
    if (esp_wifi_scan_get_ap_records(&n, aps) != ESP_OK) {
        free(aps);
        return snprintf(out, out_len, "<option value=\"\">(scan read failed)</option>");
    }

    int used = 0;
    char seen[24][33];
    memset(seen, 0, sizeof(seen));

    for (int i = 0; i < n && pos + 120 < (int)out_len; i++) {
        if (aps[i].ssid[0] == 0) {
            continue;
        }
        bool dup = false;
        for (int j = 0; j < used; j++) {
            if (strcmp(seen[j], (char *)aps[i].ssid) == 0) {
                dup = true;
                break;
            }
        }
        if (dup) {
            continue;
        }
        strncpy(seen[used], (char *)aps[i].ssid, 32);
        used++;

        char esc[80];
        html_escape((char *)aps[i].ssid, esc, sizeof(esc));
        const char *bars = aps[i].rssi > -55 ? "▂▄▆█" : aps[i].rssi > -65 ? "▂▄▆" : aps[i].rssi > -75 ? "▂▄" : "▂";
        const char *lock = aps[i].authmode == WIFI_AUTH_OPEN ? "" : " 🔒";
        pos += snprintf(out + pos, out_len - (size_t)pos,
                        "<option value=\"%s\">%s%s  %s</option>",
                        esc, esc, lock, bars);
    }
    free(aps);
    return pos;
}

static esp_err_t logo_get(httpd_req_t *req)
{
    httpd_resp_set_type(req, "image/png");
    httpd_resp_set_hdr(req, "Cache-Control", "public, max-age=86400");
    return httpd_resp_send(req, (const char *)logo_png_start,
                           (ssize_t)(logo_png_end - logo_png_start));
}

static void *portal_alloc(size_t bytes)
{
    void *p = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!p) {
        p = malloc(bytes);
    }
    return p;
}

static const char s_page_fallback[] =
    "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>s3-kolonka</title></head>"
    "<body style='margin:0;background:#101418;color:#f2f4f8;"
    "font-family:sans-serif;padding:24px'>"
    "<h1>s3-kolonka</h1>"
    "<p>Только сети 2.4 ГГц.</p>"
    "<form method='POST' action='/save'>"
    "<p>SSID<br><input name='ssid_manual' required></p>"
    "<p>Пароль<br><input type='password' name='pass'></p>"
    "<p><button type='submit'>Сохранить и перезагрузить</button></p>"
    "</form></body></html>";

static esp_err_t page_get(httpd_req_t *req)
{
    char *page = portal_alloc(12288);
    char *opts = portal_alloc(3072);
    if (!page || !opts) {
        free(page);
        free(opts);
        httpd_resp_set_type(req, "text/html");
        return httpd_resp_send(req, s_page_fallback, HTTPD_RESP_USE_STRLEN);
    }
    scan_options(opts, 3072);
    snprintf(page, 12288,
             "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
             "<meta name='viewport' content='width=device-width,initial-scale=1'>"
             "<link rel='icon' href='/logo.png' type='image/png'>"
             "<title>s3-kolonka</title><style>"
             "*{box-sizing:border-box}"
             "body{margin:0;min-height:100vh;background:#101418;color:#f2f4f8;"
             "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
             "display:flex;justify-content:center}"
             ".card{width:100%%;max-width:440px;margin:28px 16px;padding:28px 22px 24px;"
             "background:#1a2028;border:1px solid #2a3340;border-radius:22px}"
             "img.logo{display:block;width:96px;height:96px;margin:0 auto 16px;"
             "border-radius:24px;box-shadow:0 10px 28px rgba(0,0,0,.35)}"
             "h1{margin:0 0 6px;text-align:center;font-size:22px;font-weight:650}"
             ".sub{margin:0 0 22px;text-align:center;color:#8aa0b4;font-size:13px;line-height:1.45}"
             "label{display:block;margin:0 0 6px;color:#8aa0b4;font-size:12px;letter-spacing:.04em;text-transform:uppercase}"
             "select,input[type=password],input[type=text]{width:100%%;margin:0 0 16px;padding:12px 14px;"
             "border:1px solid #2a3340;border-radius:12px;background:#101418;color:#f2f4f8;font-size:16px}"
             "select:focus,input:focus{outline:none;border-color:#3ddc97}"
             ".passwrap{position:relative;margin:0 0 16px}"
             ".passwrap input{margin:0;padding-right:48px}"
             ".eye{position:absolute;right:6px;top:50%%;transform:translateY(-50%%);"
             "width:38px;height:38px;padding:0;border:0;border-radius:10px;background:transparent;"
             "color:#8aa0b4;display:flex;align-items:center;justify-content:center;cursor:pointer}"
             ".eye:hover{color:#f2f4f8;background:#101418}"
             ".eye.on{color:#3ddc97}"
             ".eye svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.8;"
             "stroke-linecap:round;stroke-linejoin:round}"
             ".eye .off,.eye.on .on{display:none}"
             ".eye.on .off{display:block}"
             ".check{display:flex;align-items:center;gap:10px;margin:4px 0 14px;color:#c5d0da;font-size:14px}"
             ".check input{width:18px;height:18px;accent-color:#3ddc97}"
             "#manual{display:none}"
             "button[type=submit]{width:100%%;padding:13px;border:0;border-radius:14px;background:#3ddc97;color:#102018;"
             "font-size:16px;font-weight:650}"
             "button[type=submit]:active{transform:scale(.98)}"
             ".links{margin:16px 0 0;text-align:center}"
             ".links a{color:#3ddc97;text-decoration:none;font-size:14px}"
             "</style></head><body><div class='card'>"
             "<img class='logo' src='/logo.png' width='96' height='96' alt='s3-kolonka'>"
             "<h1>s3-kolonka</h1>"
             "<p class='sub'>Только сети <b>2.4 ГГц</b>.<br>5 ГГц колонка не видит.</p>"
             "<form method='POST' action='/save'>"
             "<label>Сеть</label>"
             "<select name='ssid' required>%s</select>"
             "<label class='check'><input type='checkbox' onchange=\"document.getElementById('manual').style.display=this.checked?'block':'none'\">"
             "Ввести имя сети вручную</label>"
             "<div id='manual'><label>SSID</label>"
             "<input type='text' name='ssid_manual' placeholder='Имя сети' autocomplete='off'></div>"
             "<label>Пароль</label>"
             "<div class='passwrap'>"
             "<input type='password' name='pass' id='p' placeholder='Пароль Wi‑Fi' autocomplete='current-password'>"
             "<button type='button' class='eye' id='e' aria-label='Показать пароль' onclick=\"var i=document.getElementById('p');var s=i.type==='password';i.type=s?'text':'password';this.classList.toggle('on',s);this.setAttribute('aria-label',s?'Скрыть пароль':'Показать пароль')\">"
             "<svg class='on' viewBox='0 0 24 24'><path d='M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z'/><circle cx='12' cy='12' r='3'/></svg>"
             "<svg class='off' viewBox='0 0 24 24'><path d='M3 3l18 18'/><path d='M10.6 10.6a3 3 0 104.2 4.2'/><path d='M9.9 5.2A11 11 0 0112 5c6.4 0 10 7 10 7a18 18 0 01-4.2 5.1M6.1 6.1A18 18 0 002 12s3.6 7 10 7c1.6 0 3-.3 4.3-.8'/></svg>"
             "</button></div>"
             "<button type='submit'>Сохранить и перезагрузить</button>"
             "</form>"
             "<div class='links'><a href='/'>Обновить список сетей</a></div>"
             "</div></body></html>",
             opts);
    httpd_resp_set_type(req, "text/html");
    esp_err_t err = httpd_resp_send(req, page, HTTPD_RESP_USE_STRLEN);
    free(page);
    free(opts);
    return err;
}

static void url_decode(char *s)
{
    char *o = s;
    for (char *i = s; *i; i++, o++) {
        if (*i == '+') {
            *o = ' ';
        } else if (*i == '%' && i[1] && i[2]) {
            char hex[3] = {i[1], i[2], 0};
            *o = (char)strtol(hex, NULL, 16);
            i += 2;
        } else {
            *o = *i;
        }
    }
    *o = 0;
}

static bool form_value(const char *body, const char *key, char *out, size_t out_len)
{
    char prefix[24];
    snprintf(prefix, sizeof(prefix), "%s=", key);
    const char *p = strstr(body, prefix);
    if (!p) {
        return false;
    }
    p += strlen(prefix);
    const char *end = strchr(p, '&');
    size_t n = end ? (size_t)(end - p) : strlen(p);
    if (n >= out_len) {
        n = out_len - 1;
    }
    memcpy(out, p, n);
    out[n] = 0;
    url_decode(out);
    trim(out);
    return out[0] != 0;
}

static esp_err_t recv_body(httpd_req_t *req, char *body, size_t body_len)
{
    int remaining = req->content_len;
    int pos = 0;
    if (remaining <= 0 || remaining >= (int)body_len) {
        remaining = (int)body_len - 1;
    }
    while (pos < remaining) {
        int n = httpd_req_recv(req, body + pos, remaining - pos);
        if (n <= 0) {
            break;
        }
        pos += n;
    }
    body[pos] = 0;
    return pos > 0 ? ESP_OK : ESP_FAIL;
}

static esp_err_t page_save(httpd_req_t *req)
{
    char body[512] = {0};
    if (recv_body(req, body, sizeof(body)) != ESP_OK) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "empty");
    }
    char ssid[33] = {0};
    char manual[33] = {0};
    char pass[65] = {0};
    form_value(body, "ssid_manual", manual, sizeof(manual));
    form_value(body, "ssid", ssid, sizeof(ssid));
    form_value(body, "pass", pass, sizeof(pass));
    if (manual[0]) {
        strncpy(ssid, manual, sizeof(ssid) - 1);
    }
    if (ssid[0] == 0) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "select a network");
    }
    ESP_LOGI(TAG, "saving ssid='%s' pass_len=%u", ssid, (unsigned)strlen(pass));
    save_creds(ssid, pass);
    httpd_resp_sendstr(req, "Saved. Rebooting...");
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_restart();
    return ESP_OK;
}

static void start_httpd(void)
{
    if (s_httpd) {
        return;
    }
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.lru_purge_enable = true;
    if (httpd_start(&s_httpd, &cfg) != ESP_OK) {
        ESP_LOGE(TAG, "httpd start failed");
        return;
    }
    httpd_uri_t get = {.uri = "/", .method = HTTP_GET, .handler = page_get};
    httpd_uri_t logo = {.uri = "/logo.png", .method = HTTP_GET, .handler = logo_get};
    httpd_uri_t post = {.uri = "/save", .method = HTTP_POST, .handler = page_save};
    httpd_register_uri_handler(s_httpd, &get);
    httpd_register_uri_handler(s_httpd, &logo);
    httpd_register_uri_handler(s_httpd, &post);
}

static void start_sta(const char *ssid, const char *pass)
{
    s_setup_ap = false;
    s_fails = 0;
    wifi_config_t sta = {0};
    strlcpy((char *)sta.sta.ssid, ssid, sizeof(sta.sta.ssid));
    strlcpy((char *)sta.sta.password, pass, sizeof(sta.sta.password));
    sta.sta.threshold.authmode = WIFI_AUTH_OPEN;
    sta.sta.pmf_cfg.capable = true;
    sta.sta.pmf_cfg.required = false;

    char line[48];
    snprintf(line, sizeof(line), "Wi-Fi: %s", ssid);
    set_status(line);

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta));
    ESP_ERROR_CHECK(esp_wifi_start());
}

void app_wifi_start(void)
{
    s_events = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &on_wifi, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &on_ip, NULL));

    char ssid[33] = {0};
    char pass[65] = {0};
    if (load_creds(ssid, sizeof(ssid), pass, sizeof(pass))) {
        start_sta(ssid, pass);
    } else {
        start_portal();
    }
}

bool app_wifi_connected(void)
{
    return s_connected;
}

bool app_wifi_is_setup_ap(void)
{
    return s_setup_ap;
}

const char *app_wifi_status(void)
{
    return s_status;
}

const char *app_wifi_ip(void)
{
    return s_ip;
}

void app_wifi_forget(void)
{
    nvs_handle_t nvs;
    if (nvs_open(NVS_NS, NVS_READWRITE, &nvs) == ESP_OK) {
        nvs_erase_all(nvs);
        nvs_commit(nvs);
        nvs_close(nvs);
    }
    esp_restart();
}
