#include "mww.h"

#include <algorithm>
#include <cstring>
#include <new>

#include "audio_preprocessor_int8_model.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "hey_jarvis_model.h"

#include "tensorflow/lite/kernels/internal/tensor_ctypes.h"
#include "tensorflow/lite/micro/micro_allocator.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_resource_variable.h"
#include "tensorflow/lite/schema/schema_generated.h"

static const char *TAG = "mww";

static constexpr int kFeatureSize = 40;
static constexpr int kWindowSamples = 480;
static constexpr int kStrideSamples = 160;
static constexpr int kSlidingWindow = 5;
static constexpr int kMinSlicesBeforeDetect = 20;
static constexpr uint8_t kCutoff = 247; /* 0.97 * 255 */
static uint8_t s_cutoff = kCutoff;
static constexpr size_t kPreArenaSize = 16 * 1024;
static constexpr size_t kStreamArenaSize = 48 * 1024;
static constexpr size_t kVarArenaSize = 1024;
static constexpr int kResourceVars = 20;

static bool s_ok;
static int16_t *s_ring;
static int s_ring_write;
static uint8_t *s_pre_arena;
static uint8_t *s_stream_arena;
static uint8_t *s_var_arena;
static tflite::MicroInterpreter *s_pre;
static tflite::MicroInterpreter *s_stream;
static tflite::MicroAllocator *s_var_alloc;
static tflite::MicroResourceVariables *s_vars;
static uint8_t s_recent[kSlidingWindow];
static size_t s_recent_i;
static int16_t s_ignore;
static uint8_t s_stride_step;

alignas(tflite::MicroInterpreter) static uint8_t s_pre_mem[sizeof(tflite::MicroInterpreter)];
alignas(tflite::MicroInterpreter) static uint8_t s_stream_mem[sizeof(tflite::MicroInterpreter)];

static uint8_t *psram_aligned(size_t bytes)
{
    uint8_t *p = static_cast<uint8_t *>(
        heap_caps_aligned_alloc(16, bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!p) {
        p = static_cast<uint8_t *>(heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    }
    return p;
}

static bool register_pre_ops(tflite::MicroMutableOpResolver<20> &ops)
{
    return ops.AddReshape() == kTfLiteOk && ops.AddCast() == kTfLiteOk &&
           ops.AddStridedSlice() == kTfLiteOk && ops.AddConcatenation() == kTfLiteOk &&
           ops.AddMul() == kTfLiteOk && ops.AddAdd() == kTfLiteOk && ops.AddDiv() == kTfLiteOk &&
           ops.AddMinimum() == kTfLiteOk && ops.AddMaximum() == kTfLiteOk &&
           ops.AddWindow() == kTfLiteOk && ops.AddFftAutoScale() == kTfLiteOk &&
           ops.AddRfft() == kTfLiteOk && ops.AddEnergy() == kTfLiteOk &&
           ops.AddFilterBank() == kTfLiteOk && ops.AddFilterBankSquareRoot() == kTfLiteOk &&
           ops.AddFilterBankSpectralSubtraction() == kTfLiteOk && ops.AddPCAN() == kTfLiteOk &&
           ops.AddFilterBankLog() == kTfLiteOk;
}

static bool register_stream_ops(tflite::MicroMutableOpResolver<20> &ops)
{
    return ops.AddCallOnce() == kTfLiteOk && ops.AddVarHandle() == kTfLiteOk &&
           ops.AddReshape() == kTfLiteOk && ops.AddReadVariable() == kTfLiteOk &&
           ops.AddStridedSlice() == kTfLiteOk && ops.AddConcatenation() == kTfLiteOk &&
           ops.AddAssignVariable() == kTfLiteOk && ops.AddConv2D() == kTfLiteOk &&
           ops.AddMul() == kTfLiteOk && ops.AddAdd() == kTfLiteOk && ops.AddMean() == kTfLiteOk &&
           ops.AddFullyConnected() == kTfLiteOk && ops.AddLogistic() == kTfLiteOk &&
           ops.AddQuantize() == kTfLiteOk && ops.AddDepthwiseConv2D() == kTfLiteOk &&
           ops.AddAveragePool2D() == kTfLiteOk && ops.AddMaxPool2D() == kTfLiteOk &&
           ops.AddPad() == kTfLiteOk && ops.AddPack() == kTfLiteOk && ops.AddSplitV() == kTfLiteOk;
}

static void reset_probs(void)
{
    memset(s_recent, 0, sizeof(s_recent));
    s_recent_i = 0;
    s_ignore = -kMinSlicesBeforeDetect;
    s_stride_step = 0;
}

void mww_reset(void)
{
    s_ring_write = 0;
    if (s_ring) {
        memset(s_ring, 0, kWindowSamples * sizeof(int16_t));
    }
    reset_probs();
}

void mww_set_cutoff(uint8_t cutoff)
{
    s_cutoff = cutoff < 200 ? 200 : cutoff;
}

static bool features_from_window(const int16_t *window, int8_t *features)
{
    TfLiteTensor *input = s_pre->input(0);
    memcpy(tflite::GetTensorData<int16_t>(input), window, kWindowSamples * sizeof(int16_t));
    if (s_pre->Invoke() != kTfLiteOk) {
        ESP_LOGE(TAG, "pre invoke fail");
        return false;
    }
    TfLiteTensor *output = s_pre->output(0);
    memcpy(features, tflite::GetTensorData<int8_t>(output), kFeatureSize);
    return true;
}

static bool stream_infer(const int8_t *features)
{
    TfLiteTensor *input = s_stream->input(0);
    const int stride = input->dims->data[1];
    s_stride_step = static_cast<uint8_t>(s_stride_step % stride);
    memcpy(tflite::GetTensorData<int8_t>(input) + kFeatureSize * s_stride_step, features, kFeatureSize);
    s_stride_step++;
    if (s_stride_step < stride) {
        return false;
    }

    if (s_stream->Invoke() != kTfLiteOk) {
        ESP_LOGE(TAG, "stream invoke fail");
        return false;
    }

    TfLiteTensor *output = s_stream->output(0);
    s_recent_i = (s_recent_i + 1) % kSlidingWindow;
    s_recent[s_recent_i] = output->data.uint8[0];
    if (s_recent[s_recent_i] < s_cutoff) {
        s_ignore = std::min<int16_t>(static_cast<int16_t>(s_ignore + 1), 0);
    }
    return true;
}

static bool detected(void)
{
    if (s_ignore < 0) {
        return false;
    }
    uint32_t sum = 0;
    uint8_t max_p = 0;
    for (int i = 0; i < kSlidingWindow; i++) {
        sum += s_recent[i];
        max_p = std::max(max_p, s_recent[i]);
    }
    if (sum > static_cast<uint32_t>(s_cutoff) * kSlidingWindow) {
        ESP_LOGI(TAG, "hit avg=%u max=%u", (unsigned)(sum / kSlidingWindow), (unsigned)max_p);
        return true;
    }
    return false;
}

bool mww_start(void)
{
    const tflite::Model *pre_model = tflite::GetModel(g_audio_preprocessor_int8_tflite);
    const tflite::Model *stream_model = tflite::GetModel(g_hey_jarvis_tflite);
    if (pre_model->version() != TFLITE_SCHEMA_VERSION || stream_model->version() != TFLITE_SCHEMA_VERSION) {
        ESP_LOGE(TAG, "schema mismatch");
        return false;
    }

    static tflite::MicroMutableOpResolver<20> pre_ops;
    static tflite::MicroMutableOpResolver<20> stream_ops;
    if (!register_pre_ops(pre_ops) || !register_stream_ops(stream_ops)) {
        ESP_LOGE(TAG, "op register fail");
        return false;
    }

    s_pre_arena = psram_aligned(kPreArenaSize);
    s_stream_arena = psram_aligned(kStreamArenaSize);
    s_var_arena = psram_aligned(kVarArenaSize);
    s_ring = static_cast<int16_t *>(
        heap_caps_calloc(kWindowSamples, sizeof(int16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!s_pre_arena || !s_stream_arena || !s_var_arena || !s_ring) {
        ESP_LOGE(TAG, "arena alloc fail");
        return false;
    }

    s_var_alloc = tflite::MicroAllocator::Create(s_var_arena, kVarArenaSize);
    s_vars = tflite::MicroResourceVariables::Create(s_var_alloc, kResourceVars);
    if (!s_var_alloc || !s_vars) {
        ESP_LOGE(TAG, "resource vars fail");
        return false;
    }

    s_pre = new (s_pre_mem) tflite::MicroInterpreter(pre_model, pre_ops, s_pre_arena, kPreArenaSize);
    if (s_pre->AllocateTensors() != kTfLiteOk) {
        ESP_LOGE(TAG, "pre tensors fail");
        return false;
    }

    s_stream = new (s_stream_mem)
        tflite::MicroInterpreter(stream_model, stream_ops, s_stream_arena, kStreamArenaSize, s_vars);
    if (s_stream->AllocateTensors() != kTfLiteOk) {
        ESP_LOGE(TAG, "stream tensors fail used=%u", (unsigned)s_stream->arena_used_bytes());
        return false;
    }

    TfLiteTensor *in = s_stream->input(0);
    TfLiteTensor *out = s_stream->output(0);
    if (!in || in->type != kTfLiteInt8 || in->dims->size != 3 || in->dims->data[2] != kFeatureSize) {
        ESP_LOGE(TAG, "bad stream input");
        return false;
    }
    if (!out || out->type != kTfLiteUInt8) {
        ESP_LOGE(TAG, "bad stream output");
        return false;
    }

    reset_probs();
    s_ok = true;
    ESP_LOGI(TAG, "hey jarvis ready pre=%u stream=%u in=[%d,%d,%d]",
             (unsigned)s_pre->arena_used_bytes(), (unsigned)s_stream->arena_used_bytes(),
             in->dims->data[0], in->dims->data[1], in->dims->data[2]);
    return true;
}

bool mww_feed(const int16_t *mono, int samples)
{
    if (!s_ok || !mono || samples <= 0) {
        return false;
    }

    bool hit = false;
    for (int i = 0; i < samples; i++) {
        s_ring[s_ring_write++] = mono[i];
        if (s_ring_write < kWindowSamples) {
            continue;
        }

        int8_t features[kFeatureSize];
        if (features_from_window(s_ring, features) && stream_infer(features) && detected()) {
            hit = true;
            reset_probs();
        }

        memmove(s_ring, s_ring + kStrideSamples, (kWindowSamples - kStrideSamples) * sizeof(int16_t));
        s_ring_write = kWindowSamples - kStrideSamples;
    }
    return hit;
}
