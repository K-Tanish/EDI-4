package com.tourist.safety

import android.app.*
import android.content.Intent
import android.os.*
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.android.gms.location.*
import kotlinx.coroutines.*

/**
 * LocationTrackingService — foreground service for continuous GPS tracking.
 * Normal interval: 10 s. SOS interval: 3 s.
 * Buffers updates offline via FirebaseRepository.
 * Implements: Requirements 3.1, 3.2, 3.3, 3.5
 */
class LocationTrackingService : Service() {

    companion object {
        const val CHANNEL_ID = "tourist_tracking"
        const val NOTIF_ID = 1001
        const val ACTION_STOP = "ACTION_STOP"
        const val ACTION_SOS_MODE = "ACTION_SOS_MODE"
        const val NORMAL_INTERVAL_MS = 10_000L
        const val SOS_INTERVAL_MS = 3_000L
        var isRunning = false
    }

    private lateinit var fusedClient: FusedLocationProviderClient
    private lateinit var locationCallback: LocationCallback
    private val anomalyDetector = AnomalyDetector()
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val alertCooldown = mutableMapOf<String, Long>()
    private val COOLDOWN_MS = 5 * 60 * 1000L
    private var touristId = ""
    private var currentIntervalMs = NORMAL_INTERVAL_MS

    override fun onCreate() {
        super.onCreate()
        fusedClient = LocationServices.getFusedLocationProviderClient(this)
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> { stopSelf(); return START_NOT_STICKY }
            ACTION_SOS_MODE -> { switchInterval(SOS_INTERVAL_MS); return START_STICKY }
        }
        touristId = intent?.getStringExtra("touristId") ?: return START_NOT_STICKY
        currentIntervalMs = intent.getLongExtra("intervalMs", NORMAL_INTERVAL_MS)
        startForeground(NOTIF_ID, buildNotification())
        isRunning = true
        startTracking()
        return START_STICKY
    }

    private fun startTracking() {
        val req = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, currentIntervalMs)
            .setMinUpdateIntervalMillis(currentIntervalMs / 2).build()

        locationCallback = object : LocationCallback() {
            override fun onLocationResult(r: LocationResult) {
                r.lastLocation?.let { loc ->
                    scope.launch { processLocation(touristId, loc.latitude, loc.longitude, loc.accuracy) }
                }
            }
        }
        try {
            fusedClient.requestLocationUpdates(req, locationCallback, mainLooper)
        } catch (e: SecurityException) {
            Log.e("LocationService", "Permission denied: ${e.message}"); stopSelf()
        }
    }

    private fun switchInterval(intervalMs: Long) {
        if (!::locationCallback.isInitialized) return
        fusedClient.removeLocationUpdates(locationCallback)
        currentIntervalMs = intervalMs
        startTracking()
    }

    private suspend fun processLocation(id: String, lat: Double, lng: Double, accuracy: Float) {
        var status = "SAFE"

        // Geo-fence check
        GeofenceManager.checkZones(lat, lng)?.let { zone ->
            status = if (zone.riskLevel == "RESTRICTED") "DANGER" else "CAUTION"
            throttleAlert(id, "ZONE_ENTRY_${zone.zoneId}", zone.riskLevel, lat, lng)
        }

        // Anomaly detection
        anomalyDetector.analyze(lat, lng)?.let { anomaly ->
            throttleAlert(id, anomaly.type, anomaly.risk, lat, lng)
        }

        // Push to Firebase (handles offline buffering internally)
        FirebaseRepository.updateLiveLocation(id, lat, lng, status)
        FirebaseRepository.pushLocationHistory(id, lat, lng)

        // Push to backend API
        val jwt = TouristPreferences.getJwt(applicationContext) ?: return
        try {
            ApiClient.api.updateLocation(
                "Bearer $jwt",
                LocationPayload(id, lat, lng, System.currentTimeMillis(), accuracy)
            )
        } catch (e: Exception) {
            Log.w("LocationService", "API push failed (offline?): ${e.message}")
        }
    }

    private fun throttleAlert(id: String, type: String, risk: String, lat: Double, lng: Double) {
        val now = System.currentTimeMillis()
        if (now - (alertCooldown[type] ?: 0L) > COOLDOWN_MS) {
            alertCooldown[type] = now
            FirebaseRepository.createAlert(id, type, risk, lat, lng)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        if (::locationCallback.isInitialized) fusedClient.removeLocationUpdates(locationCallback)
        scope.cancel()
        anomalyDetector.reset()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Tourist Safety Tracking", NotificationManager.IMPORTANCE_LOW)
            )
        }
    }

    private fun buildNotification(): Notification {
        val stopIntent = PendingIntent.getService(
            this, 0,
            Intent(this, LocationTrackingService::class.java).apply { action = ACTION_STOP },
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Maharashtra Tourist Safety")
            .setContentText("GPS tracking active")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .addAction(android.R.drawable.ic_delete, "Stop", stopIntent)
            .setOngoing(true).build()
    }
}
