#include <ArduinoJson.h>
#include <WiFi.h>
#include <WebServer.h>
#include <EEPROM.h>                                   

String disText;                                           ////////////  bu dastur sammoykalar uchun 2-esp32 dasturi, bu dastur web sahifani va 7 ta releni boshqarish uchun moljallangan.
int time_number;
int value;
int pul, count, minut, sekunt, button_number, LOOPnum;
long total_sum;
byte safetotal;
int Pause = 240;
const long oraliqVaqt = 1000; 
unsigned long oxringiVaqt = 0; 

const int inputPins[] = {15, 2, 4, 5, 18, 19, 21, 35, 34, 32};  // Kirish pinlari, 32 qo'shildi
const int outpin[] = {23, 22, 13, 33, 25, 26, 27, 14};
const int numPins = sizeof(inputPins) / sizeof(inputPins[0]); // Pinlar soni

int lastButtonState[numPins];     // Oxirgi o'qilgan tugma holati
unsigned long lastDebounceTime[numPins];  // Oxirgi debounce vaqti
const long debounceDelay = 70; 
unsigned long lastDebounceTime2 = 0;

#define NUM_PRODUCTS 10
#define EEPROM_SIZE 2048

char ssid[33] = "mecanuz";  // O'zgaruvchi ssid va password
char password[33] = "12072020";
int custom_number = 1;  // Admin2 sahifasidan kiritilgan raqam (int o'zgaruvchi)
int bonusLimit = 0;     // "Bonus limit" inputdan kiritilgan qiymat (int o'zgaruvchi)

const char* default_ssid = "mecanuz";
const char* default_password = "12072020";
const int default_custom_number = 1;

const char* admin_password1 = "qwerty";  // 1-parol: Mahsulotlar sahifasi
const char* admin_password2 = "simsim";  // 2-parol: WiFi sozlamalari sahifasi

String productNames[NUM_PRODUCTS];
int productPrices[NUM_PRODUCTS];

WebServer server(80);

/* ======================= EEPROM manzillari ====================== */
// Har mahsulot: 20 nom + 2 narx = 22 bayt -> 22 * 10 = 220 bayt
// Keyin 4 bayt total_sum
#define TOTAL_SUM_ADDR (NUM_PRODUCTS * 22)   // 220

// Yangi: SSID (32+1 bayt), Password (32+1 bayt), custom_number (2 bayt), bonusLimit (2 bayt)
#define SSID_ADDR (TOTAL_SUM_ADDR + 4)        // 224
#define PASSWORD_ADDR (SSID_ADDR + 33)        // 257
#define CUSTOM_NUMBER_ADDR (PASSWORD_ADDR + 33)  // 290
#define BONUS_LIMIT_ADDR (CUSTOM_NUMBER_ADDR + 2) // 292

void saveTotalToEEPROM() {
  uint32_t ts = (uint32_t) total_sum;   // long -> 32-bit
  int addr = TOTAL_SUM_ADDR;
  EEPROM.write(addr++, (ts >> 24) & 0xFF);
  EEPROM.write(addr++, (ts >> 16) & 0xFF);
  EEPROM.write(addr++, (ts >> 8)  & 0xFF);
  EEPROM.write(addr++,  ts        & 0xFF);
  EEPROM.commit();
}

void saveWifiSettingsToEEPROM() {
  int addr = SSID_ADDR;
  for (int i = 0; i < 32; i++) {
    EEPROM.write(addr++, ssid[i]);
  }
  EEPROM.write(addr++, 0);  // Null terminator

  addr = PASSWORD_ADDR;
  for (int i = 0; i < 32; i++) {
    EEPROM.write(addr++, password[i]);
  }
  EEPROM.write(addr++, 0);  // Null terminator

  addr = CUSTOM_NUMBER_ADDR;
  EEPROM.write(addr++, (custom_number >> 8) & 0xFF);
  EEPROM.write(addr++, custom_number & 0xFF);

  EEPROM.commit();
}

void loadWifiSettingsFromEEPROM() {
  int addr = SSID_ADDR;
  for (int i = 0; i < 33; i++) {
    ssid[i] = EEPROM.read(addr++);
  }

  addr = PASSWORD_ADDR;
  for (int i = 0; i < 33; i++) {
    password[i] = EEPROM.read(addr++);
  }

  addr = CUSTOM_NUMBER_ADDR;
  int highByte = EEPROM.read(addr++);
  int lowByte = EEPROM.read(addr++);
  custom_number = (highByte << 8) | lowByte;
}

/* ======================= Bonus Limit EEPROM ====================== */
void saveBonusLimitToEEPROM() {
  int addr = BONUS_LIMIT_ADDR;
  EEPROM.write(addr++, (bonusLimit >> 8) & 0xFF);
  EEPROM.write(addr++, bonusLimit & 0xFF);
  EEPROM.commit();
}

void loadBonusLimitFromEEPROM() {
  int addr = BONUS_LIMIT_ADDR;
  int highByte = EEPROM.read(addr++);
  int lowByte = EEPROM.read(addr++);
  bonusLimit = (highByte << 8) | lowByte;
}
/* ====================================================================== */

void resetToDefaultWifiSettings() {
  strcpy(ssid, default_ssid);
  strcpy(password, default_password);
  custom_number = default_custom_number;
  saveWifiSettingsToEEPROM();
  ESP.restart();  // Qayta ishga tushirish WiFi ni yangilash uchun
}

void saveToEEPROM() {
  int addr = 0;
  for (int i = 0; i < NUM_PRODUCTS; i++) {
    for (int j = 0; j < 20; j++) {
      char c = (j < productNames[i].length()) ? productNames[i][j] : 0;
      EEPROM.write(addr++, c);
    }
    EEPROM.write(addr++, (productPrices[i] >> 8) & 0xFF);
    EEPROM.write(addr++, productPrices[i] & 0xFF);
  }
  EEPROM.commit();
}

void loadFromEEPROM() {
  int addr = 0;
  for (int i = 0; i < NUM_PRODUCTS; i++) {
    char name[21];
    for (int j = 0; j < 20; j++) {
      name[j] = EEPROM.read(addr++);
    }
    name[20] = '\0';
    productNames[i] = String(name);
    int highByte = EEPROM.read(addr++);
    int lowByte = EEPROM.read(addr++);
    productPrices[i] = (highByte << 8) | lowByte;
  }

  // ===== total_sum ni 4 baytda o‘qish =====
  uint32_t ts = 0;
  ts  = ((uint32_t)EEPROM.read(TOTAL_SUM_ADDR    ) << 24);
  ts |= ((uint32_t)EEPROM.read(TOTAL_SUM_ADDR + 1) << 16);
  ts |= ((uint32_t)EEPROM.read(TOTAL_SUM_ADDR + 2) << 8);
  ts |= ((uint32_t)EEPROM.read(TOTAL_SUM_ADDR + 3));
  total_sum = (long)ts;
}

String generateLoginForm() {
  String html = R"====(
  <!DOCTYPE html><html><head><meta charset="UTF-8">
  <title>Login</title>
  <style>
    body { font-family: Arial; background-color: #f0f0f0; padding: 20px; }
    h2 { text-align: center; }
    .container {
      max-width: 400px;
      margin: auto;
      background: #fff;
      padding: 20px;
      border-radius: 12px;
      box-shadow: 0 0 10px rgba(0,0,0,0.1);
    }
    input[type="password"] {
      width: 100%;
      padding: 8px;
      margin: 6px 0 12px;
      border: 1px solid #ccc;
      border-radius: 6px;
    }
    input[type="submit"] {
      width: 100%;
      background: #4CAF50;
      color: white;
      padding: 12px;
      border: none;
      border-radius: 8px;
      cursor: pointer;
    }
    input[type="submit"]:hover { background-color: #45a049; }
  </style>
  </head><body><h2>Parolni kiriting</h2>
  <form method='POST' action='/login' class='container'>
    <label>Parol:</label><br>
    <input type='password' name='pass' required><br>
    <input type='submit' value='Kirish'>
  </form></body></html>
  )====";
  return html;
}

void handleLoginPage() {
  server.send(200, "text/html", generateLoginForm());
}

void handleLogin() {
  String pass = server.arg("pass");
  if (pass == admin_password1) {
    handleRoot();  // 1-parol: Mahsulotlar sahifasi
  } else if (pass == admin_password2) {
    handleWifiSettings();  // 2-parol: WiFi sozlamalari sahifasi
  } else {
    server.send(200, "text/html", "<html><body><h2>Xato parol!</h2><a href='/'>Ortga</a></body></html>");
  }
}

String generateForm() {
  String html = R"====(
  <!DOCTYPE html><html><head><meta charset="UTF-8">
  <title>Mahsulotlar</title>
  <style>
    body { font-family: Arial; background-color: #f0f0f0; padding: 20px; }
    h2 { text-align: center; }
    .container {
      display: flex;
      flex-direction: column;
      gap: 20px;
      max-width: 500px;
      margin: auto;
    }
    .card {
      background: #fff;
      padding: 20px;
      border-radius: 12px;
      box-shadow: 0 0 10px rgba(0,0,0,0.1);
    }
    input[type="text"], input[type="number"] {
      width: 100%;
      padding: 8px;
      margin: 6px 0 12px;
      border: 1px solid #ccc;
      border-radius: 6px;
    }
    input[type="submit"] {
      margin: 20px auto;
      display: block;
      background: #4CAF50;
      color: white;
      padding: 12px 24px;
      border: none;
      border-radius: 8px;
      cursor: pointer;
    }
    input[type="submit"]:hover { background-color: #45a049; }
    .row { display:flex; gap:12px; align-items:center; justify-content:space-between; }
    .linkbar { text-align:center; margin-top:10px; }
    a.btn { display:inline-block; padding:8px 14px; border-radius:8px; background:#1976d2; color:#fff; text-decoration:none; }
    a.btn:hover { background:#135ca6; }
  </style>
  </head><body><h2>Mahsulotlar va narxlarni 5000 so‘mga nisbatan kiriting</h2>
  <div class='linkbar'>
    <a class='btn' href='/stats'>📊 Hisobot / Stats</a>
  </div>
  <form method='POST' action='/save'><div class='container'>
  )====";

  // ====== Umumiy tushum kartasi ======
  html += "<div class='card'>";
  html += "<h3>Umumiy tushum:</h3>";
  html += "<div style='font-size:22px; font-weight:700;'>";
  html += String((unsigned long)total_sum);
  html += " so'm</div>";
  html += "<div class='row' style='margin-top:12px'>";
  html += "<a class='btn' href='/stats'>Ko‘rish</a>";
  html += "</div>";
  html += "</div>";

  for (int i = 0; i < NUM_PRODUCTS; i++) {
    html += "<div class='card'>";
    html += "<label>Mahsulot " + String(i + 1) + ":</label><br>";

    if (i == 0) {
      html += "<input type='text' name='name" + String(i) + "' value='" + productNames[i] + "'><br>";
      html += "<label>%Bonus:</label><br>";
      html += "<input type='number' name='price" + String(i) + "' value='" + String(productPrices[i]) + "'><br>";
      html += "<label>Bonus limit:</label><br>";
      html += "<input type='number' name='bonus_limit' value='" + String(bonusLimit) + "'><br>";
    } else if (i == NUM_PRODUCTS - 1) {
      html += "<input type='text' name='name" + String(i) + "' value='PAUSE' readonly><br>";
      html += "<label>Narxi:</label><br>";
      html += "<input type='number' name='price" + String(i) + "' value='" + String(productPrices[i]) + "'><br>";
    } else {
      html += "<input type='text' name='name" + String(i) + "' value='" + productNames[i] + "'><br>";
      html += "<label>Narxi:</label><br>";
      html += "<input type='number' name='price" + String(i) + "' value='" + String(productPrices[i]) + "'><br>";
    }

    html += "</div>";
  }

  html += R"====(
      </div><input type='submit' value='Saqlash'>
    </form></body></html>
  )====";

  return html;
}

String generateWifiSettingsForm() {
  String html = R"====(
  <!DOCTYPE html><html><head><meta charset="UTF-8">
  <title>WiFi Sozlamalari</title>
  <style>
    body { font-family: Arial; background-color: #f0f0f0; padding: 20px; }
    h2 { text-align: center; }
    .container {
      max-width: 400px;
      margin: auto;
      background: #fff;
      padding: 20px;
      border-radius: 12px;
      box-shadow: 0 0 10px rgba(0,0,0,0.1);
    }
    input[type="text"], input[type="password"], input[type="number"] {
      width: 100%;
      padding: 8px;
      margin: 6px 0 12px;
      border: 1px solid #ccc;
      border-radius: 6px;
    }
    input[type="submit"] {
      width: 100%;
      background: #4CAF50;
      color: white;
      padding: 12px;
      border: none;
      border-radius: 8px;
      cursor: pointer;
    }
    input[type="submit"]:hover { background-color: #45a049; }
  </style>
  </head><body><h2>WiFi SSID va Passwordni o'zgartiring</h2>
  <form method='POST' action='/save_wifi' class='container'>
    <label>SSID:</label><br>
    <input type='text' name='ssid' value=')====" + String(ssid) + R"====(' required><br>
    <label>Password:</label><br>
    <input type='password' name='pass' value=')====" + String(password) + R"====(' required><br>
    <label>Raqam (standart 1):</label><br>
    <input type='number' name='custom_num' value=')====" + String(custom_number) + R"====(' required><br>
    <input type='submit' value='Saqlash'>
  </form></body></html>
  )====";
  return html;
}

void handleRoot() {
  server.send(200, "text/html", generateForm());
}

void handleWifiSettings() {
  server.send(200, "text/html", generateWifiSettingsForm());
}

void handleSave() {
  for (int i = 0; i < NUM_PRODUCTS; i++) {
    if (i == 0) {
      productNames[i] = server.arg("name" + String(i));
      productPrices[i] = server.arg("price" + String(i)).toInt();
    } else if (i == NUM_PRODUCTS - 1) {
      productNames[i] = "PAUSE";
      productPrices[i] = server.arg("price" + String(i)).toInt();
    } else {
      productNames[i] = server.arg("name" + String(i));
      productPrices[i] = server.arg("price" + String(i)).toInt();
    }
  }

  bonusLimit = server.arg("bonus_limit").toInt();   // "Bonus limit" inputdan int ga saqlash
  saveBonusLimitToEEPROM();

  saveToEEPROM();
  server.send(200, "text/html", "<html><body><h2>✅ Ma’lumotlar saqlandi!</h2><a href='/'>🔙 Ortga</a></body></html>");
}

void handleSaveWifi() {
  String new_ssid = server.arg("ssid");
  String new_pass = server.arg("pass");
  custom_number = server.arg("custom_num").toInt();   // Admin2 sahifasidagi raqamni int ga saqlash

  if (new_ssid.length() > 0 && new_ssid.length() <= 32 && new_pass.length() >= 8 && new_pass.length() <= 32) {
    strcpy(ssid, new_ssid.c_str());
    strcpy(password, new_pass.c_str());
    saveWifiSettingsToEEPROM();
    server.send(200, "text/html", "<html><body><h2>✅ Sozlamalar saqlandi! Tizim qayta yuklanadi.</h2></body></html>");
    delay(1000);
    ESP.restart();
  } else {
    server.send(200, "text/html", "<html><body><h2>Xato: SSID (1-32 harf), Password (8-32 harf)!</h2><a href='/wifi_settings'>Ortga</a></body></html>");
  }
}

void handleStats() {
  String page = R"====(
    <!DOCTYPE html><html><head><meta charset="UTF-8"><title>Stats</title>
    <style>
      body { font-family: Arial; background:#f0f0f0; padding:20px; }
      .card { background:#fff; padding:20px; border-radius:12px; box-shadow:0 0 10px rgba(0,0,0,.1); max-width:520px; margin:auto; }
      .row { display:flex; gap:12px; align-items:center; justify-content:space-between; margin-top:14px;}
      a.btn, button { display:inline-block; padding:10px 16px; border-radius:8px; background:#1976d2; color:#fff; border:none; text-decoration:none; cursor:pointer; }
      a.btn:hover, button:hover { background:#135ca6; }
      .warn { background:#c62828; }
      .warn:hover { background:#8e1d1d; }
      .big { font-size:24px; font-weight:700; }
    </style></head><body>
    <div class='card'>
      <h2>📊 Hisobot (Umumiy tushum)</h2>
  )====";
  page += "<div class='big'>" + String((unsigned long)total_sum) + " so'm</div>";
  page += R"====(
      <div class='row'>
        <a class='btn' href='/'>⬅️ Ortga</a>
        <form method='POST' action='/reset_total' onsubmit="return confirm('Rostdan ham umumiy tushumni 0 qilamizmi?');">
          <button type='submit' class='warn'>♻️ Reset</button>
        </form>
      </div>
    </div></body></html>
  )====";
  server.send(200, "text/html", page);
}

void handleResetTotal() {
  total_sum = 0;
  saveTotalToEEPROM();  // darhol saqlaymiz
  server.send(200, "text/html", "<html><body><h2>♻️ Umumiy tushum 0 qilindi.</h2><a href='/stats'>⬅️ Ortga</a></body></html>");
}

void setup() {
  Serial.begin(115200);
  EEPROM.begin(EEPROM_SIZE);

  loadFromEEPROM();
  loadWifiSettingsFromEEPROM();
  loadBonusLimitFromEEPROM();   

  WiFi.softAP(ssid, password);
  Serial.println("WiFi AP: " + WiFi.softAPIP().toString());

  server.on("/", handleLoginPage);
  server.on("/login", HTTP_POST, handleLogin);
  server.on("/save", HTTP_POST, handleSave);
  server.on("/stats", handleStats);
  server.on("/reset_total", HTTP_POST, handleResetTotal);
  server.on("/wifi_settings", handleWifiSettings);  
  server.on("/save_wifi", HTTP_POST, handleSaveWifi);  

  server.begin();
  Serial.println("Server ishga tushdi!");
  Serial.println("2-esp 8x relay uchun");

  for (int i = 0; i < numPins; i++) {
    pinMode(inputPins[i], INPUT);  
    lastDebounceTime[i] = 0;
    lastButtonState[i] = digitalRead(inputPins[i]);  
  }

  pinMode(23, OUTPUT);   //suv
  pinMode(22, OUTPUT);     // pena
  pinMode(13, OUTPUT);     // A pena
  pinMode(33, OUTPUT);    /// nano
  pinMode(25, OUTPUT);    // Vosk
  pinMode(26, OUTPUT);  
  pinMode(27, OUTPUT);  
  pinMode(14, OUTPUT); 

  for (int pin : {23, 22, 13, 33, 25, 26, 27, 14}) {
    digitalWrite(pin, LOW);
  }

  delay(2000);
}

unsigned long buttonPressTime = 0;
bool buttonPressed = false;

void loop() {

  // 32 pin ni tekshirish
  int reading32 = digitalRead(32);
  if (reading32 != lastButtonState[9]) {  
    lastDebounceTime[9] = millis();
  }

  if ((millis() - lastDebounceTime[9]) > debounceDelay) {
    if (reading32 == HIGH) {
      if (!buttonPressed) {
        buttonPressTime = millis();
        buttonPressed = true;
      }
    } else {
      if (buttonPressed) {
        unsigned long holdTime = millis() - buttonPressTime;
        if (holdTime > 5000) {
          resetToDefaultWifiSettings();
        } else if (holdTime > 2000) {
          pul = 0;
          resetSystem();
        }
        buttonPressed = false;
      }
    }
  }
  lastButtonState[9] = reading32;

  if (pul > value) {
    button_rele();
    time_number = pul; 
    if (LOOPnum) {
      disText = "SUM";
      StaticJsonDocument<200> doc;
      doc["number"] = time_number;
      doc["Text"] = disText;
      String jsonData;
      serializeJson(doc, jsonData);
      Serial.println(jsonData);
      LOOPnum = 0;
    }  
  } else {
    resetSystem();
  }

  if (Serial.available() > 0) {
    if (Serial.read() == 0) {
      count++;
      pul = count * 1000;
      LOOPnum = 1;
    }
    if (pul > 101000) {
      pul = 0;
    }
    if (pul >= bonusLimit) {
    pul += (pul/100)*productPrices[0];
    }
  }

  while(pul >= value && button_number > 0) {
    count = 0;
    button_rele();
    unsigned long currentMillis = millis();

    if (safetotal == true) {
      total_sum = total_sum + pul;          
      saveTotalToEEPROM();                  
      safetotal = false;
    }
   
    if (button_number < 10) {
      if (currentMillis - oxringiVaqt >= oraliqVaqt) {
        oxringiVaqt = currentMillis;
        pul -= value;
        minut = (pul / value) / 60;
        sekunt = (pul / value) % 60;
        time_number = (minut * 100) + sekunt;

        StaticJsonDocument<200> doc;
        doc["number"] = time_number;
        doc["Text"] = disText;
        String jsonData;
        serializeJson(doc, jsonData);
        Serial.println(jsonData);
      }
    } else {
      if (value > 0) {
        if (currentMillis - oxringiVaqt >= oraliqVaqt) {
          oxringiVaqt = currentMillis;
          value -= 1;
          minut = value / 60;
          sekunt = value % 60;
          time_number = (minut * 100) + sekunt;

          StaticJsonDocument<200> doc;
          doc["number"] = time_number;
          doc["Text"] = disText;
          String jsonData;
          serializeJson(doc, jsonData);
          Serial.println(jsonData);
        }
      } else {
        if (currentMillis - oxringiVaqt >= oraliqVaqt) {
          oxringiVaqt = currentMillis;
          pul -= 50;
          disText = "PULLI VAQT";
          minut = (pul / 50) / 60;
          sekunt = (pul / 50) % 60;
          time_number = (minut * 100) + sekunt;

          StaticJsonDocument<200> doc;
          doc["number"] = time_number;
          doc["Text"] = disText;
          String jsonData;
          serializeJson(doc, jsonData);
          Serial.println(jsonData);
        }
      }
    }
  }
}

void button_rele() {
  for (int i = 0; i < numPins - 1; i++) {  
    int reading = digitalRead(inputPins[i]);  
    
    if (reading != lastButtonState[i]) {
      lastDebounceTime[i] = millis();
    }
    
    if ((millis() - lastDebounceTime[i]) > debounceDelay) {
      if (reading == HIGH) {  

        if (inputPins[i] == 15) {
          button_number = 1;
          value = 5000/productPrices[1];
          disText = productNames[1];
          setRelay(23);
          delay(100);

        } else if(inputPins[i] == 2){
          button_number = 2;
          value = 5000/productPrices[2];
          disText = productNames[2];
          setRelay(22);
          delay(100);

        } else if(inputPins[i] == 4){
          button_number = 3;
          value = 5000/productPrices[3];
          disText = productNames[3];
          setRelay(13);
          delay(100);

        } else if(inputPins[i] == 5){
          button_number = 4;
          value = 5000/productPrices[4];
          disText = productNames[4];
          setRelay(33);
          delay(100);

        } else if(inputPins[i] == 18){
          button_number = 5;
          value = 5000/productPrices[5];
          disText = productNames[5];
          setRelay(25);
          delay(100);

        } else if(inputPins[i] == 34){
          button_number = 10;
          value = productPrices[9];
          disText = "PAUSE";
          digitalWrite(23, 0);
          digitalWrite(22, 0);
          digitalWrite(13, 0);
          digitalWrite(33, 0);
          digitalWrite(25, 0);
          digitalWrite(26, 0);
          digitalWrite(27, 0);
          digitalWrite(14, 0);
          delay(100);
          
        } else if (inputPins[i] == 19) {
          button_number = 6;
          value = 5000/productPrices[6];
          disText = productNames[6];
          setRelay(26);
          delay(100);

        } else if (inputPins[i] == 21) {
          button_number = 7;
          value = 5000/productPrices[7];
          disText = productNames[7];
          setRelay(27);
          delay(100);

        } else if (inputPins[i] == 35) {
          button_number = 7;
          value = 5000/productPrices[8];
          disText = productNames[8];
          setRelay(14);
          delay(100);
        }     
      }
    } 
    lastButtonState[i] = reading;            
  }
}

void resetSystem() {
  for (int pin : {23, 22, 13, 33, 25, 26, 27, 14}) {
    digitalWrite(pin, LOW);
  }
  button_number = 0;
  pul = 0;
  value = 0;
  count = 0;
  safetotal = true;
  disText = productNames[0];
  time_number = 0;

  server.handleClient();

  StaticJsonDocument<200> doc;
  doc["number"] = time_number;
  doc["Text"] = disText;
  String jsonData;
  serializeJson(doc, jsonData);
  Serial.println(jsonData);
  delay(200);
}

void setRelay(int relayPin) {
  for (int pin : {14, 27, 26, 25, 33, 22, 13, 23}) {
    digitalWrite(pin, LOW);
  }
  digitalWrite(relayPin, HIGH);
  digitalWrite(outpin[custom_number-1], HIGH);
}