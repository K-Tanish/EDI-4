package com.tourist.safety

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.math.*

/**
 * GeofenceManager — Maharashtra-specific geo-fence zone management.
 * Fetches zone list from backend API; performs Haversine distance checks.
 * Enforces 5-minute alert cooldown per zone.
 * Implements: Requirements 4.1, 4.2, 4.3, 4.5, 13.3
 */
object GeofenceManager {

    private const val TAG = "GeofenceManager"
    private const val COOLDOWN_MS = 5 * 60 * 1000L

    // Cached zone list (refreshed on app start and zone updates)
    private var cachedZones: List<DangerZone> = maharashtraDefaultZones()
    private val cooldowns = mutableMapOf<String, Long>()  // zoneId -> last alert timestamp

    /** Refresh zone list from backend API. Falls back to defaults on failure. */
    suspend fun refreshZones(apiClient: ApiClient) = withContext(Dispatchers.IO) {
        try {
            val response = apiClient.getZones()
            if (response.isSuccessful) {
                cachedZones = response.body()?.zones?.map { z ->
                    DangerZone(
                        zoneId = z.zoneId,
                        name = z.name,
                        type = z.type,
                        riskLevel = z.riskLevel,
                        latitude = z.centerLat,
                        longitude = z.centerLng,
                        radiusMeters = z.radiusMeters,
                        active = z.active
                    )
                } ?: maharashtraDefaultZones()
            } else Unit
        } catch (e: Exception) {
            Log.w(TAG, "Zone refresh failed, using cached: ${e.message}")
        }
    }

    /**
     * Check if [lat]/[lng] is inside any HIGH or RESTRICTED zone.
     * Returns the matched zone if an alert should fire (respects cooldown), else null.
     */
    fun checkZones(lat: Double, lng: Double): DangerZone? {
        val now = System.currentTimeMillis()
        return cachedZones
            .filter { it.active && it.riskLevel in listOf("HIGH", "RESTRICTED") }
            .firstOrNull { zone ->
                val dist = distanceMeters(lat, lng, zone.latitude, zone.longitude)
                if (dist > zone.radiusMeters) return@firstOrNull false
                val lastAlert = cooldowns[zone.zoneId] ?: 0L
                if (now - lastAlert < COOLDOWN_MS) return@firstOrNull false
                cooldowns[zone.zoneId] = now
                true
            }
    }

    fun distanceMeters(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
        val R = 6_371_000.0
        val dLat = Math.toRadians(lat2 - lat1)
        val dLng = Math.toRadians(lng2 - lng1)
        val a = sin(dLat / 2).pow(2) +
                cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLng / 2).pow(2)
        return R * 2 * atan2(sqrt(a), sqrt(1 - a))
    }

    /** Maharashtra zone seed — used when API is unavailable. */
    private fun maharashtraDefaultZones() = listOf(
        DangerZone("z1", "Dharavi",               "URBAN",   "HIGH",       19.0390, 72.8530, 2000.0),
        DangerZone("z2", "Ratnagiri Coastal",      "COASTAL", "HIGH",       16.9902, 73.3120, 10000.0),
        DangerZone("z3", "Tadoba Tiger Reserve",   "FOREST",  "RESTRICTED", 20.2280, 79.3950, 30000.0),
        DangerZone("z4", "Melghat Tiger Reserve",  "FOREST",  "RESTRICTED", 21.5000, 77.0000, 40000.0)
    )
}
