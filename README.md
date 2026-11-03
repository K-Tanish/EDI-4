# Smart Tourist Safety Monitoring and Incident Response System

A prototype platform for monitoring tourist safety across Maharashtra. The repository brings together an Android application, a live web control-room dashboard, a Python REST API, data-analysis utilities, and an Ethereum smart contract.

The codebase contains two closely related implementations: the Android and dashboard demo in `smart-tourist-safety/`, and the API and blockchain prototype in `maharashtra-tourist-safety/`. They share the same project goal, but require configuration to connect to the same Firebase project and API before they operate as one end-to-end deployment.

## What it does

- Tracks tourist locations from an Android foreground location service.
- Displays tourists and incoming alerts on a Leaflet map centered on Maharashtra.
- Detects configured geofence entries and movement anomalies, including prolonged stationary movement and unusually high speed.
- Provides SOS and incident-related API routes and safety-score calculations.
- Includes a registry of example Maharashtra zones and synthetic data generation and evaluation utilities.
- Includes a Solidity contract and Python scripts for the blockchain component.

This is a development prototype, not a production-ready emergency response service. Do not rely on it for real-world safety decisions or submit real identity documents or location data.

## Repository layout

```text
.
├── maharashtra-tourist-safety/
│   ├── backend/                  # FastAPI application, services, workers, and analysis data
│   └── blockchain/               # Solidity contract and blockchain utility scripts
├── smart-tourist-safety/
│   ├── android-app/              # Kotlin Android app
│   └── web-dashboard/            # Browser-based Firebase dashboard
├── .kiro/specs/                  # Project requirements, design, and task documents
└── README.md
```

## Architecture

```text
Android app ── REST ──> FastAPI backend ──> MongoDB
    │                          │
    │                          ├──> Firebase Realtime Database
    │                          ├──> anomaly and escalation workers
    │                          └──> optional blockchain integration
    │
    └── Firebase Realtime Database <── Web dashboard
```

The dashboard listens to Firebase Realtime Database for live tourist and alert data. The backend can write live locations and history to Firebase, while MongoDB is used for persistent records when available. The backend includes asynchronous anomaly and escalation workers.

The blockchain contract and client utilities are present, and the identity service accepts an optional blockchain client. The backend does not initialize and inject that client automatically at startup; configure this integration separately before expecting API operations to be recorded on-chain.

## Technology

- Android: Kotlin, Android SDK 34, Google Play Services Location, Firebase Realtime Database, Retrofit.
- Dashboard: HTML, CSS, JavaScript, Leaflet, Firebase Web SDK.
- Backend: Python, FastAPI, Pydantic, MongoDB, Firebase Admin SDK, Redis/Celery dependencies, and scikit-learn.
- Blockchain: Solidity 0.8+, Web3.py, and py-solc-x.

## Getting started

### 1. Start the backend

Requirements: Python 3.10 or later and, for full persistence and live features, MongoDB and Firebase project credentials.

From the repository root:

```powershell
cd maharashtra-tourist-safety\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

Create a `backend/.env` file and configure at least a non-default JWT signing secret:

```dotenv
JWT_SECRET=replace-with-a-long-random-secret
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=maharashtra_tourist_safety
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json
```

Place a Firebase Admin service-account JSON file at the configured path, or set `FIREBASE_CREDENTIALS_PATH` to its location. Keep service-account files and `.env` files private; do not commit them. The Firebase project/database URL is currently configured in the backend code and must match the project used by the dashboard and Android app.

Start the API from the `backend` directory:

```bash
uvicorn app:app --reload
```

The API will be available at `http://127.0.0.1:8000`. Check `http://127.0.0.1:8000/health` for the health endpoint and `http://127.0.0.1:8000/docs` for interactive API documentation.

MongoDB and Firebase initialization can fail without stopping the API, but the corresponding persistence or live database features will then be unavailable. The application currently contains development defaults; configure secure values and production services before exposing it beyond a local environment.

### 2. Configure and run the Android app

1. Create or select a Firebase project and register an Android app with package name `com.tourist.safety`.
2. Download that project's `google-services.json` and place it in `smart-tourist-safety/android-app/app/`. Do not commit credentials or environment-specific configuration.
3. Open `smart-tourist-safety/android-app/` in Android Studio, sync the Gradle project, and run it on an Android device or emulator with Google Play Services.
4. Configure the API base URL in `ApiClient.kt` to point to the backend. For an Android emulator, use the emulator's host-loopback address (commonly `10.0.2.2`) and the backend port. For a physical device, use a reachable development-machine address.
5. Grant the location permissions requested by the app. Location tracking requires device location services and network access for remote updates.

The Android app and dashboard must use a Firebase project/database that is configured to receive the same data. The current client configuration is environment-specific; replace it with your own Firebase configuration and database rules.

### 3. Run the web dashboard

Configure the Firebase Web app settings in `smart-tourist-safety/web-dashboard/app.js` to match your Firebase project. Apply database rules appropriate for your test setup; do not use permissive test rules for a public or production database.

Serve the dashboard from the repository root:

```bash
python -m http.server 8080 --directory smart-tourist-safety/web-dashboard
```

Open `http://localhost:8080` in a browser. The dashboard uses Firebase Realtime Database and loads Leaflet and Firebase scripts from external CDNs, so internet access is required.

### 4. Blockchain development

The Solidity contract is at `maharashtra-tourist-safety/blockchain/contracts/TouristSafety.sol`. The adjacent Python scripts support compiling, deploying, and interacting with the contract. Blockchain use requires a compatible local or hosted Ethereum node, a Solidity compiler, and suitable deployment configuration. Treat local-chain scripts and credentials as development-only.

## API overview

The API routes are mounted under `/api/v1`:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/register` | Register a tourist and issue a signed token |
| `POST` | `/location` | Submit a tourist location update |
| `POST` | `/sos` | Submit an SOS event |
| `GET` | `/zones` | List the configured safety zones |
| `POST`, `PATCH` | `/zones` | Create or update zones (authority access required) |
| `GET` | `/score/{touristId}` | Retrieve a tourist safety score |
| `GET`, `POST`, `PATCH` | `/incidents` and `/incidents/{incident_id}` | Manage incidents |
| `GET` | `/blockchain/verify/{txHash}` | Verify a blockchain transaction |
| `GET` | `/health` | Check API availability |

Most tourist and authority operations require the appropriate bearer token. See the interactive API documentation at `/docs` for request models and authentication details.

## Data and evaluation

Synthetic trajectories, detector outputs, evaluation results, and generated figures are stored under `maharashtra-tourist-safety/backend/data/`. Analysis and plotting scripts are in `maharashtra-tourist-safety/backend/utils/`. These are development and evaluation artifacts; synthetic results should not be interpreted as field validation.

## Security and privacy

- Never commit Firebase service-account JSON, `.env` files, private keys, or real identity data.
- Set a strong, unique `JWT_SECRET`; do not use the development default.
- Use appropriately restrictive Firebase Realtime Database rules and protect authority-only routes.
- The project contains prototype configuration that may not be suitable for production. Review service URLs, CORS policy, transport security, authentication, and data retention before deployment.
- Use synthetic data for demonstrations and evaluation.

## License

No license is currently specified. Unless a license is added, standard copyright restrictions apply to reuse and redistribution.
