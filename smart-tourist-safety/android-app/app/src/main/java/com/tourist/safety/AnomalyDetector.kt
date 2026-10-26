package com.tourist.safety

/**
 * AnomalyDetector - detects stationary tourists and abnormal movement speed.
 */
class AnomalyDetector {
    private var lastLat = 0.0; private var lastLng = 0.0
    private var lastMoveTime = System.currentTimeMillis()
    private var lastUpdateTime = System.currentTimeMillis()

    companion object {
        const val STATIONARY_THRESHOLD_MS = 10 * 60 * 1000L  // 10 minutes
        const val MAX_SPEED_MPS = 30.0                         // ~108 km/h
    }

    data class AnomalyResult(val detected: Boolean, val type: String, val risk: String)

    fun analyze(lat: Double, lng: Double): AnomalyResult? {
        val now = System.currentTimeMillis()
        val dist = GeofenceManager.distanceMeters(lastLat, lastLng, lat, lng)
        val timeSec = (now - lastUpdateTime) / 1000.0

        if (timeSec > 1 && lastUpdateTime > 0 && (lastLat != 0.0 || lastLng != 0.0)) {
            if (dist / timeSec > MAX_SPEED_MPS) {
                update(lat, lng, now)
                return AnomalyResult(true, "ABNORMAL_SPEED", "MEDIUM")
            }
        }
        if (dist > 10) lastMoveTime = now
        else if ((now - lastMoveTime) > STATIONARY_THRESHOLD_MS) {
            update(lat, lng, now)
            return AnomalyResult(true, "STATIONARY", "LOW")
        }
        update(lat, lng, now)
        return null
    }

    private fun update(lat: Double, lng: Double, time: Long) { lastLat = lat; lastLng = lng; lastUpdateTime = time }
    fun reset() { lastLat = 0.0; lastLng = 0.0; lastMoveTime = System.currentTimeMillis(); lastUpdateTime = System.currentTimeMillis() }
}
