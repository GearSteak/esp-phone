#include "sip.h"
#include "modem.h"
#include "audio.h"
#include "shared_state.h"
#include <Arduino.h>
#include <mbedtls/md5.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

SipClient g_sip;

static void randomHex(char* out, size_t nibbles) {
  for (size_t i = 0; i < nibbles; i++) {
    uint8_t v = (uint8_t)(esp_random() & 0xF);
    out[i] = "0123456789abcdef"[v];
  }
  out[nibbles] = 0;
}

void SipClient::setState(CallState s) {
  state_ = s;
  statusLock();
  g_status.callState = s;
  if (s == CALL_IN_CALL) g_status.callSeconds = 0;
  statusUnlock();
  if (stateCb_) stateCb_(s);
}

void SipClient::makeIds() {
  randomHex(callId_, 16);
  randomHex(tagLocal_, 8);
  randomHex(branch_, 12);
  rtpSsrc_ = esp_random();
  rtpSeq_ = (uint16_t)(esp_random() & 0xFFFF);
  rtpTs_ = esp_random();
}

void SipClient::md5Hex(const char* data, char out[33]) {
  unsigned char dig[16];
  mbedtls_md5((const unsigned char*)data, strlen(data), dig);
  for (int i = 0; i < 16; i++) sprintf(out + i * 2, "%02x", dig[i]);
  out[32] = 0;
}

bool SipClient::computeAuthResponse(const char* method, const char* uri,
                                    const char* realm, const char* nonce,
                                    char outResp[33]) {
  char ha1In[160], ha2In[160], ha1[33], ha2[33], respIn[200];
  snprintf(ha1In, sizeof(ha1In), "%s:%s:%s", SIP_USERNAME, realm, SIP_PASSWORD);
  snprintf(ha2In, sizeof(ha2In), "%s:%s", method, uri);
  md5Hex(ha1In, ha1);
  md5Hex(ha2In, ha2);
  snprintf(respIn, sizeof(respIn), "%s:%s:%s", ha1, nonce, ha2);
  md5Hex(respIn, outResp);
  return true;
}

bool SipClient::begin() {
  makeIds();
  statusLock();
  strncpy(localIp_, g_status.ipAddr[0] ? g_status.ipAddr : "0.0.0.0",
          sizeof(localIp_) - 1);
  statusUnlock();

  if (!g_modem.udpOpen(sipLink_, SIP_SERVER, SIP_PORT, SIP_LOCAL_PORT)) {
    Serial.println("[SIP] UDP open failed");
    return false;
  }
  return true;
}

bool SipClient::sendSip(const char* msg) {
  return g_modem.udpSend(sipLink_, (const uint8_t*)msg, strlen(msg));
}

bool SipClient::extractHeader(const char* msg, const char* name, char* out,
                              size_t outLen) {
  const char* p = msg;
  size_t nlen = strlen(name);
  while (*p) {
    const char* line = p;
    const char* nl = strstr(p, "\r\n");
    size_t llen = nl ? (size_t)(nl - p) : strlen(p);
    if (llen == 0) break;
    if (llen > nlen + 1 && strncasecmp(line, name, nlen) == 0 &&
        line[nlen] == ':') {
      const char* v = line + nlen + 1;
      while (*v == ' ') v++;
      size_t vlen = llen - (size_t)(v - line);
      if (vlen >= outLen) vlen = outLen - 1;
      memcpy(out, v, vlen);
      out[vlen] = 0;
      return true;
    }
    if (!nl) break;
    p = nl + 2;
  }
  return false;
}

bool SipClient::extractSdpMedia(const char* msg) {
  const char* sdp = strstr(msg, "\r\n\r\n");
  if (!sdp) return false;
  sdp += 4;
  const char* c = strstr(sdp, "c=IN IP4 ");
  if (c) {
    c += 9;
    size_t i = 0;
    while (c[i] && c[i] != '\r' && c[i] != '\n' && i + 1 < sizeof(remoteRtpHost_)) {
      remoteRtpHost_[i] = c[i];
      i++;
    }
    remoteRtpHost_[i] = 0;
  }
  const char* m = strstr(sdp, "m=audio ");
  if (m) {
    remoteRtpPort_ = (uint16_t)atoi(m + 8);
  }
  return remoteRtpPort_ > 0;
}

bool SipClient::buildRegister(char* buf, size_t len, bool withAuth,
                              const char* realm, const char* nonce) {
  char uri[96];
  snprintf(uri, sizeof(uri), "sip:%s", SIP_SERVER);
  char auth[256] = {0};
  if (withAuth && realm && nonce) {
    char resp[33];
    computeAuthResponse("REGISTER", uri, realm, nonce, resp);
    snprintf(auth, sizeof(auth),
             "Authorization: Digest username=\"%s\", realm=\"%s\", "
             "nonce=\"%s\", uri=\"%s\", response=\"%s\", algorithm=MD5\r\n",
             SIP_USERNAME, realm, nonce, uri, resp);
  }
  makeIds();
  return snprintf(
             buf, len,
             "REGISTER %s SIP/2.0\r\n"
             "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
             "Max-Forwards: 70\r\n"
             "From: \"%s\" <sip:%s@%s>;tag=%s\r\n"
             "To: <sip:%s@%s>\r\n"
             "Call-ID: %s@%s\r\n"
             "CSeq: %u REGISTER\r\n"
             "Contact: <sip:%s@%s:%u>\r\n"
             "Expires: %u\r\n"
             "User-Agent: %s\r\n"
             "%s"
             "Content-Length: 0\r\n"
             "\r\n",
             uri, localIp_, (unsigned)SIP_LOCAL_PORT, branch_, SIP_DISPLAY_NAME,
             SIP_USERNAME, SIP_SERVER, tagLocal_, SIP_USERNAME, SIP_SERVER,
             callId_, localIp_, (unsigned)cseq_++, SIP_USERNAME, localIp_,
             (unsigned)SIP_LOCAL_PORT, (unsigned)SIP_REGISTER_EXPIRES,
             SIP_USER_AGENT, auth) > 0;
}

bool SipClient::registerAccount() {
  char msg[1200];
  if (!buildRegister(msg, sizeof(msg), false, nullptr, nullptr)) return false;
  if (!sendSip(msg)) return false;

  // Wait briefly for 401/200 via loop polling — caller should keep calling loop()
  lastRegisterMs_ = millis();
  return true;
}

bool SipClient::unregister() {
  // Expires: 0
  char msg[1200];
  char uri[96];
  snprintf(uri, sizeof(uri), "sip:%s", SIP_SERVER);
  makeIds();
  snprintf(msg, sizeof(msg),
           "REGISTER %s SIP/2.0\r\n"
           "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
           "From: <sip:%s@%s>;tag=%s\r\n"
           "To: <sip:%s@%s>\r\n"
           "Call-ID: %s@%s\r\n"
           "CSeq: %u REGISTER\r\n"
           "Contact: <sip:%s@%s:%u>\r\n"
           "Expires: 0\r\n"
           "Content-Length: 0\r\n\r\n",
           uri, localIp_, (unsigned)SIP_LOCAL_PORT, branch_, SIP_USERNAME,
           SIP_SERVER, tagLocal_, SIP_USERNAME, SIP_SERVER, callId_, localIp_,
           (unsigned)cseq_++, SIP_USERNAME, localIp_, (unsigned)SIP_LOCAL_PORT);
  registered_ = false;
  return sendSip(msg);
}

bool SipClient::buildInvite(char* buf, size_t len, const char* target) {
  char requestUri[96];
  if (strncmp(target, "sip:", 4) == 0) {
    strncpy(requestUri, target, sizeof(requestUri) - 1);
  } else {
    snprintf(requestUri, sizeof(requestUri), "sip:%s@%s", target, SIP_SERVER);
  }
  strncpy(remoteUri_, requestUri, sizeof(remoteUri_) - 1);
  makeIds();

  char sdp[256];
  int sdpLen = snprintf(
      sdp, sizeof(sdp),
      "v=0\r\n"
      "o=- %lu %lu IN IP4 %s\r\n"
      "s=ESP Phone\r\n"
      "c=IN IP4 %s\r\n"
      "t=0 0\r\n"
      "m=audio %u RTP/AVP 0\r\n"
      "a=rtpmap:0 PCMU/8000\r\n"
      "a=sendrecv\r\n",
      (unsigned long)esp_random(), (unsigned long)esp_random(), localIp_,
      localIp_, (unsigned)SIP_RTP_PORT);

  return snprintf(
             buf, len,
             "INVITE %s SIP/2.0\r\n"
             "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
             "Max-Forwards: 70\r\n"
             "From: \"%s\" <sip:%s@%s>;tag=%s\r\n"
             "To: <%s>\r\n"
             "Call-ID: %s@%s\r\n"
             "CSeq: %u INVITE\r\n"
             "Contact: <sip:%s@%s:%u>\r\n"
             "Content-Type: application/sdp\r\n"
             "User-Agent: %s\r\n"
             "Content-Length: %d\r\n"
             "\r\n"
             "%s",
             requestUri, localIp_, (unsigned)SIP_LOCAL_PORT, branch_,
             SIP_DISPLAY_NAME, SIP_USERNAME, SIP_SERVER, tagLocal_, requestUri,
             callId_, localIp_, (unsigned)cseq_++, SIP_USERNAME, localIp_,
             (unsigned)SIP_LOCAL_PORT, SIP_USER_AGENT, sdpLen, sdp) > 0;
}

bool SipClient::dial(const char* numberOrUri) {
  if (state_ != CALL_IDLE && state_ != CALL_ENDED) return false;
  char msg[1600];
  if (!buildInvite(msg, sizeof(msg), numberOrUri)) return false;
  if (!sendSip(msg)) return false;
  setState(CALL_DIALING);
  statusLock();
  strncpy(g_status.callerId, numberOrUri, sizeof(g_status.callerId) - 1);
  statusUnlock();
  return true;
}

bool SipClient::buildOkInvite(char* buf, size_t len) {
  char sdp[256];
  int sdpLen = snprintf(
      sdp, sizeof(sdp),
      "v=0\r\n"
      "o=- %lu %lu IN IP4 %s\r\n"
      "s=ESP Phone\r\n"
      "c=IN IP4 %s\r\n"
      "t=0 0\r\n"
      "m=audio %u RTP/AVP 0\r\n"
      "a=rtpmap:0 PCMU/8000\r\n"
      "a=sendrecv\r\n",
      (unsigned long)esp_random(), (unsigned long)esp_random(), localIp_,
      localIp_, (unsigned)SIP_RTP_PORT);

  return snprintf(
             buf, len,
             "SIP/2.0 200 OK\r\n"
             "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
             "From: <%s>;tag=%s\r\n"
             "To: <sip:%s@%s>;tag=%s\r\n"
             "Call-ID: %s@%s\r\n"
             "CSeq: %u INVITE\r\n"
             "Contact: <sip:%s@%s:%u>\r\n"
             "Content-Type: application/sdp\r\n"
             "Content-Length: %d\r\n"
             "\r\n"
             "%s",
             localIp_, (unsigned)SIP_LOCAL_PORT, branch_, remoteUri_, tagRemote_,
             SIP_USERNAME, SIP_SERVER, tagLocal_, callId_, localIp_,
             (unsigned)cseq_, SIP_USERNAME, localIp_, (unsigned)SIP_LOCAL_PORT,
             sdpLen, sdp) > 0;
}

bool SipClient::answer() {
  if (state_ != CALL_RINGING) return false;
  char msg[1200];
  if (!buildOkInvite(msg, sizeof(msg))) return false;
  if (!sendSip(msg)) return false;

  if (remoteRtpPort_ && remoteRtpHost_[0]) {
    g_modem.udpOpen(rtpLink_, remoteRtpHost_, remoteRtpPort_, SIP_RTP_PORT);
  }
  g_audio.startCallAudio();
  callStartMs_ = millis();
  setState(CALL_IN_CALL);
  return true;
}

bool SipClient::buildBye(char* buf, size_t len) {
  return snprintf(
             buf, len,
             "BYE %s SIP/2.0\r\n"
             "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
             "From: <sip:%s@%s>;tag=%s\r\n"
             "To: <%s>;tag=%s\r\n"
             "Call-ID: %s@%s\r\n"
             "CSeq: %u BYE\r\n"
             "Content-Length: 0\r\n\r\n",
             remoteUri_[0] ? remoteUri_ : "sip:unknown", localIp_,
             (unsigned)SIP_LOCAL_PORT, branch_, SIP_USERNAME, SIP_SERVER,
             tagLocal_, remoteUri_, tagRemote_[0] ? tagRemote_ : "0", callId_,
             localIp_, (unsigned)cseq_++) > 0;
}

bool SipClient::hangup() {
  if (state_ == CALL_IDLE) return true;
  char msg[800];
  buildBye(msg, sizeof(msg));
  sendSip(msg);
  g_audio.stopCallAudio();
  g_modem.udpClose(rtpLink_);
  setState(CALL_ENDED);
  delay(50);
  setState(CALL_IDLE);
  return true;
}

bool SipClient::sendDtmf(char digit) {
  // RFC 2833 would need telephone-event; v1 uses SIP INFO
  char body[64];
  int blen = snprintf(body, sizeof(body),
                      "Signal=%c\r\nDuration=160\r\n", digit);
  char msg[700];
  snprintf(msg, sizeof(msg),
           "INFO %s SIP/2.0\r\n"
           "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
           "From: <sip:%s@%s>;tag=%s\r\n"
           "To: <%s>;tag=%s\r\n"
           "Call-ID: %s@%s\r\n"
           "CSeq: %u INFO\r\n"
           "Content-Type: application/dtmf-relay\r\n"
           "Content-Length: %d\r\n\r\n%s",
           remoteUri_, localIp_, (unsigned)SIP_LOCAL_PORT, branch_,
           SIP_USERNAME, SIP_SERVER, tagLocal_, remoteUri_,
           tagRemote_[0] ? tagRemote_ : "0", callId_, localIp_,
           (unsigned)cseq_++, blen, body);
  return sendSip(msg);
}

bool SipClient::buildAck(char* buf, size_t len) {
  return snprintf(
             buf, len,
             "ACK %s SIP/2.0\r\n"
             "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
             "From: <sip:%s@%s>;tag=%s\r\n"
             "To: <%s>;tag=%s\r\n"
             "Call-ID: %s@%s\r\n"
             "CSeq: %u ACK\r\n"
             "Content-Length: 0\r\n\r\n",
             remoteUri_, localIp_, (unsigned)SIP_LOCAL_PORT, branch_,
             SIP_USERNAME, SIP_SERVER, tagLocal_, remoteUri_,
             tagRemote_[0] ? tagRemote_ : "0", callId_, localIp_,
             (unsigned)(cseq_ - 1)) > 0;
}

void SipClient::handleRtp(const uint8_t* data, size_t len) {
  if (len < 12 || state_ != CALL_IN_CALL) return;
  // Minimal RTP header skip; payload is PCMU
  uint8_t cc = data[0] & 0x0F;
  size_t hdr = 12 + cc * 4;
  if (len <= hdr) return;
  const uint8_t* payload = data + hdr;
  size_t plen = len - hdr;
  int16_t pcm[AUDIO_FRAME_SAMPLES];
  size_t n = plen > AUDIO_FRAME_SAMPLES ? AUDIO_FRAME_SAMPLES : plen;
  AudioPipeline::decodePcmu(payload, pcm, n);
  g_audio.writeSpk(pcm, n);
}

void SipClient::sendRtpFrame() {
  if (state_ != CALL_IN_CALL || !remoteRtpPort_) return;
  int16_t pcm[AUDIO_FRAME_SAMPLES];
  size_t got = g_audio.readMic(pcm, AUDIO_FRAME_SAMPLES);
  if (got == 0) return;
  uint8_t ulaw[AUDIO_FRAME_SAMPLES];
  AudioPipeline::encodePcmu(pcm, ulaw, got);

  uint8_t pkt[12 + AUDIO_FRAME_SAMPLES];
  pkt[0] = 0x80;
  pkt[1] = 0x00;  // PT=0 PCMU
  pkt[2] = (rtpSeq_ >> 8) & 0xFF;
  pkt[3] = rtpSeq_ & 0xFF;
  rtpSeq_++;
  pkt[4] = (rtpTs_ >> 24) & 0xFF;
  pkt[5] = (rtpTs_ >> 16) & 0xFF;
  pkt[6] = (rtpTs_ >> 8) & 0xFF;
  pkt[7] = rtpTs_ & 0xFF;
  rtpTs_ += (uint32_t)got;
  pkt[8] = (rtpSsrc_ >> 24) & 0xFF;
  pkt[9] = (rtpSsrc_ >> 16) & 0xFF;
  pkt[10] = (rtpSsrc_ >> 8) & 0xFF;
  pkt[11] = rtpSsrc_ & 0xFF;
  memcpy(pkt + 12, ulaw, got);
  g_modem.udpSend(rtpLink_, pkt, 12 + got);
}

void SipClient::processAudio() {
  if (state_ == CALL_IN_CALL) sendRtpFrame();
}

void SipClient::handleSipMessage(const char* msg, size_t len) {
  (void)len;
  if (strncmp(msg, "SIP/2.0", 7) == 0) {
    int code = atoi(msg + 8);
    char auth[256] = {0};
    if (code == 401 || code == 407) {
      extractHeader(msg, "WWW-Authenticate", auth, sizeof(auth));
      if (!auth[0]) extractHeader(msg, "Proxy-Authenticate", auth, sizeof(auth));
      // Parse realm="..." nonce="..."
      char realm[64] = {0}, nonce[128] = {0};
      const char* r = strstr(auth, "realm=\"");
      const char* n = strstr(auth, "nonce=\"");
      if (r) {
        r += 7;
        size_t i = 0;
        while (r[i] && r[i] != '"' && i + 1 < sizeof(realm)) {
          realm[i] = r[i];
          i++;
        }
      }
      if (n) {
        n += 7;
        size_t i = 0;
        while (n[i] && n[i] != '"' && i + 1 < sizeof(nonce)) {
          nonce[i] = n[i];
          i++;
        }
      }
      char out[1400];
      if (buildRegister(out, sizeof(out), true, realm, nonce)) sendSip(out);
    } else if (code == 200) {
      char cseq[64] = {0};
      extractHeader(msg, "CSeq", cseq, sizeof(cseq));
      if (strstr(cseq, "REGISTER")) {
        registered_ = true;
        statusLock();
        g_status.sipRegistered = true;
        statusUnlock();
        Serial.println("[SIP] Registered");
      } else if (strstr(cseq, "INVITE")) {
        char to[128] = {0};
        extractHeader(msg, "To", to, sizeof(to));
        const char* tg = strstr(to, "tag=");
        if (tg) {
          tg += 4;
          size_t i = 0;
          while (tg[i] && tg[i] != ';' && tg[i] != ' ' &&
                 i + 1 < sizeof(tagRemote_)) {
            tagRemote_[i] = tg[i];
            i++;
          }
          tagRemote_[i] = 0;
        }
        extractSdpMedia(msg);
        char ack[600];
        buildAck(ack, sizeof(ack));
        sendSip(ack);
        if (remoteRtpPort_ && remoteRtpHost_[0]) {
          g_modem.udpOpen(rtpLink_, remoteRtpHost_, remoteRtpPort_,
                          SIP_RTP_PORT);
        }
        g_audio.startCallAudio();
        callStartMs_ = millis();
        setState(CALL_IN_CALL);
      }
    } else if (code == 180 || code == 183) {
      setState(CALL_RINGING);
    } else if (code >= 400) {
      g_audio.stopCallAudio();
      setState(CALL_ENDED);
      setState(CALL_IDLE);
    }
  } else if (strncmp(msg, "INVITE ", 7) == 0) {
    char from[128] = {0};
    extractHeader(msg, "From", from, sizeof(from));
    extractHeader(msg, "Call-ID", callId_, sizeof(callId_));
    // strip @host from Call-ID if present for our storage — keep full in header replies ideally
    char toTagSrc[128] = {0};
    extractHeader(msg, "From", toTagSrc, sizeof(toTagSrc));
    const char* tg = strstr(toTagSrc, "tag=");
    if (tg) {
      tg += 4;
      size_t i = 0;
      while (tg[i] && tg[i] != ';' && i + 1 < sizeof(tagRemote_)) {
        tagRemote_[i] = tg[i];
        i++;
      }
      tagRemote_[i] = 0;
    }
    // Remote URI from Contact or From
    const char* lt = strchr(from, '<');
    const char* gt = lt ? strchr(lt, '>') : nullptr;
    if (lt && gt) {
      size_t n = (size_t)(gt - lt - 1);
      if (n >= sizeof(remoteUri_)) n = sizeof(remoteUri_) - 1;
      memcpy(remoteUri_, lt + 1, n);
      remoteUri_[n] = 0;
    }
    extractSdpMedia(msg);
    randomHex(tagLocal_, 8);
    randomHex(branch_, 12);

    char trying[400];
    snprintf(trying, sizeof(trying),
             "SIP/2.0 100 Trying\r\n"
             "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
             "From: %s\r\n"
             "To: <sip:%s@%s>\r\n"
             "Call-ID: %s\r\n"
             "CSeq: 1 INVITE\r\n"
             "Content-Length: 0\r\n\r\n",
             localIp_, (unsigned)SIP_LOCAL_PORT, branch_, from, SIP_USERNAME,
             SIP_SERVER, callId_);
    sendSip(trying);

    char ringing[400];
    snprintf(ringing, sizeof(ringing),
             "SIP/2.0 180 Ringing\r\n"
             "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
             "From: %s\r\n"
             "To: <sip:%s@%s>;tag=%s\r\n"
             "Call-ID: %s\r\n"
             "CSeq: 1 INVITE\r\n"
             "Contact: <sip:%s@%s:%u>\r\n"
             "Content-Length: 0\r\n\r\n",
             localIp_, (unsigned)SIP_LOCAL_PORT, branch_, from, SIP_USERNAME,
             SIP_SERVER, tagLocal_, callId_, SIP_USERNAME, localIp_,
             (unsigned)SIP_LOCAL_PORT);
    sendSip(ringing);
    setState(CALL_RINGING);
    statusLock();
    strncpy(g_status.callerId, remoteUri_, sizeof(g_status.callerId) - 1);
    statusUnlock();
    if (incomingCb_) incomingCb_(remoteUri_);
  } else if (strncmp(msg, "BYE ", 4) == 0) {
    char ok[300];
    snprintf(ok, sizeof(ok),
             "SIP/2.0 200 OK\r\n"
             "Via: SIP/2.0/UDP %s:%u;branch=z9hG4bK%s;rport\r\n"
             "Call-ID: %s\r\n"
             "Content-Length: 0\r\n\r\n",
             localIp_, (unsigned)SIP_LOCAL_PORT, branch_, callId_);
    sendSip(ok);
    g_audio.stopCallAudio();
    setState(CALL_ENDED);
    setState(CALL_IDLE);
  } else if (strncmp(msg, "ACK ", 4) == 0) {
    // call already active after 200 OK
  }
}

void SipClient::handleIncomingPacket(const uint8_t* data, size_t len) {
  if (len >= 12 && (data[0] & 0xC0) == 0x80 && state_ == CALL_IN_CALL) {
    // Heuristic: RTP if version=2 and not ASCII SIP
    if (data[0] != 'S' && data[0] != 'I' && data[0] != 'B' && data[0] != 'A' &&
        data[0] != 'C' && data[0] != 'O') {
      handleRtp(data, len);
      return;
    }
  }
  if (len > 8 && (data[0] == 'S' || data[0] == 'I' || data[0] == 'B' ||
                  data[0] == 'A' || data[0] == 'C' || data[0] == 'N' ||
                  data[0] == 'O' || data[0] == 'R')) {
    char* tmp = (char*)malloc(len + 1);
    if (!tmp) return;
    memcpy(tmp, data, len);
    tmp[len] = 0;
    handleSipMessage(tmp, len);
    free(tmp);
  }
}

void SipClient::loop() {
  statusLock();
  if (g_status.ipAddr[0]) strncpy(localIp_, g_status.ipAddr, sizeof(localIp_) - 1);
  if (state_ == CALL_IN_CALL && callStartMs_) {
    g_status.callSeconds = (millis() - callStartMs_) / 1000;
  }
  statusUnlock();

  // Re-register while registered; also retry if registration was lost
  if (registered_ && (millis() - lastRegisterMs_ >
                      (registerExpires_ * 1000UL * 3 / 4))) {
    registerAccount();
  } else if (!registered_ && lastRegisterMs_ != 0 &&
             (millis() - lastRegisterMs_ > 30000UL)) {
    Serial.println("[SIP] reconnect register...");
    registerAccount();
  } else if (!registered_ && lastRegisterMs_ == 0 &&
             (millis() > 45000UL)) {
    // never registered successfully — keep trying slowly
    static uint32_t lastTry = 0;
    if (millis() - lastTry > 45000UL) {
      lastTry = millis();
      registerAccount();
    }
  }

  uint8_t buf[1600];
  int n;
  while ((n = g_modem.udpAvailable(sipLink_)) > 0) {
    int got = g_modem.udpRead(sipLink_, buf, sizeof(buf));
    if (got > 0) handleIncomingPacket(buf, (size_t)got);
  }
  // RTP may arrive on same URC path depending on modem multiplexing
  while ((n = g_modem.udpAvailable(rtpLink_)) > 0) {
    int got = g_modem.udpRead(rtpLink_, buf, sizeof(buf));
    if (got > 0) handleIncomingPacket(buf, (size_t)got);
  }

  processAudio();
}
