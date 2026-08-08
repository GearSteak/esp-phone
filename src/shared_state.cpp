#include "shared_state.h"

PhoneStatus g_status = {};
SemaphoreHandle_t g_statusMutex = nullptr;

void statusLock() {
  if (g_statusMutex) xSemaphoreTake(g_statusMutex, portMAX_DELAY);
}

void statusUnlock() {
  if (g_statusMutex) xSemaphoreGive(g_statusMutex);
}

void statusUpdate(void (*fn)(PhoneStatus&)) {
  statusLock();
  fn(g_status);
  statusUnlock();
}
