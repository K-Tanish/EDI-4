package com.tourist.safety

// ── Firebase / legacy models ───────────────────────────────────────────────
data class Tourist(val createdAt: Long = 0L, val status: String = "SAFE")
data class LiveLocation(
    val latitude: Double = 0.0,
    val longitude: Double = 0.0,
    val time: Long = 0L,
    val status: String = "SAFE",
    val safetyScore: Int = 100,
    val safetyLabel: String = "SAFE",
    val zoneRiskLevel: String = "LOW",
    val simulatedTime: Long = 0L,
    val actualEmittedAtMs: Long = 0L
)
data class LocationEntry(val latitude: Double = 0.0, val longitude: Double = 0.0, val time: Long = 0L)
data class SosAlert(val latitude: Double = 0.0, val longitude: Double = 0.0, val time: Long = 0L, val status: String = "ACTIVE")
data class Alert(
    val touristId: String = "",
    val type: String = "",
    val risk: String = "",
    val latitude: Double = 0.0,
    val longitude: Double = 0.0,
    val time: Long = 0L,
    val zoneName: String = "",
    val simulatedTimestamp: Long = 0L,
    val actualEmittedAtMs: Long = 0L,
    val processingLatencyMs: Double = 0.0
)

// ── Maharashtra-specific domain models ────────────────────────────────────
data class DangerZone(
    val zoneId: String = "",
    val name: String = "",
    val type: String = "URBAN",          // URBAN | COASTAL | HILL_STATION | FOREST | HERITAGE
    val riskLevel: String = "LOW",       // LOW | MEDIUM | HIGH | RESTRICTED
    val latitude: Double = 0.0,
    val longitude: Double = 0.0,
    val radiusMeters: Double = 1000.0,
    val active: Boolean = true
)

data class TouristRecord(
    val touristId: String = "",
    val validUntil: Long = 0L,
    val txHash: String? = null
)

data class RegistrationRequest(
    val idType: String,      // "aadhaar" | "passport"
    val idValue: String,
    val visitStart: Long,
    val visitEnd: Long,
    val region: String = "Maharashtra",
    val name: String = ""
)

data class LocationPayload(
    val touristId: String,
    val latitude: Double,
    val longitude: Double,
    val timestamp: Long,
    val accuracy: Float = 0f,
    val isOfflineBuffered: Boolean = false,
    val emittedAtMs: Long = 0L
)

data class SosRequest(
    val touristId: String,
    val latitude: Double,
    val longitude: Double,
    val timestamp: Long? = null
)

data class SafetyScore(
    val touristId: String = "",
    val score: Int = 100,
    val label: String = "SAFE"   // SAFE | CAUTION | DANGER
)
