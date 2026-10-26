# Implementation Plan: Smart Tourist Safety Monitoring & Incident Response System — Maharashtra

## Overview

Tasks are sequenced by dependency: blockchain contract first (identity anchor), then Python backend (API + services), then Android app (mobile client), then web dashboard (authority UI), with integration wiring at the end. Property-based tests (hypothesis / kotest) are placed as optional sub-tasks immediately after the code they validate.

---

## Tasks

- [x] 1. Blockchain — Solidity smart contract
  - [x] 1.1 Create `TouristSafety.sol` with tourist registration functions
    - Implement `registerTourist(bytes32 idHash, uint256 visitStart, uint256 visitEnd)` returning a `tokenId`
    - Implement `expireTourist(uint256 tokenId)` and emit `TouristExpired`
    - Store records in a mapping; mark entries immutable after creation
    - _Requirements: 1.3, 1.4, 1.6, 11.1, 11.5_

  - [x] 1.2 Add SOS and zone-entry functions to `TouristSafety.sol`
    - Implement `recordSosEvent`, `resolveSosEvent`, `recordZoneEntry`, `resolveIncident`
    - Emit `SosCreated`, `SosResolved`, `RestrictedZoneEntered`, `IncidentResolved` events
    - _Requirements: 6.3, 4.6, 8.7, 11.1_

  - [ ]* 1.3 Write property test for blockchain immutability (Property 3)
    - **Property 3: Blockchain immutability — recorded events cannot be modified**
    - **Validates: Requirements 1.6, 11.3**
    - Use hypothesis with a Web3.py mock; generate random event data, write, attempt update/delete, verify rejection

  - [x] 1.4 Write Ganache deployment script and Web3.py client wrapper
    - `blockchain_client.py`: connect to Ganache, deploy contract, expose `register_tourist`, `record_sos_event`, `record_zone_entry`, `resolve_incident`, `verify_tx`
    - _Requirements: 11.2, 11.5_

- [ ] 2. Backend — project scaffold and shared utilities
  - [x] 2.1 Scaffold Flask/FastAPI project structure
    - Create `backend/` with `app.py`, `config.py`, `requirements.txt`
    - Set up middleware stack: TLS config, rate limiter, JWT auth, RBAC check
    - Configure MongoDB connection (pymongo) and Firebase Admin SDK
    - _Requirements: 9.1, 10.2_

  - [x] 2.2 Implement shared data models and validators
    - Python dataclasses / Pydantic models for `TouristRecord`, `LocationUpdate`, `SosEvent`, `Incident`, `GeoFenceZone`, `AnomalyAlert`
    - Aadhaar validator (12-digit numeric) and passport validator (alphanumeric)
    - SHA-256 hashing utility — never returns raw identity value
    - AES-256 encrypt/decrypt helpers for PII fields
    - _Requirements: 1.2, 1.5, 10.1, 10.3_

  - [ ]* 2.3 Write property test for SHA-256 determinism and no raw PII storage (Property 1)
    - **Property 1: SHA-256 hash is deterministic and raw identity is never stored**
    - **Validates: Requirements 1.2, 10.3**

  - [ ]* 2.4 Write property test for PII never stored in plaintext (Property 11)
    - **Property 11: PII is never stored in plaintext**
    - **Validates: Requirements 10.1**

- [ ] 3. Backend — Identity Verifier and registration endpoint
  - [ ] 3.1 Implement `IdentityVerifier` service
    - Format-validate input, SHA-256 hash, check MongoDB for active duplicate (same hash, `visitEnd > now`)
    - Issue UUID v4 `Digital_Tourist_ID`, write to MongoDB, call `blockchain_client.register_tourist` asynchronously
    - Return `{ touristId, validUntil, txHash }` within 10 s; handle blockchain timeout with HTTP 202 + retry
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.7_

  - [ ] 3.2 Wire `POST /api/v1/register` endpoint
    - Route to `identity_controller.register`, apply JWT + RBAC middleware
    - Return HTTP 400 for format errors, HTTP 409 for duplicates, HTTP 200/202 for success
    - _Requirements: 1.1, 1.5, 1.7_

  - [ ]* 3.3 Write property test for duplicate registration rejection (Property 2)
    - **Property 2: Duplicate registration is rejected**
    - **Validates: Requirements 1.7**

- [ ] 4. Backend — Location controller and Firebase writer
  - [ ] 4.1 Implement `LocationController` and `POST /api/v1/location`
    - Validate JWT, decrypt payload, write to `Firebase:/LiveLocation/{touristId}` and `Firebase:/LocationHistory/{touristId}/{pushId}`
    - Write to `MongoDB:location_history` with TTL index (90 days after `visitEnd`)
    - Enqueue location event for Anomaly Detector worker
    - _Requirements: 3.3, 3.6, 10.4_

  - [ ]* 4.2 Write property test for location update latency (Property 4)
    - **Property 4: Location update transmission within latency bound**
    - **Validates: Requirements 3.3**

  - [ ]* 4.3 Write property test for offline buffer round-trip (Property 5)
    - **Property 5: Offline buffer round-trip preserves order and completeness**
    - **Validates: Requirements 3.4, 12.1, 12.2**

- [ ] 5. Backend — Risk Scorer and score endpoint
  - [ ] 5.1 Implement `RiskScorer` service
    - `compute_score(zone_classification, incident_density_30d, current_hour) -> (score: int, label: str)`
    - Apply formula: `base_score - incident_penalty - time_penalty`, clamped to [0, 100]
    - Map score to label: SAFE ≥ 70, CAUTION 40–69, DANGER < 40
    - _Requirements: 5.1, 5.4_

  - [ ] 5.2 Wire `GET /api/v1/score/{touristId}` endpoint
    - Fetch tourist's current zone from Firebase, query incident density from MongoDB, call `RiskScorer`
    - Update `Firebase:/LiveLocation/{touristId}/safetyScore`
    - _Requirements: 5.2, 5.3_

  - [ ]* 5.3 Write property test for safety score bounds and label consistency (Property 7)
    - **Property 7: Safety score is bounded and label is consistent**
    - **Validates: Requirements 5.1, 5.3**

- [ ] 6. Backend — Geo-Fence Engine and zones endpoint
  - [ ] 6.1 Implement `GeoFenceEngine` service
    - Haversine distance check on each location update against zone registry loaded from MongoDB/Firebase
    - Trigger alert when tourist enters HIGH or RESTRICTED zone; write alert to `Firebase:/Alerts/{pushId}`
    - Log RESTRICTED zone entry via `blockchain_client.record_zone_entry` asynchronously
    - Enforce 5-minute cooldown per tourist per zone (in-memory TTL dict or Redis)
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6_

  - [ ] 6.2 Wire `GET /api/v1/zones` endpoint
    - Return active zone list from MongoDB; ADMIN can POST/PATCH zones via `zone_controller`
    - On zone update, write to Firebase `/Zones/{zoneId}` so apps receive propagation within 60 s
    - _Requirements: 13.2, 13.3_

  - [ ]* 6.3 Write property test for geo-fence alert timing and cooldown (Property 6)
    - **Property 6: Geo-fence alert fires within latency bound and respects cooldown**
    - **Validates: Requirements 4.2, 4.5**

  - [ ]* 6.4 Write property test for zone configuration propagation (Property 13)
    - **Property 13: Zone configuration propagates to all active apps within 60 seconds**
    - **Validates: Requirements 13.3**

- [ ] 7. Backend — SOS Handler and SOS endpoint
  - [ ] 7.1 Implement `SosHandler` service
    - Create `SosEvent` record (UUID, touristId, lat/lng, timestamp, status=ACTIVE)
    - Write to `Firebase:/SOS/{touristId}` and MongoDB `incidents`
    - Call `blockchain_client.record_sos_event` asynchronously; store `txHash`
    - Publish high-priority alert to Dashboard via Firebase `/Alerts`
    - Signal `LocationController` to switch to 3 s update interval
    - _Requirements: 6.2, 6.3, 6.4, 6.5_

  - [ ] 7.2 Wire `POST /api/v1/sos` endpoint and SOS resolution
    - `POST /api/v1/sos` → `sos_controller.trigger`; respond within 5 s
    - `PATCH /api/v1/incidents/{id}` with status=RESOLVED → call `blockchain_client.resolve_incident`, notify tourist app
    - _Requirements: 6.2, 6.6, 6.7, 8.7_

  - [ ]* 7.3 Write property test for SOS event completeness and timing (Property 8)
    - **Property 8: SOS event creation is complete and timely**
    - **Validates: Requirements 6.2, 6.3, 6.4**

- [ ] 8. Backend — Anomaly Detector worker
  - [ ] 8.1 Implement `AnomalyDetector` async worker
    - Consume location events from asyncio queue / Celery
    - Apply rule-based checks: stationary (< 10 m in 10 min), abnormal speed (> 30 m/s), GPS loss in HIGH/RESTRICTED (> 5 min), route deviation (> 500 m)
    - Train Isolation Forest on historical movement data; use anomaly score as supplementary signal
    - Write `AnomalyAlert` to Firebase `/Alerts` and MongoDB; send push notification to tourist app
    - Skip analysis if < 3 location points available
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ] 8.2 Implement anomaly escalation scheduler
    - Track unacknowledged alerts; after 5-minute timeout escalate risk level by one step (LOW→MEDIUM, MEDIUM→HIGH)
    - Update alert record in Firebase and MongoDB
    - _Requirements: 7.8_

  - [ ]* 8.3 Write property test for anomaly escalation on non-response (Property 9)
    - **Property 9: Anomaly escalation on non-response**
    - **Validates: Requirements 7.8**

- [ ] 9. Backend — RBAC controller and audit log
  - [ ] 9.1 Implement `RbacController` middleware
    - Decode JWT, extract role claim, check permission matrix for (role, resource, action) tuples
    - On denial: return HTTP 403 and write to MongoDB `audit_log` with userId, resource, timestamp
    - Enforce 8-hour session timeout for AUTHORITY and ADMIN; return HTTP 401 on expiry
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 9.2 Write property test for RBAC denial and audit logging (Property 10)
    - **Property 10: RBAC denies out-of-scope access and logs the attempt**
    - **Validates: Requirements 9.5**

- [ ] 10. Backend — data retention and purge job
  - [ ] 10.1 Implement TTL index on `location_history` collection (90 days after `visitEnd`)
    - Create MongoDB TTL index on `location_history.timestamp` relative to tourist's `visitEnd`
    - Implement `purge_tourist_data(touristId)` for on-demand deletion within 24 h
    - _Requirements: 10.4, 10.5_

  - [ ]* 10.2 Write property test for location history purge after retention period (Property 12)
    - **Property 12: Location history is purged after retention period**
    - **Validates: Requirements 10.4**

- [ ] 11. Checkpoint — backend tests pass
  - Ensure all backend unit tests and property tests pass. Ask the user if questions arise.

- [ ] 12. Android — project setup and shared models
  - [ ] 12.1 Add dependencies to `app/build.gradle`
    - Add Kotest property testing, Room, EncryptedSharedPreferences, FusedLocationProvider, Firebase Realtime DB, Retrofit, WorkManager
    - _Requirements: 2.1, 3.1, 12.1_

  - [ ] 12.2 Implement `Models.kt` data classes
    - `TouristRecord`, `LocationUpdate`, `SosEvent`, `GeoFenceZone`, `AnomalyAlert` matching backend schemas
    - _Requirements: 2.1, 3.1_

  - [ ] 12.3 Implement `TouristPreferences.kt` — EncryptedSharedPreferences wrapper
    - Store/retrieve `Digital_Tourist_ID`, `visitEnd`, JWT token
    - Detect expired ID and return null to trigger re-registration prompt
    - _Requirements: 2.3, 2.4, 2.5_

- [ ] 13. Android — registration flow
  - [ ] 13.1 Implement `RegistrationActivity`
    - Input fields for Aadhaar (12-digit numeric) or passport; client-side format validation
    - Call `POST /api/v1/register` via Retrofit; on success store encrypted ID via `TouristPreferences`
    - Display `Digital_Tourist_ID` and `validUntil` on `MainActivity` home screen
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 14. Android — location tracking service
  - [ ] 14.1 Implement `LocationTrackingService` foreground service
    - `FusedLocationProviderClient` at 10 s normal interval, 3 s during active SOS
    - On each fix: call `FirebaseRepository.pushLocation`, enqueue to `OfflineBuffer` if offline
    - Emit `GPS_LOSS` event to `AnomalyDetector` after 60 s without fix
    - _Requirements: 3.1, 3.2, 3.3, 3.5_

  - [ ] 14.2 Implement `OfflineBuffer` using Room database
    - `LocationUpdateEntity` table; insert on capture, delete batch after successful transmission
    - `flushBuffer()`: read all rows ordered by timestamp, POST to API, delete on 200 response
    - _Requirements: 3.4, 12.1, 12.2_

  - [ ]* 14.3 Write Kotest property test for offline buffer order and completeness (Property 5 — Android)
    - **Property 5: Offline buffer round-trip preserves order and completeness**
    - **Validates: Requirements 3.4, 12.1, 12.2**

- [ ] 15. Android — geo-fence manager and SOS
  - [ ] 15.1 Implement `GeofenceManager.kt`
    - On app start, fetch zone list from `GET /api/v1/zones` and cache locally
    - `checkZones(lat, lng)`: Haversine check against cached zones; return matching zone or null
    - Show push notification for HIGH/RESTRICTED zone entry; enforce 5-min cooldown in memory
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 13.3_

  - [ ] 15.2 Implement SOS button in `MainActivity`
    - Prominent SOS button; on press call `POST /api/v1/sos` with current location
    - If offline: store SOS in `OfflineBuffer`, show "SOS queued" toast
    - Show confirmation within 5 s; switch `LocationTrackingService` to 3 s interval
    - _Requirements: 6.1, 6.2, 6.5, 6.6, 12.3_

  - [ ]* 15.3 Write Kotest property test for geo-fence zone detection (Property 6 — Android)
    - **Property 6: Geo-fence alert fires within latency bound and respects cooldown**
    - **Validates: Requirements 4.2, 4.5**

- [ ] 16. Android — safety score display and anomaly notifications
  - [ ] 16.1 Display safety score on `MainActivity`
    - Poll `GET /api/v1/score/{touristId}` every 30 s; display score and SAFE/CAUTION/DANGER label with colour coding
    - _Requirements: 5.3_

  - [ ] 16.2 Handle incoming FCM push notifications
    - Parse anomaly alert and SOS resolution notifications; show safety check dialog for anomaly alerts
    - On tourist response (safe/not safe): POST acknowledgement to API; if no response in 5 min, escalation handled server-side
    - _Requirements: 7.7, 6.7_

  - [ ] 16.3 Show offline mode indicator
    - Observe network state; display persistent banner when offline
    - _Requirements: 12.4_

- [ ] 17. Checkpoint — Android build and instrumented tests pass
  - Ensure the Android project compiles and instrumented tests for `LocationTrackingService`, `OfflineBuffer`, and `GeofenceManager` pass. Ask the user if questions arise.

- [ ] 18. Web dashboard — map and real-time tourist tracking
  - [ ] 18.1 Implement Leaflet.js map centred on Maharashtra in `index.html` / `app.js`
    - Initialise Firebase Web SDK; subscribe to `Firebase:/LiveLocation` for real-time tourist markers
    - Colour-code markers: green (SAFE), amber (CAUTION), red (DANGER/SOS)
    - _Requirements: 8.1_

  - [ ] 18.2 Implement alert panel with audible notification
    - Subscribe to `Firebase:/Alerts`; render SOS, geo-fence, and anomaly alerts in sidebar
    - Play audible alert sound for HIGH risk and SOS events
    - _Requirements: 8.2_

  - [ ] 18.3 Implement tourist detail view
    - On marker click: fetch tourist record from API, display Digital_Tourist_ID, identity hash, safety score, location history polyline on map
    - Show blockchain tx hash with "Verify" button calling `GET /api/v1/blockchain/verify/{txHash}`
    - _Requirements: 8.3, 11.4_

- [ ] 19. Web dashboard — incident management and zone admin
  - [ ] 19.1 Implement incident manager UI
    - Form to create Incident linked to SOS/alert; display incident list with status badges
    - Buttons to update status to IN_PROGRESS / RESOLVED; call `PATCH /api/v1/incidents/{id}`
    - _Requirements: 8.4, 8.5, 8.6, 8.7_

  - [ ] 19.2 Implement filtering controls
    - Filter tourists and alerts by region, risk level, alert type
    - _Requirements: 8.8_

  - [ ] 19.3 Implement zone admin panel (ADMIN only)
    - Form to add/edit/deactivate geo-fence zones; POST/PATCH to zone API
    - Hide panel for AUTHORITY role via RBAC token claim check in JS
    - _Requirements: 13.2, 9.4_

- [ ] 20. Firebase security rules and MongoDB indexes
  - [ ] 20.1 Write Firebase Realtime Database security rules
    - Tourists write only to own `/LiveLocation/{touristId}` and `/SOS/{touristId}`
    - Dashboard reads require `AUTHORITY` or `ADMIN` claim
    - _Requirements: 9.2, 9.3_

  - [ ] 20.2 Create MongoDB indexes
    - Unique index on `tourists.idHash`; TTL index on `location_history`; compound index on `incidents` (touristId, status)
    - _Requirements: 10.4_

- [ ] 21. Integration wiring — end-to-end flows
  - [ ] 21.1 Wire registration end-to-end
    - Android app → `POST /api/v1/register` → IdentityVerifier → Blockchain → Firebase → app stores ID
    - Verify response contains `touristId`, `validUntil`, `txHash`
    - _Requirements: 1.1, 1.3, 2.2, 2.3_

  - [ ] 21.2 Wire SOS end-to-end
    - Android SOS button → `POST /api/v1/sos` → SosHandler → Firebase `/SOS` + `/Alerts` → Dashboard alert panel → authority resolves → tourist receives FCM notification
    - _Requirements: 6.2, 6.3, 6.4, 6.6, 6.7_

  - [ ] 21.3 Wire offline resilience end-to-end
    - Simulate network disconnect on Android; generate location updates; reconnect; verify Firebase `/LocationHistory` contains all updates in order
    - _Requirements: 3.4, 12.1, 12.2_

  - [ ] 21.4 Wire zone propagation end-to-end
    - ADMIN updates zone via dashboard → `PATCH /api/v1/zones/{id}` → Firebase `/Zones` updated → Android app fetches updated zone list within 60 s
    - _Requirements: 13.3_

  - [ ]* 21.5 Write integration tests for all four end-to-end flows
    - Cover registration, SOS, offline resilience, and zone propagation flows using pytest + requests
    - _Requirements: 1.1, 6.2, 3.4, 13.3_

- [ ] 22. Final checkpoint — all tests pass
  - Ensure all backend unit tests, property tests, Android instrumented tests, and integration tests pass. Ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests require minimum 100 iterations each (hypothesis `@settings(max_examples=100)`, kotest `PropTestConfig(iterations = 100)`)
- Each property test file must include the tag comment: `# Feature: maharashtra-tourist-safety, Property N: <property_text>`
- Blockchain writes are always async — never block user-facing responses waiting for on-chain confirmation
- The Anomaly Detector worker runs as a separate process; do not couple it to the API Gateway request cycle
