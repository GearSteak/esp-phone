#include "audio.h"
#include <driver/i2s.h>
#include <math.h>

AudioPipeline g_audio;

bool AudioPipeline::begin(int sampleRate) {
  if (installed_) {
    if (sampleRate_ == sampleRate) return true;
    end();
  }
  sampleRate_ = sampleRate;

  i2s_config_t cfg = {
      .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_RX),
      .sample_rate = (uint32_t)sampleRate_,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
      .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 6,
      .dma_buf_len = AUDIO_FRAME_SAMPLES,
      .use_apll = false,
      .tx_desc_auto_clear = true,
      .fixed_mclk = 0,
  };

  i2s_pin_config_t pins = {
      .bck_io_num = I2S_BCLK,
      .ws_io_num = I2S_LRCK,
      .data_out_num = I2S_DOUT,
      .data_in_num = I2S_DIN,
  };

  if (i2s_driver_install((i2s_port_t)I2S_PORT_NUM, &cfg, 0, nullptr) != ESP_OK) return false;
  if (i2s_set_pin((i2s_port_t)I2S_PORT_NUM, &pins) != ESP_OK) return false;
  i2s_zero_dma_buffer((i2s_port_t)I2S_PORT_NUM);
  installed_ = true;
  return true;
}

bool AudioPipeline::setSampleRate(int sampleRate) {
  return begin(sampleRate);
}

void AudioPipeline::end() {
  stopCallAudio();
  if (installed_) {
    i2s_driver_uninstall((i2s_port_t)I2S_PORT_NUM);
    installed_ = false;
  }
}

void AudioPipeline::startCallAudio() {
  if (!installed_) begin();
  running_ = true;
}

void AudioPipeline::stopCallAudio() {
  running_ = false;
  if (installed_) i2s_zero_dma_buffer((i2s_port_t)I2S_PORT_NUM);
}

size_t AudioPipeline::readMic(int16_t* pcm, size_t samples) {
  if (!installed_ || !pcm) return 0;
  size_t bytesRead = 0;
  i2s_read((i2s_port_t)I2S_PORT_NUM, pcm, samples * sizeof(int16_t), &bytesRead,
           pdMS_TO_TICKS(50));
  return bytesRead / sizeof(int16_t);
}

size_t AudioPipeline::writeSpk(const int16_t* pcm, size_t samples) {
  if (!installed_ || !pcm) return 0;
  size_t bytesWritten = 0;
  i2s_write((i2s_port_t)I2S_PORT_NUM, pcm, samples * sizeof(int16_t), &bytesWritten,
            pdMS_TO_TICKS(50));
  return bytesWritten / sizeof(int16_t);
}

void AudioPipeline::playTestTone(uint32_t durationMs) {
  playTone(1000, durationMs, 8000.0f);
}

void AudioPipeline::playTone(uint16_t freqHz, uint32_t durationMs,
                             float amplitude) {
  if (!installed_) begin();
  const float freq = (float)freqHz;
  const float amp = amplitude;
  int16_t frame[AUDIO_FRAME_SAMPLES];
  uint32_t start = millis();
  uint32_t n = 0;
  while (millis() - start < durationMs) {
    for (int i = 0; i < AUDIO_FRAME_SAMPLES; i++, n++) {
      float t = (float)n / (float)I2S_SAMPLE_RATE;
      frame[i] = (int16_t)(sinf(2.0f * PI * freq * t) * amp);
    }
    writeSpk(frame, AUDIO_FRAME_SAMPLES);
  }
  i2s_zero_dma_buffer((i2s_port_t)I2S_PORT_NUM);
}

// G.711 u-law (PCMU)
uint8_t AudioPipeline::linearToUlaw(int16_t sample) {
  const uint16_t BIAS = 0x84;
  const uint16_t CLIP = 32635;
  uint8_t sign = (sample < 0) ? 0x80 : 0;
  if (sample < 0) sample = -sample;
  if (sample > (int16_t)CLIP) sample = CLIP;
  sample += BIAS;
  uint8_t exponent = 7;
  for (int expMask = 0x4000; (sample & expMask) == 0 && exponent > 0;
       exponent--, expMask >>= 1) {
  }
  uint8_t mantissa = (sample >> (exponent + 3)) & 0x0F;
  uint8_t ulaw = ~(sign | (exponent << 4) | mantissa);
  return ulaw;
}

int16_t AudioPipeline::ulawToLinear(uint8_t ulaw) {
  static const int16_t table[256] = {
      -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956, -23932,
      -22908, -21884, -20860, -19836, -18812, -17788, -16764, -15996, -15484,
      -14972, -14460, -13948, -13436, -12924, -12412, -11900, -11388, -10876,
      -10364, -9852,  -9340,  -8828,  -8316,  -7932,  -7676,  -7420,  -7164,
      -6908,  -6652,  -6396,  -6140,  -5884,  -5628,  -5372,  -5116,  -4860,
      -4604,  -4348,  -4092,  -3900,  -3772,  -3644,  -3516,  -3388,  -3260,
      -3132,  -3004,  -2876,  -2748,  -2620,  -2492,  -2364,  -2236,  -2108,
      -1980,  -1884,  -1820,  -1756,  -1692,  -1628,  -1564,  -1500,  -1436,
      -1372,  -1308,  -1244,  -1180,  -1116,  -1052,  -988,   -924,   -876,
      -844,   -812,   -780,   -748,   -716,   -684,   -652,   -620,   -588,
      -556,   -524,   -492,   -460,   -428,   -396,   -372,   -356,   -340,
      -324,   -308,   -292,   -276,   -260,   -244,   -228,   -212,   -196,
      -180,   -164,   -148,   -132,   -120,   -112,   -104,   -96,    -88,
      -80,    -72,    -64,    -56,    -48,    -40,    -32,    -24,    -16,
      -8,     0,      32124,  31100,  30076,  29052,  28028,  27004,  25980,
      24956,  23932,  22908,  21884,  20860,  19836,  18812,  17788,  16764,
      15996,  15484,  14972,  14460,  13948,  13436,  12924,  12412,  11900,
      11388,  10876,  10364,  9852,   9340,   8828,   8316,   7932,   7676,
      7420,   7164,   6908,   6652,   6396,   6140,   5884,   5628,   5372,
      5116,   4860,   4604,   4348,   4092,   3900,   3772,   3644,   3516,
      3388,   3260,   3132,   3004,   2876,   2748,   2620,   2492,   2364,
      2236,   2108,   1980,   1884,   1820,   1756,   1692,   1628,   1564,
      1500,   1436,   1372,   1308,   1244,   1180,   1116,   1052,   988,
      924,    876,    844,    812,    780,    748,    716,    684,    652,
      620,    588,    556,    524,    492,    460,    428,    396,    372,
      356,    340,    324,    308,    292,    276,    260,    244,    228,
      212,    196,    180,    164,    148,    132,    120,    112,    104,
      96,     88,     80,     72,     64,     56,     48,     40,     32,
      24,     16,     8,      0};
  return table[ulaw];
}

void AudioPipeline::encodePcmu(const int16_t* pcm, uint8_t* out, size_t n) {
  for (size_t i = 0; i < n; i++) out[i] = linearToUlaw(pcm[i]);
}

void AudioPipeline::decodePcmu(const uint8_t* in, int16_t* pcm, size_t n) {
  for (size_t i = 0; i < n; i++) pcm[i] = ulawToLinear(in[i]);
}
