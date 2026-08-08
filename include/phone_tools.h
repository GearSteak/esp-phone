#pragma once

#include <stddef.h>
#include <stdint.h>

// Simple calculator expression: digits + - * / . and =
// Returns false on divide-by-zero / overflow / syntax.
bool calcEval(const char* expr, double& out);

// Unit / currency tables (offline). category: 0=length 1=mass 2=temp 3=currency
const char* converterCategoryName(int cat);
int converterCategoryCount();
int converterUnitCount(int cat);
const char* converterUnitName(int cat, int unit);
bool converterConvert(int cat, int from, int to, double value, double& out);

const char* weatherCodeText(int code);
bool weatherFetchOpenMeteo(double lat, double lon);

void connectivityApplyFromSettings();
void connectivitySetHotspot(bool on);
void connectivitySetBluetooth(bool on);
bool connectivityHotspotOn();
bool connectivityBluetoothOn();
