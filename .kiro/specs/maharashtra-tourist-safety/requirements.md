# Requirements Document

## Introduction

The Smart Tourist Safety Monitoring & Incident Response System is a unified digital platform for Maharashtra, India, designed to proactively protect domestic and international tourists across the state's diverse regions — urban centres (Mumbai, Pune, Nagpur), coastal areas (Konkan coast), hill stations (Mahabaleshwar, Lonavala), forests (Tadoba, Melghat), and heritage sites (Ajanta, Ellora). The system integrates a blockchain-based digital tourist identity, a mobile application with geo-fencing and SOS capabilities, AI-based anomaly detection, and a centralised web dashboard for Maharashtra Tourism authorities and state law enforcement.

---

## Glossary

- **System**: The Smart Tourist Safety Monitoring & Incident Response System for Maharashtra
- **Tourist**: A domestic or international visitor registered within the System during their stay in Maharashtra
- **Digital_Tourist_ID**: A temporary, cryptographically secured digital identity token issued to a Tourist upon verified registration, valid only for the duration of the tourist's visit within Maharashtra
- **Identity_Verifier**: The subsystem responsible for validating Aadhaar or passport credentials and issuing Digital_Tourist_IDs
- **Mobile_App**: The Android application installed on a Tourist's device
- **Location_Service**: The foreground background service within the Mobile_App responsible for continuous GPS tracking
- **Geofence_Engine**: The subsystem that defines and monitors Maharashtra-specific geographic boundaries and risk zones
- **Anomaly_Detector**: The AI/ML subsystem that analyses Tourist movement patterns to identify distress or unusual behaviour
- **SOS_Handler**: The subsystem that processes panic/SOS signals from Tourists
- **Blockchain_Ledger**: The Ethereum-based tamper-proof distributed ledger storing Tourist IDs, SOS events, and incident records
- **Dashboard**: The centralised web-based control room accessible to Maharashtra Tourism officials and state law enforcement
- **Incident_Manager**: The Dashboard subsystem for creating, assigning, and resolving safety incidents
- **Notification_Service**: The subsystem responsible for delivering alerts to Tourists and authorities
- **RBAC_Controller**: The Role-Based Access Control subsystem governing data access permissions
- **Risk_Scorer**: The subsystem that computes a real-time safety score for a Tourist's current location based on zone classification
- **Data_Store**: The backend database (Firebase / MongoDB) storing Tourist profiles, location history, and alert records
- **API_Gateway**: The RESTful backend (Flask / FastAPI) mediating communication between Mobile_App, Dashboard, and backend services
- **Aadhaar**: India's national biometric identity system
- **Geo-fence Zone**: A defined geographic boundary within Maharashtra associated with a risk level (LOW / MEDIUM / HIGH / RESTRICTED)
- **SOS Event**: A distress signal triggered manually by a Tourist or automatically by the Anomaly_Detector
- **Incident**: A recorded safety case created in the Dashboard in response to an SOS Event or anomaly alert

---

## Requirements

### Requirement 1: Blockchain-Based Digital Tourist Identity Registration

**User Story:** As a Tourist visiting Maharashtra, I want to register my identity using my Aadhaar or passport so that I receive a secure, temporary digital ID valid only for my visit.

#### Acceptance Criteria

1. WHEN a Tourist submits a valid Aadhaar number or passport number for registration, THE Identity_Verifier SHALL generate a Digital_Tourist_ID within 10 seconds.
2. THE Identity_Verifier SHALL hash the Tourist's identity document number using SHA-256 before storing or transmitting it.
3. THE Identity_Verifier SHALL record the Digital_Tourist_ID, hashed identity reference, visit start timestamp, and visit end timestamp on the Blockchain_Ledger.
4. WHEN a Tourist's visit end timestamp is reached, THE Identity_Verifier SHALL mark the Digital_Tourist_ID as expired on the Blockchain_Ledger.
5. IF an Aadhaar number or passport number fails format validation, THEN THE Identity_Verifier SHALL return a descriptive error message within 3 seconds without storing any data.
6. THE Blockchain_Ledger SHALL ensure that each Digital_Tourist_ID entry is immutable after creation.
7. WHEN a duplicate registration attempt is made using the same identity document within an active visit period, THE Identity_Verifier SHALL reject the request and return an error indicating an active ID already exists.

---

### Requirement 2: Mobile Application — Tourist Registration and Onboarding

**User Story:** As a Tourist, I want to register and onboard through the Mobile_App so that I can access all safety features during my Maharashtra visit.

#### Acceptance Criteria

1. THE Mobile_App SHALL support registration using Aadhaar or passport number as the identity input.
2. WHEN registration is successful, THE Mobile_App SHALL display the Tourist's Digital_Tourist_ID and visit validity period on the home screen.
3. THE Mobile_App SHALL store the Digital_Tourist_ID locally in encrypted storage on the device.
4. WHEN the Mobile_App is launched after a successful registration, THE Mobile_App SHALL restore the Tourist's session without requiring re-registration.
5. IF the stored Digital_Tourist_ID is expired, THEN THE Mobile_App SHALL prompt the Tourist to re-register.

---

### Requirement 3: Continuous GPS Location Tracking

**User Story:** As a Maharashtra Tourism authority, I want the Mobile_App to continuously track Tourist locations so that I can monitor tourist safety in real time.

#### Acceptance Criteria

1. WHILE a Tourist's session is active, THE Location_Service SHALL capture the Tourist's GPS coordinates at intervals not exceeding 10 seconds.
2. WHILE the Mobile_App is running in the background, THE Location_Service SHALL continue GPS tracking without interruption.
3. THE Location_Service SHALL transmit each captured location update to the Data_Store via the API_Gateway within 5 seconds of capture.
4. THE Location_Service SHALL store location updates locally when network connectivity is unavailable and transmit them once connectivity is restored.
5. IF GPS signal is unavailable for more than 60 seconds, THEN THE Location_Service SHALL notify the Anomaly_Detector of a signal loss event.
6. THE Location_Service SHALL record a timestamped location history for each Tourist in the Data_Store.

---

### Requirement 4: Maharashtra-Specific Geo-Fencing and Safety Alerts

**User Story:** As a Tourist, I want to receive alerts when I enter high-risk or restricted zones in Maharashtra so that I can make informed safety decisions.

#### Acceptance Criteria

1. THE Geofence_Engine SHALL maintain a configurable registry of Geo-fence Zones covering Maharashtra regions including coastal areas, hill stations, forest zones, and urban high-risk areas.
2. WHEN a Tourist's location enters a Geo-fence Zone classified as HIGH or RESTRICTED risk, THE Geofence_Engine SHALL trigger an alert within 15 seconds of zone entry detection.
3. WHEN a Geo-fence Zone alert is triggered, THE Mobile_App SHALL display a push notification describing the zone name, risk level, and recommended safety action.
4. WHEN a Geo-fence Zone alert is triggered, THE Notification_Service SHALL simultaneously send an alert to the Dashboard.
5. THE Geofence_Engine SHALL enforce a minimum alert cooldown of 5 minutes per Tourist per Geo-fence Zone to prevent duplicate alerts.
6. WHERE a Geo-fence Zone is classified as RESTRICTED, THE Geofence_Engine SHALL log the entry event on the Blockchain_Ledger.

---

### Requirement 5: Real-Time Safety Scoring

**User Story:** As a Tourist, I want to see a real-time safety score for my current location so that I can assess risk before or during travel.

#### Acceptance Criteria

1. WHILE a Tourist's session is active, THE Risk_Scorer SHALL compute a safety score between 0 and 100 for the Tourist's current location, where 0 represents maximum risk and 100 represents no known risk.
2. THE Risk_Scorer SHALL update the safety score within 10 seconds of a location change that crosses a zone boundary.
3. THE Mobile_App SHALL display the current safety score and corresponding risk label (SAFE / CAUTION / DANGER) on the home screen.
4. THE Risk_Scorer SHALL derive the safety score from the Geo-fence Zone classification, historical incident density, and time-of-day factors for the current location.

---

### Requirement 6: SOS / Panic Button

**User Story:** As a Tourist in distress, I want to trigger an SOS alert with my live location so that authorities can respond immediately.

#### Acceptance Criteria

1. THE Mobile_App SHALL provide a clearly visible SOS button accessible from the home screen without requiring navigation.
2. WHEN a Tourist activates the SOS button, THE SOS_Handler SHALL create an SOS Event containing the Tourist's Digital_Tourist_ID, GPS coordinates, and timestamp within 5 seconds.
3. WHEN an SOS Event is created, THE SOS_Handler SHALL record the event on the Blockchain_Ledger.
4. WHEN an SOS Event is created, THE Notification_Service SHALL send a high-priority alert to the Dashboard within 10 seconds.
5. WHEN an SOS Event is active, THE Location_Service SHALL increase the GPS update frequency to intervals not exceeding 3 seconds.
6. THE Mobile_App SHALL display a confirmation to the Tourist within 5 seconds of SOS activation indicating that authorities have been notified.
7. WHEN an SOS Event is resolved by an authority on the Dashboard, THE Notification_Service SHALL send a resolution notification to the Tourist's Mobile_App.

---

### Requirement 7: AI-Based Anomaly Detection

**User Story:** As a Maharashtra Tourism authority, I want the system to automatically detect unusual Tourist behaviour so that I can proactively respond before a Tourist manually triggers an SOS.

#### Acceptance Criteria

1. WHILE a Tourist's session is active, THE Anomaly_Detector SHALL continuously analyse the Tourist's movement pattern using location history from the Data_Store.
2. WHEN a Tourist has not moved more than 10 metres for a continuous period of 10 minutes in a non-accommodation zone, THE Anomaly_Detector SHALL generate a LOW risk anomaly alert.
3. WHEN a Tourist's computed movement speed exceeds 30 metres per second, THE Anomaly_Detector SHALL generate a MEDIUM risk anomaly alert indicating abnormal speed.
4. WHEN the Location_Service reports a GPS signal loss event lasting more than 5 minutes in a HIGH or RESTRICTED risk zone, THE Anomaly_Detector SHALL generate a HIGH risk anomaly alert.
5. WHEN a Tourist deviates more than 500 metres from a pre-registered planned route, THE Anomaly_Detector SHALL generate a MEDIUM risk anomaly alert.
6. WHEN the Anomaly_Detector generates a HIGH risk anomaly alert, THE Notification_Service SHALL send the alert to the Dashboard within 10 seconds.
7. WHEN the Anomaly_Detector generates any anomaly alert, THE Mobile_App SHALL display a safety check notification prompting the Tourist to confirm their status.
8. IF a Tourist does not respond to a safety check notification within 5 minutes, THEN THE Anomaly_Detector SHALL escalate the alert severity by one level.

---

### Requirement 8: Centralised Dashboard for Authorities

**User Story:** As a Maharashtra Tourism official or state law enforcement officer, I want a centralised dashboard so that I can monitor all active tourists, view alerts, and manage incidents in real time.

#### Acceptance Criteria

1. THE Dashboard SHALL display a real-time map of Maharashtra showing the live locations of all active Tourists.
2. WHEN a new SOS Event or HIGH risk alert is received, THE Dashboard SHALL display the alert within 10 seconds and play an audible notification.
3. THE Dashboard SHALL provide a Tourist detail view showing the Tourist's Digital_Tourist_ID, verified identity reference, current location, safety score, and location history.
4. THE Dashboard SHALL allow an authority to create an Incident linked to an SOS Event or anomaly alert.
5. WHEN an Incident is created, THE Incident_Manager SHALL assign a unique incident ID and record the creation timestamp.
6. THE Dashboard SHALL allow an authority to update the status of an Incident to IN_PROGRESS or RESOLVED.
7. WHEN an Incident status is updated to RESOLVED, THE Incident_Manager SHALL record the resolution timestamp and resolving officer ID on the Blockchain_Ledger.
8. THE Dashboard SHALL support filtering of Tourists and alerts by region, risk level, and alert type.

---

### Requirement 9: Role-Based Access Control

**User Story:** As a system administrator, I want role-based access control so that Tourist data is only accessible to authorised personnel.

#### Acceptance Criteria

1. THE RBAC_Controller SHALL enforce three roles: TOURIST, AUTHORITY, and ADMIN.
2. WHILE a user holds the TOURIST role, THE RBAC_Controller SHALL restrict data access to that user's own Digital_Tourist_ID, location, and SOS events only.
3. WHILE a user holds the AUTHORITY role, THE RBAC_Controller SHALL grant read access to all active Tourist locations, alerts, and incidents within the authority's assigned region.
4. WHILE a user holds the ADMIN role, THE RBAC_Controller SHALL grant full read and write access to all system data including zone configuration and user management.
5. IF a user attempts to access a resource outside their role's permitted scope, THEN THE RBAC_Controller SHALL deny the request and log the unauthorised access attempt.
6. THE RBAC_Controller SHALL require re-authentication after 8 hours of inactivity for AUTHORITY and ADMIN roles.

---

### Requirement 10: Data Encryption and Privacy

**User Story:** As a Tourist, I want my personal data to be encrypted and handled with privacy so that my identity and location are not exposed to unauthorised parties.

#### Acceptance Criteria

1. THE System SHALL encrypt all Tourist personally identifiable information at rest using AES-256.
2. THE System SHALL transmit all data between the Mobile_App, API_Gateway, and Data_Store over TLS 1.2 or higher.
3. THE Identity_Verifier SHALL never store the raw Aadhaar number or passport number; only the SHA-256 hash SHALL be persisted.
4. THE Data_Store SHALL retain Tourist location history for a maximum of 90 days after the Tourist's visit end date, after which the data SHALL be automatically purged.
5. WHERE a Tourist requests deletion of their data before the 90-day retention period, THE System SHALL purge all personally identifiable Tourist data from the Data_Store within 24 hours.

---

### Requirement 11: Blockchain Audit Trail

**User Story:** As a Maharashtra Tourism authority, I want all critical events to be recorded on a tamper-proof blockchain so that incident records are verifiable and legally defensible.

#### Acceptance Criteria

1. THE Blockchain_Ledger SHALL record the following event types: Digital_Tourist_ID issuance, Digital_Tourist_ID expiry, SOS Event creation, SOS Event resolution, RESTRICTED zone entry, and Incident resolution.
2. WHEN an event is written to the Blockchain_Ledger, THE Blockchain_Ledger SHALL return a transaction hash within 30 seconds.
3. THE Blockchain_Ledger SHALL ensure that no previously recorded event can be modified or deleted.
4. THE Dashboard SHALL allow an AUTHORITY or ADMIN user to retrieve and verify the transaction hash for any recorded event.
5. THE Blockchain_Ledger SHALL use Solidity smart contracts deployed on an Ethereum-compatible network to enforce immutability.

---

### Requirement 12: Offline Resilience

**User Story:** As a Tourist in a low-connectivity area such as a forest or remote hill station, I want the Mobile_App to continue functioning so that my safety data is not lost during network outages.

#### Acceptance Criteria

1. WHILE network connectivity is unavailable, THE Mobile_App SHALL continue capturing GPS location updates and storing them locally.
2. WHEN network connectivity is restored, THE Location_Service SHALL transmit all locally stored location updates to the Data_Store in chronological order.
3. WHILE network connectivity is unavailable, THE Mobile_App SHALL allow the Tourist to trigger an SOS Event, storing it locally for transmission upon reconnection.
4. THE Mobile_App SHALL display a visible indicator when operating in offline mode.

---

### Requirement 13: Maharashtra Region Coverage and Zone Configuration

**User Story:** As a system administrator, I want to configure geo-fence zones specific to Maharashtra's diverse regions so that the system reflects accurate local risk profiles.

#### Acceptance Criteria

1. THE Geofence_Engine SHALL support at minimum the following Maharashtra region types: urban high-risk areas, Konkan coastal zones, Western Ghats hill station zones, forest and wildlife reserve zones, and heritage site zones.
2. THE Geofence_Engine SHALL allow an ADMIN user to add, update, or deactivate a Geo-fence Zone without requiring a system restart.
3. WHEN a Geo-fence Zone is updated by an ADMIN, THE Geofence_Engine SHALL propagate the updated zone boundaries to all active Mobile_App instances within 60 seconds.
4. THE Geofence_Engine SHALL support zone risk levels of LOW, MEDIUM, HIGH, and RESTRICTED.
