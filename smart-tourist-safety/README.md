# Smart Tourist Safety Monitoring & Incident Response System

A real-time tourist safety platform with Android mobile app, web control room dashboard, and Firebase backend.

---

## Project Structure

```
smart-tourist-safety/
 android-app/
    app/src/main/
       java/com/tourist/safety/
          MainActivity.kt          # UI + permission handling
          LocationTrackingService.kt # Foreground GPS service
          FirebaseRepository.kt    # All Firebase writes
          GeofenceManager.kt       # Danger zone detection
          AnomalyDetector.kt       # Behavioral anomaly logic
          DemoSimulator.kt         # Multi-tourist simulation
          TouristPreferences.kt    # Persistent UUID storage
          Models.kt               # Data classes
       res/layout/activity_main.xml
       AndroidManifest.xml
    build.gradle
    settings.gradle
 web-dashboard/
    index.html    # Control room UI
    style.css     # Dark theme styles
    app.js        # Firebase listeners + Leaflet map
 firebase-rules.json
 README.md
```

---

## Firebase Setup (Required First)

1. Go to https://console.firebase.google.com  Create project
2. Enable Realtime Database  Start in test mode
3. Go to Database  Rules  paste contents of `firebase-rules.json`
4. Note your database URL: `https://YOUR_PROJECT-default-rtdb.firebaseio.com`

### Android
1. Project Settings  Add Android App  package: `com.tourist.safety`
2. Download `google-services.json`  place in `android-app/app/`

### Web Dashboard
1. Project Settings  Add Web App
2. Copy the config object
3. Open `web-dashboard/app.js`  replace the `firebaseConfig` object at the top

---

## Android App Setup

Requirements: Android Studio, SDK 24+, Google Play Services

```
1. Open android-app/ in Android Studio
2. Place google-services.json in app/
3. File > Sync Project with Gradle Files
4. Run on device or emulator
```

Permissions granted at runtime: ACCESS_FINE_LOCATION, FOREGROUND_SERVICE

---

## Web Dashboard Setup

Option A - Open directly:
```
Open web-dashboard/index.html in Chrome/Firefox
```

Option B - Local server (recommended for Firebase module imports):
```bash
npx serve web-dashboard
# or
python -m http.server 8080 --directory web-dashboard
```

---

## Firebase Database Structure

```
Tourists/{touristId}
  createdAt: 1710000000000
  status: "SAFE" | "DANGER" | "SOS"

LiveLocation/{touristId}
  latitude: 3.13900
  longitude: 101.68690
  time: 1710000000000
  status: "SAFE"

LocationHistory/{touristId}/{pushId}
  latitude: 3.13900
  longitude: 101.68690
  time: 1710000000000

SOS/{touristId}
  latitude: 3.13900
  longitude: 101.68690
  time: 1710000000000
  status: "ACTIVE"

Alerts/{alertId}
  touristId: "TOURIST_ABC12345"
  type: "GEOFENCE" | "ANOMALY_STATIONARY" | "ANOMALY_SPEED" | "SOS"
  risk: "HIGH" | "MEDIUM" | "LOW"
  latitude: 3.13900
  longitude: 101.68690
  time: 1710000000000
```

---

## System Architecture

```
[Android App]
    |-- TouristPreferences  -> generates/stores UUID
    |-- LocationTrackingService (Foreground) -> GPS every 5s
    |       |-- GeofenceManager  -> checks danger zones (Haversine)
    |       |-- AnomalyDetector  -> speed + stationary checks
    |       |-- FirebaseRepository -> writes LiveLocation, History, Alerts
    |-- DemoSimulator -> simulates 5 tourists for testing
    |-- MainActivity  -> UI, SOS button, permissions

[Firebase Realtime Database]
    Tourists / LiveLocation / LocationHistory / SOS / Alerts

[Web Dashboard]
    |-- app.js
    |       |-- Firebase onValue listeners (real-time)
    |       |-- Leaflet map with tourist markers
    |       |-- Danger zone circles on map
    |       |-- Tourist cards (sorted by severity)
    |       |-- SOS / Danger / Anomaly alert panels
    |       |-- Route history modal with polyline
```

---

## Safety Intelligence

Geofencing (on-device + dashboard):
- 3 predefined danger zones around Kuala Lumpur (configurable in GeofenceManager.kt)
- Haversine formula for accurate distance calculation
- Alert cooldown: 5 minutes per zone to prevent spam

Anomaly Detection:
- Stationary: tourist not moving >10m for 10 minutes  LOW risk alert
- Speed: movement >30 m/s (~108 km/h)  MEDIUM risk alert

---

## Demo Mode

Tap "Start Demo Mode" in the Android app to simulate 5 tourists:
- Sends location updates every 3 seconds
- Generates realistic random movement
- Automatically triggers SOS every 90 seconds (auto-clears after 10s)
- Triggers geofence alerts when simulated tourists enter danger zones

---

## Fault Tolerance

- Firebase offline persistence enabled (setPersistenceEnabled)
- Foreground service survives app backgrounding
- GPS errors caught with try/catch, service stops gracefully
- Alert cooldown prevents duplicate Firebase writes
- Auto-reconnect handled by Firebase SDK

---

## Expanding the System

- Add authentication: Firebase Auth + restrict database rules by UID
- More danger zones: add entries to GeofenceManager.dangerZones list
- Push notifications: integrate Firebase Cloud Messaging
- AI anomaly detection: replace AnomalyDetector with ML Kit
- Multi-city: add city field to Tourist model and filter in dashboard
