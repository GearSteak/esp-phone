#pragma once

#include "Config.h"
#include <functional>

using SipIncomingCb = std::function<void(const char* from)>;
using SipStateCb = std::function<void(CallState state)>;

class SipClient {
 public:
  bool begin();
  void loop();  // call frequently from modem/SIP task

  bool registerAccount();
  bool unregister();
  bool isRegistered() const { return registered_; }

  bool dial(const char* numberOrUri);
  bool answer();
  bool hangup();
  bool sendDtmf(char digit);

  void onIncoming(SipIncomingCb cb) { incomingCb_ = cb; }
  void onState(SipStateCb cb) { stateCb_ = cb; }

  CallState state() const { return state_; }
  const char* remoteUri() const { return remoteUri_; }

 private:
  bool registered_ = false;
  CallState state_ = CALL_IDLE;
  uint32_t cseq_ = 1;
  uint32_t callStartMs_ = 0;
  char callId_[48] = {0};
  char tagLocal_[16] = {0};
  char tagRemote_[32] = {0};
  char branch_[32] = {0};
  char remoteUri_[96] = {0};
  char remoteContact_[128] = {0};
  char localIp_[32] = "0.0.0.0";
  uint16_t remoteRtpPort_ = 0;
  char remoteRtpHost_[64] = {0};
  uint16_t rtpSeq_ = 0;
  uint32_t rtpTs_ = 0;
  uint32_t rtpSsrc_ = 0xE53253C0u;
  int sipLink_ = 0;
  int rtpLink_ = 1;
  uint32_t lastRegisterMs_ = 0;
  uint32_t registerExpires_ = SIP_REGISTER_EXPIRES;
  SipIncomingCb incomingCb_;
  SipStateCb stateCb_;

  void setState(CallState s);
  void makeIds();
  bool sendSip(const char* msg);
  void handleIncomingPacket(const uint8_t* data, size_t len);
  void handleSipMessage(const char* msg, size_t len);
  void handleRtp(const uint8_t* data, size_t len);
  void sendRtpFrame();
  void processAudio();
  bool buildRegister(char* buf, size_t len, bool withAuth, const char* realm,
                     const char* nonce);
  bool buildInvite(char* buf, size_t len, const char* target);
  bool buildBye(char* buf, size_t len);
  bool buildAck(char* buf, size_t len);
  bool buildOkInvite(char* buf, size_t len);
  bool buildTrying(char* buf, size_t len);
  bool buildRinging(char* buf, size_t len);
  void parseViaFromTo(const char* msg);
  bool extractHeader(const char* msg, const char* name, char* out, size_t outLen);
  bool extractSdpMedia(const char* msg);
  static void md5Hex(const char* data, char out[33]);
  bool computeAuthResponse(const char* method, const char* uri, const char* realm,
                           const char* nonce, char outResp[33]);
};

extern SipClient g_sip;
