#pragma once

#include "Config.h"
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

extern PhoneStatus g_status;
extern SemaphoreHandle_t g_statusMutex;

void statusLock();
void statusUnlock();
void statusUpdate(void (*fn)(PhoneStatus&));
